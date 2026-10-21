"""Text embeddings shared by ingestion (indexing events) and the API (embedding prompts).

Both sides must use the same model, so the model name is stored on every embedded Event
(``embedding_model``) and events embedded with a different model are re-embedded.

Default model: model2vec ``minishlab/potion-base-8M`` (MIT): static embeddings, 256 dims,
~30 MB, numpy only (no PyTorch), a few ms per batch on CPU.
"""

import logging
import os
from typing import Protocol

import numpy as np

DEFAULT_MODEL = "minishlab/potion-base-8M"

log = logging.getLogger(__name__)


class Embedder(Protocol):
    name: str
    dims: int

    def encode(self, texts: list[str]) -> list[list[float]]: ...


class Model2VecEmbedder:
    def __init__(self, name: str | None = None):
        from model2vec import StaticModel

        self.name = name or os.environ.get("EMBEDDING_MODEL") or DEFAULT_MODEL
        self._model = StaticModel.from_pretrained(self.name)
        self.dims = int(self._model.dim)

    def encode(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = np.asarray(self._model.encode(texts), dtype=np.float32)
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        return (vectors / np.where(norms == 0, 1, norms)).tolist()


def event_text(description: str, source_text: str = "", entities: list[str] = (), topic: str = "") -> str:
    # What an event "means" for search: its sentence, plus the names and topic it is filed under.
    parts = [source_text or description]
    if entities:
        parts.append(", ".join(entities))
    if topic and topic != "general":
        parts.append(topic)
    return ". ".join(p for p in parts if p)


_default: Embedder | None = None
_failed = False


def get_embedder() -> Embedder | None:
    """Process-wide embedder, or None if the model cannot be loaded (search then uses keywords only)."""

    global _default, _failed
    if _default is None and not _failed:
        try:
            _default = Model2VecEmbedder()
        except Exception:
            _failed = True
            log.exception("embedding model unavailable; semantic search disabled")
    return _default
