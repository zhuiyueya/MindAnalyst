from __future__ import annotations

import logging
from typing import Optional

from src.adapters.sources.bilibili.types import (
    AuthorVideosResult,
    BilibiliAdapterError,
    DownloadedAudio,
    SubtitleLine,
    VideoMeta,
)
from src.adapters.sources.bilibili.browser import BrowserProvider
from src.adapters.sources.bilibili.bilix import BilixProvider

logger = logging.getLogger(__name__)


class BilibiliSourceService:
    def __init__(self):
        self._browser = BrowserProvider()
        self._bilix = BilixProvider()

    def _normalize_for_browser(self, author_ref: str) -> str:
        ref = (author_ref or "").strip()
        if not ref:
            return ref
        if ref.startswith("http://") or ref.startswith("https://"):
            return ref
        # Assume it's a mid
        return f"https://space.bilibili.com/{ref}"

    async def fetch_author_and_videos(self, author_ref: str, limit: int = 0) -> AuthorVideosResult:
        try:
            browser_ref = self._normalize_for_browser(author_ref)
            result = await self._browser.fetch_author_and_videos(browser_ref, limit=limit)
            if not result.videos:
                raise BilibiliAdapterError(
                    "No videos found from browser provider",
                    operation="fetch_author_and_videos",
                    ref=author_ref,
                )
            if not result.author.external_id or result.author.external_id == "0":
                raise BilibiliAdapterError(
                    "Author mid missing from browser provider",
                    operation="fetch_author_and_videos",
                    ref=author_ref,
                )
            return result
        except Exception as exc:
            logger.warning("Browser provider failed, falling back to bilix: %s", exc)
            result = await self._bilix.fetch_author_and_videos(author_ref, limit=limit)
            result.parse_warnings = list(result.parse_warnings) + ["fallback_from_browser"]
            return result

    async def fetch_video_meta(self, bvid: str, *, reuse_audio_only: bool = False) -> VideoMeta:
        return await self._bilix.fetch_video_meta(bvid, reuse_audio_only=reuse_audio_only)

    async def fetch_subtitles(self, bvid: str, cid: int) -> list[SubtitleLine]:
        return await self._bilix.fetch_subtitles(bvid, cid)

    async def download_audio(self, bvid: str) -> Optional[DownloadedAudio]:
        return await self._bilix.download_audio(bvid)
