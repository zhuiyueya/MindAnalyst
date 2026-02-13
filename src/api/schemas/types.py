from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class AuthorTypeRequest(BaseModel):
    author_type: Optional[str] = None


class ContentTypeRequest(BaseModel):
    content_type: Optional[str] = None
