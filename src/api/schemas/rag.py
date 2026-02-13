from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class RagReindexRequest(BaseModel):
    author_id: Optional[str] = None
