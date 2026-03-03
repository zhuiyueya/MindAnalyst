from __future__ import annotations

from typing import Dict, List, Literal, Optional, Protocol

from pydantic import BaseModel, Field


class EmbeddingAdapterError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        operation: Literal["embed_text", "embed_texts", "load_model"],
        model: Optional[str] = None,
        cause: Optional[BaseException] = None,
    ):
        super().__init__(message)
        self.message = message
        self.operation = operation
        self.model = model
        self.cause = cause


class EmbeddingVector(BaseModel):
    values: List[float]
    dim: int
    model: str
    provider: str
    normalized: bool
    parse_warnings: List[str] = Field(default_factory=list)
    meta: Dict[str, str] = Field(default_factory=dict)


class EmbeddingBatchResult(BaseModel):
    vectors: List[EmbeddingVector]
    model: str
    provider: str
    normalized: bool
    parse_warnings: List[str] = Field(default_factory=list)


class EmbeddingProvider(Protocol):
    name: str

    def get_model_name(self) -> str: ...

    def embed_texts(self, texts: List[str], *, normalize: bool) -> List[List[float]]: ...
