from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True, slots=True)
class RagDoc:
    rag_id: str
    source_type: str
    summary_id: str
    content_id: str

    title: str
    url: str

    tag: Optional[str]
    text: str

    content_type: Optional[str] = None


@dataclass(frozen=True, slots=True)
class Citation:
    index: int

    source_type: Optional[str] = None
    tag: Optional[str] = None

    rag_id: Optional[str] = None
    summary_id: Optional[str] = None
    content_id: Optional[str] = None

    title: Optional[str] = None
    url: Optional[str] = None
    text: Optional[str] = None

    report_id: Optional[str] = None
    report_type: Optional[str] = None
    created_at: Optional[datetime] = None


@dataclass(frozen=True, slots=True)
class RagChatResponse:
    answer: str
    citations: list[Citation]
