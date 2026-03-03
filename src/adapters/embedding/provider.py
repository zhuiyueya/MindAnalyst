from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

from sentence_transformers import SentenceTransformer

from src.core.config import settings
from src.adapters.embedding.types import EmbeddingAdapterError

logger = logging.getLogger(__name__)


_EMBEDDER_CACHE: Dict[Tuple[str, Optional[str]], SentenceTransformer] = {}


def _get_embedder(model_name: str, device: Optional[str]) -> SentenceTransformer:
    key = (model_name, device)
    cached = _EMBEDDER_CACHE.get(key)
    if cached is not None:
        return cached

    try:
        if device:
            embedder = SentenceTransformer(model_name, device=device)
        else:
            embedder = SentenceTransformer(model_name)
        _EMBEDDER_CACHE[key] = embedder
        return embedder
    except Exception as exc:
        raise EmbeddingAdapterError(
            "Failed to load embedder",
            operation="load_model",
            model=model_name,
            cause=exc,
        ) from exc


class SentenceTransformerProvider:
    def __init__(self, *, model_name: str, device: Optional[str] = None, batch_size: int = 32):
        self.name = "sentence_transformer"
        self._model_name = model_name
        self._device = device
        self._batch_size = batch_size

    def get_model_name(self) -> str:
        return self._model_name

    def embed_texts(self, texts: List[str], *, normalize: bool) -> List[List[float]]:
        embedder = _get_embedder(self._model_name, self._device)
        try:
            vecs = embedder.encode(
                texts,
                batch_size=self._batch_size,
                normalize_embeddings=normalize,
                show_progress_bar=False,
            )
            return vecs.tolist()
        except Exception as exc:
            raise EmbeddingAdapterError(
                "Embedding encode failed",
                operation="embed_texts",
                model=self._model_name,
                cause=exc,
            ) from exc


def embed_text(text: str) -> List[float]:
    logger.warning(
        "src.adapters.embedding.provider.embed_text is deprecated; use EmbeddingService instead"
    )
    from src.adapters.embedding.service import EmbeddingService

    vec = EmbeddingService().embed_text(text)
    return vec.values
