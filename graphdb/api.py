"""Thin FastAPI layer over ``graphdb.queries``.

The route handlers contain no graph logic. They validate input, call the stable
query functions, and serialize the plain dictionaries returned by them.

Configuration comes from the same ``NEO4J_*`` environment variables as the rest
of the backend. The app is created without loading configuration at import time
so tests can inject a fake client.
"""

from __future__ import annotations

import datetime as dt
import logging
import os
import secrets
import time
from collections.abc import Sequence
from contextlib import asynccontextmanager
from typing import Any, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from pydantic import BaseModel, Field

from common.embed import Embedder, get_embedder
from common.log import configure_logging
from graphdb.config import Neo4jConfig, load_neo4j_config
from graphdb.connection import Neo4jClient
from graphdb.health import check_health
from graphdb.queries import (
    MAX_CHAIN_DEPTH,
    chain_by_date_range,
    chain_by_entity,
    chain_by_topic,
    event_by_id,
    events_in_date_range,
    articles_by_ids,
    top_entities,
)

from graphdb.search import DEFAULT_EVENTS, MAX_EVENTS, search_graph

STATIC_DIR = Path(__file__).parent / "static"

API_TITLE = "Temporal Knowledge Graph API"
API_VERSION = "0.2.0"

log = logging.getLogger("graphdb.api")


def _env_list(name: str) -> list[str]:
    return [item.strip() for item in os.environ.get(name, "").split(",") if item.strip()]


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes"}


class EntityModel(BaseModel):
    id: str
    name: str
    type: str


class EventModel(BaseModel):
    id: str
    description: str
    date: str | None = None
    date_key: int | None = None
    type: str
    date_source: str | None = None
    article_id: str | None = None
    entities: list[EntityModel] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)


class LinkModel(BaseModel):
    from_event_id: str
    to_event_id: str
    confidence: float
    reason: str
    from_date: str | None = None
    to_date: str | None = None


class ChainModel(BaseModel):
    query: dict[str, Any]
    entity: EntityModel | None = None
    topic: str | None = None
    match_mode: str
    ambiguous: bool = False
    events: list[EventModel] = Field(default_factory=list)
    links: list[LinkModel] = Field(default_factory=list)
    truncated: bool = False


class ArticleModel(BaseModel):
    id: str
    title: str | None = None
    url: str | None = None
    source: str | None = None
    date: str | None = None


class TopEntityModel(EntityModel):
    events: int


class InterpretationModel(BaseModel):
    entities: list[dict[str, Any]] = Field(default_factory=list)
    start: str | None = None
    end: str | None = None
    date_text: str | None = None
    keywords: list[str] = Field(default_factory=list)
    semantic: bool = False


class GraphNodeModel(BaseModel, extra="allow"):
    id: str
    kind: Literal["event", "entity", "topic"]
    label: str | None = None
    degree: int = 0


class GraphEdgeModel(BaseModel):
    source: str
    target: str
    kind: Literal["involves", "about", "linked_to"]
    confidence: float | None = None
    reason: str | None = None


class SourceModel(BaseModel):
    id: str
    title: str | None = None
    url: str | None = None
    publisher: str | None = None
    date: str | None = None


class GraphModel(BaseModel):
    query: str
    interpretation: InterpretationModel
    nodes: list[GraphNodeModel] = Field(default_factory=list)
    edges: list[GraphEdgeModel] = Field(default_factory=list)
    sources: list[SourceModel] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)


class Neo4jHealthModel(BaseModel):
    connected: bool
    database: str
    server_version: str | None = None
    edition: str | None = None
    error: str | None = None


class HealthModel(BaseModel):
    status: Literal["ok", "degraded"]
    neo4j: Neo4jHealthModel


_FAKE_TEST_CONFIG = Neo4jConfig(
    uri="bolt://test.invalid:7687",
    user="test",
    password="",
    database="neo4j",
)


def create_app(
    client: Neo4jClient | None = None,
    config: Neo4jConfig | None = None,
    api_keys: Sequence[str] | None = None,
    cors_origins: Sequence[str] | None = None,
    embedder: Embedder | None = None,
) -> FastAPI:
    """Create the FastAPI app.

    When ``client`` is supplied (tests), it is used directly and closed by the
    caller. Otherwise a real client is created from the environment at startup.

    Every route except ``/health`` requires an ``X-API-Key`` header matching one of
    ``api_keys`` (default: comma-separated ``API_KEYS``). Without keys the app fails
    closed: a real deployment refuses to start unless ``API_AUTH_DISABLED=true``.
    An injected test client with no keys runs unauthenticated.
    """

    keys = list(api_keys) if api_keys is not None else _env_list("API_KEYS")
    auth_disabled = not keys and (client is not None or _env_flag("API_AUTH_DISABLED"))
    origins = list(cors_origins) if cors_origins is not None else _env_list("API_CORS_ORIGINS")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if client is None:
            # uvicorn only configures its own loggers; route the app's records to stderr too.
            configure_logging()
        if not keys and not auth_disabled:
            raise RuntimeError("API_KEYS is not set; refusing to serve an unauthenticated API "
                               "(set API_AUTH_DISABLED=true for local development only)")
        if auth_disabled:
            log.warning("API authentication is disabled")
        # Injected (tests) or the shared model; None means prompt search uses keywords only.
        app.state.embedder = embedder if (embedder is not None or client is not None) else get_embedder()
        if client is not None:
            app.state.neo4j_client = client
            app.state.neo4j_config = config or _FAKE_TEST_CONFIG
            yield
            return

        real_config = config or load_neo4j_config()
        real_client = Neo4jClient(real_config)
        app.state.neo4j_client = real_client
        app.state.neo4j_config = real_config
        try:
            yield
        finally:
            real_client.close()

    app = FastAPI(title=API_TITLE, version=API_VERSION, lifespan=lifespan)
    if origins:
        app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET"],
                           allow_headers=["X-API-Key"])

    @app.middleware("http")
    async def access_log(request: Request, call_next):
        started = time.perf_counter()
        response = await call_next(request)
        log.info("request", extra={"fields": {
            "method": request.method, "path": request.url.path, "status": response.status_code,
            "ms": round((time.perf_counter() - started) * 1000, 1)}})
        return response

    def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
        if auth_disabled:
            return
        if not x_api_key or not any(secrets.compare_digest(x_api_key, key) for key in keys):
            raise HTTPException(status_code=401, detail="Missing or invalid X-API-Key header")

    protected = [Depends(require_api_key)]

    def get_client(request: Request) -> Neo4jClient:
        return request.app.state.neo4j_client

    def get_config(request: Request) -> Neo4jConfig:
        return request.app.state.neo4j_config

    @app.get("/health", response_model=HealthModel)
    def health(
        neo4j_client: Neo4jClient = Depends(get_client),
        neo4j_config: Neo4jConfig = Depends(get_config),
    ):
        report = check_health(neo4j_config, client=neo4j_client)
        model = HealthModel(
            status="ok" if report.connected else "degraded",
            neo4j=Neo4jHealthModel(
                connected=report.connected,
                database=report.database,
                server_version=report.server_version,
                edition=report.edition,
                error=report.error,
            ),
        )
        if not report.connected:
            return JSONResponse(status_code=503, content=model.model_dump())
        return model

    @app.get("/events/{event_id}", response_model=EventModel, dependencies=protected)
    def get_event(
        event_id: str,
        neo4j_client: Neo4jClient = Depends(get_client),
    ):
        event = event_by_id(neo4j_client, event_id)
        if event is None:
            raise HTTPException(status_code=404, detail=f"event not found: {event_id}")
        return event

    @app.get("/events", response_model=list[EventModel], dependencies=protected)
    def list_events(
        start: dt.date = Query(..., description="Inclusive ISO start date"),
        end: dt.date = Query(..., description="Inclusive ISO end date"),
        limit: int = Query(100, ge=1, le=1000),
        offset: int = Query(0, ge=0),
        neo4j_client: Neo4jClient = Depends(get_client),
    ):
        try:
            return events_in_date_range(neo4j_client, start, end, limit=limit, offset=offset)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/chains/entity", response_model=ChainModel, dependencies=protected)
    def entity_chain(
        name: str = Query(..., min_length=1),
        min_confidence: float = Query(0.0, ge=0.0, le=1.0),
        depth: int = Query(3, ge=1, le=MAX_CHAIN_DEPTH),
        limit: int = Query(100, ge=1, le=1000),
        neo4j_client: Neo4jClient = Depends(get_client),
    ):
        try:
            return chain_by_entity(
                neo4j_client, name, min_confidence=min_confidence, depth=depth, limit=limit
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/chains/topic", response_model=ChainModel, dependencies=protected)
    def topic_chain(
        topic: str = Query(..., min_length=1),
        min_confidence: float = Query(0.0, ge=0.0, le=1.0),
        depth: int = Query(3, ge=1, le=MAX_CHAIN_DEPTH),
        limit: int = Query(100, ge=1, le=1000),
        neo4j_client: Neo4jClient = Depends(get_client),
    ):
        try:
            return chain_by_topic(
                neo4j_client, topic, min_confidence=min_confidence, depth=depth, limit=limit
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/chains/date-range", response_model=ChainModel, dependencies=protected)
    def date_range_chain(
        start: dt.date = Query(..., description="Inclusive ISO start date"),
        end: dt.date = Query(..., description="Inclusive ISO end date"),
        min_confidence: float = Query(0.0, ge=0.0, le=1.0),
        depth: int = Query(3, ge=1, le=MAX_CHAIN_DEPTH),
        limit: int = Query(100, ge=1, le=1000),
        neo4j_client: Neo4jClient = Depends(get_client),
    ):
        try:
            return chain_by_date_range(
                neo4j_client,
                start,
                end,
                min_confidence=min_confidence,
                depth=depth,
                limit=limit,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/articles", response_model=list[ArticleModel], dependencies=protected)
    def articles(
        ids: str = Query(..., description="Comma-separated article ids (max 200)"),
        neo4j_client: Neo4jClient = Depends(get_client),
    ):
        try:
            return articles_by_ids(neo4j_client, [i.strip() for i in ids.split(",") if i.strip()])
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/entities/top", response_model=list[TopEntityModel], dependencies=protected)
    def entities_top(
        limit: int = Query(20, ge=1, le=100),
        neo4j_client: Neo4jClient = Depends(get_client),
    ):
        return top_entities(neo4j_client, limit=limit)

    @app.get("/graph", response_model=GraphModel, dependencies=protected)
    def graph(
        request: Request,
        q: str = Query(..., min_length=1, max_length=500, description="Free-text prompt"),
        limit: int = Query(DEFAULT_EVENTS, ge=1, le=MAX_EVENTS, description="Max events in the graph"),
        neo4j_client: Neo4jClient = Depends(get_client),
    ):
        try:
            return search_graph(neo4j_client, q, request.app.state.embedder, limit=limit)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    # The browser UI. Mounted last so every API route above takes precedence.
    if STATIC_DIR.is_dir():
        app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="ui")

    return app


app = create_app()


if __name__ == "__main__":  # pragma: no cover - manual entry point
    import uvicorn

    uvicorn.run("graphdb.api:app", host="127.0.0.1", port=8000, reload=False)
