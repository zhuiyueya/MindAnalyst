from __future__ import annotations

from typing import Literal, Optional, List

from pydantic import BaseModel, Field


class BilibiliAdapterError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        operation: str,
        ref: Optional[str] = None,
        cause: Optional[BaseException] = None,
    ):
        super().__init__(message)
        self.operation = operation
        self.ref = ref
        self.cause = cause


class AuthorProfile(BaseModel):
    platform: Literal["bilibili"] = "bilibili"
    external_id: str
    name: str
    avatar_url: Optional[str] = None
    homepage_url: Optional[str] = None


class VideoItem(BaseModel):
    bvid: str
    title: str
    url: str


class AuthorVideosResult(BaseModel):
    author: AuthorProfile
    videos: List[VideoItem] = Field(default_factory=list)
    source: Literal["browser", "bilix_api"]
    parse_warnings: List[str] = Field(default_factory=list)


class VideoMeta(BaseModel):
    bvid: str
    title: Optional[str] = None
    desc: Optional[str] = None
    duration_s: Optional[int] = None
    cid: Optional[int] = None
    parse_warnings: List[str] = Field(default_factory=list)


class SubtitleLine(BaseModel):
    start_s: float
    end_s: float
    text: str


class DownloadedAudio(BaseModel):
    local_path: str
    bvid: str
    parse_warnings: List[str] = Field(default_factory=list)
