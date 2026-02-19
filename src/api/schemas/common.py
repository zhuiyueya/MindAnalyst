from __future__ import annotations

from typing import Any

from pydantic import BaseModel, RootModel


class TaskStartedResponse(BaseModel):
    status: str
    message: str


class RagReindexResponse(BaseModel):
    status: str
    scope: str
    author_id: str | None = None


class AuthorTypeSetResponse(BaseModel):
    author_id: str
    author_type: str | None


class VideoTypeSetResponse(BaseModel):
    video: dict[str, Any]


class PlaybackUrlResponse(BaseModel):
    url: str


class LlmCallsListResponse(BaseModel):
    items: list[dict[str, Any]]
    total: int
    limit: int
    offset: int


class AuthorsListResponse(RootModel[list[dict[str, Any]]]):
    pass


class AuthorDetailResponse(BaseModel):
    author: dict[str, Any]
    latest_report: dict[str, Any] | None
    reports: list[dict[str, Any]]
    reports_by_type: dict[str, list[dict[str, Any]]]
    category_reports_by_type: dict[str, dict[str, dict[str, Any]]]
    author_status: dict[str, Any]


class VideosListResponse(RootModel[list[dict[str, Any]]]):
    pass


class VideoDetailResponse(BaseModel):
    video: dict[str, Any]
    summary: dict[str, Any] | None
    segments: list[dict[str, Any]]
