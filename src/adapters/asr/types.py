from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Protocol

from pydantic import BaseModel, Field


class ASRAdapterError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        operation: Literal["transcribe", "convert_audio"],
        ref: Optional[str] = None,
        cause: Optional[BaseException] = None,
    ):
        super().__init__(message)
        self.message = message
        self.operation = operation
        self.ref = ref
        self.cause = cause


class AsrSegment(BaseModel):
    start_s: float
    end_s: float
    text: str
    confidence: Optional[float] = None
    parse_warnings: List[str] = Field(default_factory=list)


class AsrTranscriptionResult(BaseModel):
    text: str
    segments: List[AsrSegment] = Field(default_factory=list)
    language: Optional[str] = None
    duration_s: Optional[float] = None

    provider: str
    model: str

    parse_warnings: List[str] = Field(default_factory=list)
    meta: Dict[str, str] = Field(default_factory=dict)


class ASRProvider(Protocol):
    name: str

    async def transcribe_file(self, file_path: str, *, language: Optional[str] = None) -> AsrTranscriptionResult: ...
