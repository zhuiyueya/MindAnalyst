from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel


class ChatRequest(BaseModel):
    query: str
    author_id: Optional[str] = None


class ChatResponse(BaseModel):
    answer: str
    citations: List[dict[str, Any]]
