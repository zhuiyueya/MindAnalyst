from __future__ import annotations

from pydantic import BaseModel


class IngestRequest(BaseModel):
    author_id: str
    limit: int = 10
