from __future__ import annotations

import logging
from typing import List, Optional

from sentence_transformers import SentenceTransformer

from src.core.config import settings

logger = logging.getLogger(__name__)


_embedder: Optional[SentenceTransformer] = None
_embedder_model_name: Optional[str] = None


def get_embedder() -> Optional[SentenceTransformer]:
    global _embedder
    global _embedder_model_name

    model_name = settings.EMBEDDING_MODEL_NAME
    if _embedder is not None and _embedder_model_name == model_name:
        return _embedder

    try:
        _embedder = SentenceTransformer(model_name)
        _embedder_model_name = model_name
        return _embedder
    except Exception as exc:
        logger.warning("Failed to load embedder model=%s: %s", model_name, exc)
        _embedder = None
        _embedder_model_name = model_name
        return None


def embed_text(text: str) -> List[float]:
    embedder = get_embedder()
    if embedder is None:
        return [0.0] * 384
    return embedder.encode(text).tolist()
