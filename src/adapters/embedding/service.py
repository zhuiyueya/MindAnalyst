from __future__ import annotations

import logging
from typing import List, Optional

from src.adapters.embedding.types import (
    EmbeddingAdapterError,
    EmbeddingBatchResult,
    EmbeddingProvider,
    EmbeddingVector,
)
from src.core.config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    def __init__(self, provider: Optional[EmbeddingProvider] = None):
        self._provider = provider or self._build_provider_from_settings()

    def _build_provider_from_settings(self) -> EmbeddingProvider:
        provider_name = (getattr(settings, "EMBEDDING_PROVIDER", "") or "").strip() or "sentence_transformer"
        if provider_name != "sentence_transformer":
            raise EmbeddingAdapterError(
                f"Unsupported EMBEDDING_PROVIDER: {provider_name}",
                operation="load_model",
                model=getattr(settings, "EMBEDDING_MODEL_NAME", None),
            )

        from src.adapters.embedding.provider import SentenceTransformerProvider

        device = (getattr(settings, "EMBEDDING_DEVICE", "") or "").strip() or None
        batch_size = int(getattr(settings, "EMBEDDING_BATCH_SIZE", 32))

        return SentenceTransformerProvider(
            model_name=settings.EMBEDDING_MODEL_NAME,
            device=device,
            batch_size=batch_size,
        )

    def embed_text(self, text: str) -> EmbeddingVector:
        res = self.embed_texts([text])
        return res.vectors[0]

    def embed_texts(self, texts: List[str]) -> EmbeddingBatchResult:
        if not isinstance(texts, list) or not texts:
            raise EmbeddingAdapterError("texts_empty", operation="embed_texts", model=self._provider.get_model_name())

        max_chars = int(getattr(settings, "EMBEDDING_MAX_CHARS", 8000))
        normalize = bool(getattr(settings, "EMBEDDING_NORMALIZE", True))

        cleaned: List[str] = []
        batch_warnings: List[str] = []

        for idx, t in enumerate(texts):
            if not isinstance(t, str):
                raise EmbeddingAdapterError("text_not_str", operation="embed_texts", model=self._provider.get_model_name())

            s = t.strip()
            if not s:
                raise EmbeddingAdapterError("text_empty", operation="embed_texts", model=self._provider.get_model_name())

            if max_chars > 0 and len(s) > max_chars:
                s = s[:max_chars]
                batch_warnings.append(f"text_truncated:{idx}")

            cleaned.append(s)

        try:
            vectors = self._provider.embed_texts(cleaned, normalize=normalize)
        except Exception as exc:
            raise EmbeddingAdapterError(
                "Embedding provider failed",
                operation="embed_texts",
                model=self._provider.get_model_name(),
                cause=exc,
            ) from exc

        if len(vectors) != len(cleaned):
            raise EmbeddingAdapterError(
                "Embedding vector count mismatch",
                operation="embed_texts",
                model=self._provider.get_model_name(),
            )

        out: List[EmbeddingVector] = []
        for v in vectors:
            if not isinstance(v, list):
                raise EmbeddingAdapterError(
                    "Embedding vector not list",
                    operation="embed_texts",
                    model=self._provider.get_model_name(),
                )

            dim = len(v)
            out.append(
                EmbeddingVector(
                    values=[float(x) for x in v],
                    dim=dim,
                    model=self._provider.get_model_name(),
                    provider=self._provider.name,
                    normalized=normalize,
                    parse_warnings=[],
                )
            )

        return EmbeddingBatchResult(
            vectors=out,
            model=self._provider.get_model_name(),
            provider=self._provider.name,
            normalized=normalize,
            parse_warnings=batch_warnings,
        )
