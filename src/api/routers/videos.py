from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas.common import (
    PlaybackUrlResponse,
    TaskStartedResponse,
    VideoDetailResponse,
    VideosListResponse,
    VideoTypeSetResponse,
)
from src.api.schemas.types import ContentTypeRequest
from src.database.db import get_session
from src.services.analysis_tasks import (
    run_reprocess_video_asr,
    run_resummarize_video,
)
from src.services.type_service import TypeService
from src.services.video_service import VideoService

router = APIRouter()


@router.get("/api/v1/authors/{author_id}/videos", response_model=VideosListResponse)
async def get_author_videos(author_id: str, session: AsyncSession = Depends(get_session)) -> VideosListResponse:
    result = await VideoService(session).list_author_videos(author_id)
    return VideosListResponse(root=result.items)


@router.get("/api/v1/videos/{video_id}", response_model=VideoDetailResponse)
async def get_video_detail(video_id: str, session: AsyncSession = Depends(get_session)) -> VideoDetailResponse:
    result = await VideoService(session).get_video_detail(video_id)
    return VideoDetailResponse(video=result.video, summary=result.summary, segments=result.segments)


@router.get("/api/v1/videos/{video_id}/playback", response_model=PlaybackUrlResponse)
async def get_video_playback_url(video_id: str, session: AsyncSession = Depends(get_session)) -> PlaybackUrlResponse:
    result = await VideoService(session).get_playback_url(video_id)
    return PlaybackUrlResponse(url=result.url)


@router.post("/api/v1/videos/{video_id}/set_type", response_model=VideoTypeSetResponse)
async def set_video_type(
    video_id: str,
    req: ContentTypeRequest,
    session: AsyncSession = Depends(get_session),
) -> VideoTypeSetResponse:
    result = await TypeService(session).set_video_type(video_id, req.content_type)
    return VideoTypeSetResponse(video=result.video)


@router.post("/api/v1/videos/{video_id}/resummarize", response_model=TaskStartedResponse)
async def resummarize_video(
    video_id: str,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    include_fallback: bool = False,
) -> TaskStartedResponse:
    result = await VideoService(session).get_video_detail(video_id)
    content_id = str(result.video["id"])
    background_tasks.add_task(run_resummarize_video, content_id, include_fallback)
    return TaskStartedResponse(status="started", message="Video summarization started")


@router.post("/api/v1/videos/{video_id}/reprocess_asr", response_model=TaskStartedResponse)
async def reprocess_video_asr(
    video_id: str,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
) -> TaskStartedResponse:
    result = await VideoService(session).get_video_detail(video_id)
    content_id = str(result.video["id"])
    background_tasks.add_task(run_reprocess_video_asr, content_id)
    return TaskStartedResponse(status="started", message="Transcript reprocess started")
