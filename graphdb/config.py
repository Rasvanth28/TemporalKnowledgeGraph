"""Environment-backed Neo4j configuration.

Credentials are read only from environment variables (optionally loaded from a
local ``.env``). Error messages name missing variables but never include their
values.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import os

from dotenv import load_dotenv

_REQUIRED_VARIABLES = ("NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD")
_VALID_URI_PREFIXES = (
    "neo4j://",
    "neo4j+s://",
    "neo4j+ssc://",
    "bolt://",
    "bolt+s://",
    "bolt+ssc://",
)


class ConfigurationError(ValueError):
    """Raised when required Neo4j configuration is missing or invalid."""


@dataclass(frozen=True)
class Neo4jConfig:
    """Validated Neo4j connection settings.

    ``password`` is excluded from ``repr`` so accidental logging of the config
    cannot expose it.
    """

    uri: str
    user: str
    password: str = field(repr=False)
    database: str = "neo4j"


def load_neo4j_config(env: Mapping[str, str] | None = None) -> Neo4jConfig:
    """Load and validate Neo4j settings.

    ``env`` is injectable for tests. When omitted, ``load_dotenv()`` is called
    and the process environment is used. The password is preserved exactly as
    supplied but is never included in an error or ``repr``.
    """

    if env is None:
        load_dotenv()
        env = os.environ

    missing = [
        name
        for name in _REQUIRED_VARIABLES
        if not (env.get(name) or "").strip()
    ]
    if missing:
        raise ConfigurationError(
            "Missing required Neo4j environment variable(s): " + ", ".join(missing)
        )

    uri = (env.get("NEO4J_URI") or "").strip()
    user = (env.get("NEO4J_USER") or "").strip()
    password = env.get("NEO4J_PASSWORD") or ""
    database = (env.get("NEO4J_DATABASE") or "").strip() or "neo4j"

    if not uri.lower().startswith(_VALID_URI_PREFIXES):
        raise ConfigurationError(
            "Invalid NEO4J_URI scheme. Expected one of: "
            + ", ".join(prefix.rstrip("://") for prefix in _VALID_URI_PREFIXES)
        )

    return Neo4jConfig(uri=uri, user=user, password=password, database=database)


_LOCAL_HOSTS = ("localhost", "127.0.0.1", "[::1]")


def load_neo4j_test_config(env: Mapping[str, str] | None = None) -> Neo4jConfig:
    """Load the throwaway database used by integration tests.

    Integration tests wipe their database, so they read ``NEO4J_TEST_*`` and
    never ``NEO4J_*``. Two guards keep them away from real data: the test URI
    must differ from ``NEO4J_URI``, and it must be local unless
    ``NEO4J_TEST_ALLOW_REMOTE=true`` is set explicitly.
    """

    if env is None:
        load_dotenv()
        env = os.environ

    config = load_neo4j_config(
        {
            "NEO4J_URI": env.get("NEO4J_TEST_URI", ""),
            "NEO4J_USER": env.get("NEO4J_TEST_USER", ""),
            "NEO4J_PASSWORD": env.get("NEO4J_TEST_PASSWORD", ""),
            "NEO4J_DATABASE": env.get("NEO4J_TEST_DATABASE", ""),
        }
    )
    real_uri = (env.get("NEO4J_URI") or "").strip().rstrip("/")
    if real_uri and config.uri.rstrip("/") == real_uri:
        raise ConfigurationError("NEO4J_TEST_URI must not point at the NEO4J_URI database")
    host = config.uri.split("://", 1)[1].split("/", 1)[0].rsplit(":", 1)[0]
    allow_remote = (env.get("NEO4J_TEST_ALLOW_REMOTE") or "").strip().lower() in {"1", "true", "yes"}
    if host not in _LOCAL_HOSTS and not allow_remote:
        raise ConfigurationError(
            "NEO4J_TEST_URI is not local; set NEO4J_TEST_ALLOW_REMOTE=true if it is a dedicated test database"
        )
    return config
