from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.utils import compute_status_fields
from src.adapters.storage.service import StorageService
from src.domain.results import PlaybackUrlResult, VideoDetailResult, VideosListResult
from src.repositories.content_repo import ContentRepository
from src.repositories.segment_repo import SegmentRepository
from src.repositories.summary_repo import SummaryRepository


class VideoService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.contents = ContentRepository(session)
        self.segments = SegmentRepository(session)
        self.summaries = SummaryRepository(session)

    async def list_author_videos(self, author_id: str) -> VideosListResult:
        videos = await self.contents.list_by_author_ordered(author_id)
        video_ids = [str(v.id) for v in videos]
        latest_summary_by_content = await self.summaries.list_latest_by_contents(video_ids)

        video_list: list[dict[str, Any]] = []
        for v in videos:
            summary_obj = latest_summary_by_content.get(str(v.id))
            has_summary = summary_obj is not None
            has_segments = await self.segments.has_any_for_content(str(v.id))

            v_dict = v.model_dump()
            v_dict["has_summary"] = has_summary
            if summary_obj is not None:
                v_dict["video_category"] = summary_obj.video_category
                v_dict["short_json"] = summary_obj.short_json
            v_dict.update(compute_status_fields(v.content_quality, has_segments, has_summary))
            video_list.append(v_dict)

        return VideosListResult(items=video_list)

    async def get_video_detail(self, video_id: str) -> VideoDetailResult:
        video = await self.contents.get_by_id_or_external_id(video_id)
        if not video:
            raise HTTPException(status_code=404, detail="Video not found")

        summary = await self.summaries.get_for_content(str(video.id))
        segments = await self.segments.list_for_content(str(video.id))

        has_segments = len(segments) > 0
        has_summary = summary is not None

        video_data = video.model_dump()
        video_data.update(compute_status_fields(video.content_quality, has_segments, has_summary))

        return VideoDetailResult(
            video=video_data,
            summary=summary.model_dump() if summary else None,
            segments=[s.model_dump(exclude={"embedding"}) for s in segments],
        )

    async def get_playback_url(self, video_id: str) -> PlaybackUrlResult:
        video = await self.contents.get_by_id_or_external_id(video_id)
        if not video:
            raise HTTPException(status_code=404, detail="Video not found")

        storage = StorageService()
        ref = storage.find_first_by_prefix(video.external_id)
        if ref is None:
            raise HTTPException(status_code=404, detail="Media file not found in storage")

        url = storage.presign_get(ref).url
        return PlaybackUrlResult(url=url)
