import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional, Protocol, Sequence, TypedDict, cast
from bilix.sites.bilibili import DownloaderBilibili
from bilix.sites.bilibili import api
import httpx
import logging

from src.core.config import settings
from src.adapters.sources.bilibili.types import (
    AuthorProfile,
    AuthorVideosResult,
    BilibiliAdapterError,
    DownloadedAudio,
    SubtitleLine,
    VideoItem,
    VideoMeta,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class BilixAuthorInfo:
    """Author info returned by Bilix-related API calls (normalized)."""

    name: str
    face: str
    mid: str
    desc: str


@dataclass(frozen=True, slots=True)
class BilixVideoInfo:
    """Video info returned by Bilix-related API calls (normalized)."""

    bvid: str
    title: str
    created: int
    length: int
    pic: str


@dataclass(frozen=True, slots=True)
class BilixVideoDetail:
    """Video detail info returned by Bilix-related API calls (normalized)."""

    cid: int
    title: str
    desc: str
    duration: int


@dataclass(frozen=True, slots=True)
class BilixSubtitleLine:
    """A single subtitle line."""

    start_s: float
    end_s: float
    content: str


class _BilixSubtitleMeta(Protocol):
    """A minimal view of bilix subtitle meta items.

    bilix's `api.get_subtitle_info` return type is not exposed precisely to us.
    We only rely on `lan` and `url`.
    """

    lan: str
    url: str


class BilixUpInfoDict(TypedDict, total=False):
    name: str
    face: str
    mid: int | str
    desc: str
    sign: str


_BilixSubtitleJsonRow = TypedDict(
    "_BilixSubtitleJsonRow",
    {"from": float, "to": float, "content": str},
    total=False,
)

class BilixCrawler:
    def __init__(self, download_dir: Optional[str] = None):
        resolved_dir = download_dir or settings.BILIBILI_DOWNLOAD_DIR
        self.download_dir = resolved_dir
        if not os.path.exists(self.download_dir):
            os.makedirs(self.download_dir)
        # We'll create a client for API calls
        self.headers = {
            "User-Agent": settings.BILIBILI_USER_AGENT,
            "Referer": "https://www.bilibili.com/"
        }

    async def get_author_info(self, url_or_mid: str) -> BilixAuthorInfo:
        """
        Get author info.
        If url_or_mid is a Video URL, fetch video info and extract author.
        """
        # Check if it's a Video URL (BV...)
        bvid = None
        if "bilibili.com/video/BV" in url_or_mid:
            bvid = "BV" + url_or_mid.split("/BV")[1].split("/")[0].split("?")[0]
        elif url_or_mid.startswith("BV"):
            bvid = url_or_mid
            
        async with httpx.AsyncClient(headers=self.headers) as client:
            try:
                if bvid:
                    # Fetch video info to get author
                    info = await api.get_video_info(client, f"https://www.bilibili.com/video/{bvid}")
                    
                    # Attempt to find author name
                    name = (
                        getattr(info, "owner_name", None)
                        or getattr(info, "author_name", None)
                        or getattr(info, "up_name", None)
                        or "Unknown Author"
                    )
                    mid = (
                        getattr(info, "owner_id", None)
                        or getattr(info, "mid", None)
                        or getattr(info, "up_mid", None)
                        or "0"
                    )
                    face = getattr(info, "owner_face", None) or getattr(info, "face", None) or ""
                    
                    return BilixAuthorInfo(name=str(name), face=str(face), mid=str(mid), desc=f"Author of {bvid}")
                
                # Normal Author Logic
                # bilix get_up_info signature: (client, url_or_mid)
                # Try to extract MID if it's a URL
                mid = url_or_mid
                if "space.bilibili.com" in url_or_mid:
                    mid = url_or_mid.split("space.bilibili.com/")[-1].split("/")[0].split("?")[0]
                
                info = await api.get_up_info(client, mid)
                logger.info(f"Bilix get_up_info result: {info}")
                
                # Handle if info is dict or object
                if isinstance(info, dict):
                    info_dict = cast(BilixUpInfoDict, info)
                    return BilixAuthorInfo(
                        name=str(info_dict.get("name", "Unknown Author")),
                        face=str(info_dict.get("face", "")),
                        mid=str(info_dict.get("mid", mid)),
                        desc=str(info_dict.get("desc", "") or info_dict.get("sign", "")),
                    )
                else:
                    return BilixAuthorInfo(
                        name=str(getattr(info, "name", "Unknown Author")),
                        face=str(getattr(info, "face", "")),
                        mid=str(getattr(info, "mid", mid)),
                        desc=str(getattr(info, "desc", "") or getattr(info, "sign", "")),
                    )
            except Exception as e:
                logger.error(f"Failed to get author info for {url_or_mid}: {e}")
                # Return dummy if failed?
                # For MVP test, let's raise
                raise

    async def get_videos(self, url_or_mid: str, limit: int = 10) -> List[BilixVideoInfo]:
        """
        Get videos for author.
        If input is Video URL, return that single video.
        """
        # Check if it's a Video URL
        bvid = None
        if "bilibili.com/video/BV" in url_or_mid:
            bvid = "BV" + url_or_mid.split("/BV")[1].split("/")[0].split("?")[0]
        elif url_or_mid.startswith("BV"):
            bvid = url_or_mid
            
        if bvid:
             async with httpx.AsyncClient(headers=self.headers) as client:
                 info = await api.get_video_info(client, f"https://www.bilibili.com/video/{bvid}")
                 
                 # Safely get fields
                 duration = getattr(info, "duration", 0)
                 # bilix duration might be milliseconds or seconds?
                 # usually seconds.
                 
                 bvid_value = getattr(info, "bvid", bvid)
                 title_value = getattr(info, "title", "Unknown Title")
                 created_value = getattr(info, "pub_date", 0) or getattr(info, "time", 0) or 0
                 pic_value = getattr(info, "img_url", "") or getattr(info, "cover", "")
                 return [
                     BilixVideoInfo(
                         bvid=str(bvid_value),
                         title=str(title_value),
                         created=int(created_value) if isinstance(created_value, int) else 0,
                         length=int(duration) if isinstance(duration, int) else 0,
                         pic=str(pic_value),
                     )
                 ]

        videos: List[BilixVideoInfo] = []
        page = 1
        page_size = 30
        
        async with httpx.AsyncClient(headers=self.headers) as client:
            while True:
                try:
                    batch = await api.get_up_video_info(client, url_or_mid, pn=page, ps=page_size)
                except Exception as e:
                    logger.warning(f"Failed to fetch videos via API for {url_or_mid}: {e}")
                    break
                
                if not batch:
                    break
                    
                for v in batch:
                    videos.append(
                        BilixVideoInfo(
                            bvid=str(getattr(v, "bvid", "")),
                            title=str(getattr(v, "title", "")),
                            created=int(getattr(v, "pub_date", 0)) if isinstance(getattr(v, "pub_date", 0), int) else 0,
                            length=int(getattr(v, "duration", 0)) if isinstance(getattr(v, "duration", 0), int) else 0,
                            pic=str(getattr(v, "cover", "")),
                        )
                    )
                    if 0 < limit <= len(videos):
                        return videos[:limit]
                
                page += 1
                    
        return videos

    async def get_video_info(self, bvid: str) -> BilixVideoDetail:
        """Get detail info"""
        async with httpx.AsyncClient(headers=self.headers) as client:
            info = await api.get_video_info(client, f"https://www.bilibili.com/video/{bvid}")
            
            # Safely get attributes
            cid = getattr(info, "cid", 0)
            title = getattr(info, "title", "Unknown Title")
            desc = getattr(info, "desc", "")
            duration = getattr(info, "duration", 0)
            
            return BilixVideoDetail(
                cid=int(cid) if isinstance(cid, int) else 0,
                title=str(title),
                desc=str(desc),
                duration=int(duration) if isinstance(duration, int) else 0,
            )

    async def get_subtitle(self, bvid: str, cid: int) -> List[BilixSubtitleLine]:
        """Get subtitles via bilix API and normalize into subtitle lines."""
        async with httpx.AsyncClient(headers=self.headers) as client:
            try:
                # bilix has get_subtitle_info(client, bvid, cid)
                # It returns list of available subtitles.
                # Then we need to download content.
                # Or maybe bilix has helper.
                
                # Let's use the one from `api`
                sub_info_raw = await api.get_subtitle_info(client, bvid, cid)
                sub_info = cast(Sequence[_BilixSubtitleMeta], sub_info_raw)
                
                # sub_info is likely a list of subtitle meta
                target_sub: Optional[_BilixSubtitleMeta] = next((s for s in sub_info if s.lan == "zh-CN"), None)
                if not target_sub and sub_info:
                    target_sub = sub_info[0]
                    
                if target_sub:
                    # Download content
                    resp = await client.get(target_sub.url)
                    # Bilibili json format
                    data_raw: Any = resp.json()
                    data_dict: dict[str, Any] = data_raw if isinstance(data_raw, dict) else {}
                    body_raw: object = data_dict.get("body", [])
                    body: list[Any] = []
                    if isinstance(body_raw, list):
                        body = cast(list[Any], body_raw)

                    items: List[BilixSubtitleLine] = []
                    
                    for row in body:
                        if not isinstance(row, dict):
                            continue
                        row_typed = cast(_BilixSubtitleJsonRow, row)
                        start = row_typed.get("from")
                        end = row_typed.get("to")
                        text = row_typed.get("content")
                        if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
                            continue
                        if not isinstance(text, str):
                            continue
                        text_clean = text.strip()
                        if not text_clean:
                            continue
                        items.append(
                            BilixSubtitleLine(start_s=float(start), end_s=float(end), content=text_clean)
                        )

                    return items
                    
            except Exception as e:
                logger.warning(f"Failed to get subtitle for {bvid}: {e}")
        
        return []

    async def download_audio(self, bvid: str) -> Optional[str]:
        """
        Download audio for video. Returns file path.
        """
        url = f"https://www.bilibili.com/video/{bvid}"
        try:
            # Clean download dir to ensure we capture the correct file
            # CAUTION: This assumes no concurrent downloads in this dir!
            for f in os.listdir(self.download_dir):
                fp = os.path.join(self.download_dir, f)
                try:
                    if os.path.isfile(fp):
                        os.unlink(fp)
                except Exception:
                    pass

            async with DownloaderBilibili(part_concurrency=1) as d:
                # bilix will download file here
                paths = await d.get_video(url, path=Path(self.download_dir), only_audio=True, image=False)
                
                if paths:
                    if isinstance(paths, list):
                        return str(paths[0])
                    return str(paths)
                
                # Fallback: Check directory for any downloaded file
                files = [f for f in os.listdir(self.download_dir) if not f.startswith(".")]
                if files:
                    # Return the first file found (assuming we cleaned dir)
                    return os.path.join(self.download_dir, files[0])
                
                return None

        except Exception as e:
            logger.error(f"Download audio failed for {bvid}: {e}")
            return None


class BilixProvider:
    def __init__(self):
        self._crawler = BilixCrawler()

    async def fetch_author_and_videos(self, author_ref: str, limit: int = 0) -> AuthorVideosResult:
        try:
            author = await self._crawler.get_author_info(author_ref)
            videos = await self._crawler.get_videos(author_ref, limit=limit or 0)
        except Exception as exc:
            raise BilibiliAdapterError(
                "Bilix fetch author/videos failed",
                operation="fetch_author_and_videos",
                ref=author_ref,
                cause=exc,
            ) from exc

        parse_warnings: list[str] = []
        mid = str(author.mid or "").strip()
        if not mid:
            mid = "0"
            parse_warnings.append("author_mid_missing")

        avatar_url = str(author.face or "").strip() or None
        if not avatar_url:
            parse_warnings.append("author_avatar_missing")

        name = str(author.name or "").strip() or "Unknown Author"
        if name == "Unknown Author":
            parse_warnings.append("author_name_unknown")

        profile = AuthorProfile(
            external_id=mid,
            name=name,
            avatar_url=avatar_url,
            homepage_url=f"https://space.bilibili.com/{mid}" if mid and mid != "0" else None,
        )

        items: list[VideoItem] = []
        for v in videos:
            bvid = str(getattr(v, "bvid", "") or "").strip()
            if not bvid:
                continue
            title = str(getattr(v, "title", "") or "").strip() or "Unknown Title"
            items.append(VideoItem(bvid=bvid, title=title, url=f"https://www.bilibili.com/video/{bvid}"))

        return AuthorVideosResult(author=profile, videos=items, source="bilix_api", parse_warnings=parse_warnings)

    async def fetch_video_meta(self, bvid: str, *, reuse_audio_only: bool = False) -> VideoMeta:
        if reuse_audio_only:
            return VideoMeta(bvid=bvid, parse_warnings=["reuse_audio_only_skip_meta"])

        try:
            detail = await self._crawler.get_video_info(bvid)
        except Exception as exc:
            raise BilibiliAdapterError(
                "Bilix fetch video meta failed",
                operation="fetch_video_meta",
                ref=bvid,
                cause=exc,
            ) from exc

        return VideoMeta(
            bvid=bvid,
            title=str(detail.title or "").strip() or None,
            desc=str(detail.desc or "").strip() or None,
            duration_s=int(detail.duration) if isinstance(detail.duration, int) and detail.duration > 0 else None,
            cid=int(detail.cid) if isinstance(detail.cid, int) and detail.cid > 0 else None,
            parse_warnings=[],
        )

    async def fetch_subtitles(self, bvid: str, cid: int) -> list[SubtitleLine]:
        if not cid:
            return []
        try:
            raw = await self._crawler.get_subtitle(bvid, cid)
        except Exception as exc:
            raise BilibiliAdapterError(
                "Bilix fetch subtitles failed",
                operation="fetch_subtitles",
                ref=bvid,
                cause=exc,
            ) from exc

        items: list[SubtitleLine] = []
        for row in raw:
            text = str(getattr(row, "content", "") or "").strip()
            if not text:
                continue
            start = getattr(row, "start_s", None)
            end = getattr(row, "end_s", None)
            if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
                continue
            items.append(SubtitleLine(start_s=float(start), end_s=float(end), text=text))
        return items

    async def download_audio(self, bvid: str) -> Optional[DownloadedAudio]:
        try:
            path = await self._crawler.download_audio(bvid)
        except Exception as exc:
            raise BilibiliAdapterError(
                "Bilix download audio failed",
                operation="download_audio",
                ref=bvid,
                cause=exc,
            ) from exc

        if not path:
            return None
        return DownloadedAudio(local_path=str(path), bvid=bvid, parse_warnings=[])
