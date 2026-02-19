from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class TaskStartedResult:
    status: str
    message: str


@dataclass(frozen=True, slots=True)
class RagReindexResult:
    status: str
    scope: str
    author_id: str | None = None


@dataclass(frozen=True, slots=True)
class AuthorTypeSetResult:
    author_id: str
    author_type: str | None


@dataclass(frozen=True, slots=True)
class VideoTypeSetResult:
    video: dict[str, Any]


@dataclass(frozen=True, slots=True)
class PlaybackUrlResult:
    url: str


@dataclass(frozen=True, slots=True)
class LlmCallsPageResult:
    items: list[dict[str, Any]]
    total: int
    limit: int
    offset: int


@dataclass(frozen=True, slots=True)
class AuthorsListResult:
    items: list[dict[str, Any]]


@dataclass(frozen=True, slots=True)
class AuthorDetailResult:
    author: dict[str, Any]
    latest_report: dict[str, Any] | None
    reports: list[dict[str, Any]]
    reports_by_type: dict[str, list[dict[str, Any]]]
    category_reports_by_type: dict[str, dict[str, dict[str, Any]]]
    author_status: dict[str, Any]


@dataclass(frozen=True, slots=True)
class VideosListResult:
    items: list[dict[str, Any]]


@dataclass(frozen=True, slots=True)
class VideoDetailResult:
    video: dict[str, Any]
    summary: dict[str, Any] | None
    segments: list[dict[str, Any]]
