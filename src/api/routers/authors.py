from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas.common import AuthorDetailResponse, AuthorsListResponse, AuthorTypeSetResponse, TaskStartedResponse
from src.api.schemas.types import AuthorTypeRequest
from src.database.db import get_session
from src.services.author_service import AuthorService
from src.services.analysis_tasks import (
    run_generate_author_categories,
    run_generate_category_reports,
    run_generate_short_summaries,
    run_regenerate_report,
    run_reprocess_author_asr,
    run_resummarize_author,
    run_resummarize_author_pending,
)
from src.services.type_service import TypeService

router = APIRouter()


@router.get("/api/v1/authors", response_model=AuthorsListResponse)
async def list_authors(session: AsyncSession = Depends(get_session)) -> AuthorsListResponse:
    result = await AuthorService(session).list_authors()
    return AuthorsListResponse(root=result.items)


@router.get("/api/v1/authors/{author_id}", response_model=AuthorDetailResponse)
async def get_author(author_id: str, session: AsyncSession = Depends(get_session)) -> AuthorDetailResponse:
    result = await AuthorService(session).get_author_detail(author_id)
    return AuthorDetailResponse(
        author=result.author,
        latest_report=result.latest_report,
        reports=result.reports,
        reports_by_type=result.reports_by_type,
        category_reports_by_type=result.category_reports_by_type,
        author_status=result.author_status,
    )


@router.post("/api/v1/authors/{author_id}/generate_category_reports", response_model=TaskStartedResponse)
async def generate_category_reports(
    author_id: str,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
) -> TaskStartedResponse:
    background_tasks.add_task(run_generate_category_reports, author_id)
    return TaskStartedResponse(status="started", message="Category reports generation started")


@router.post("/api/v1/authors/{author_id}/set_type", response_model=AuthorTypeSetResponse)
async def set_author_type(
    author_id: str,
    req: AuthorTypeRequest,
    session: AsyncSession = Depends(get_session),
) -> AuthorTypeSetResponse:
    result = await TypeService(session).set_author_type(author_id, req.author_type)
    return AuthorTypeSetResponse(author_id=result.author_id, author_type=result.author_type)


@router.post("/api/v1/authors/{author_id}/regenerate_report", response_model=TaskStartedResponse)
async def regenerate_author_report(
    author_id: str,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
) -> TaskStartedResponse:
    background_tasks.add_task(run_regenerate_report, author_id)
    return TaskStartedResponse(status="started", message="Report regeneration started")


@router.post("/api/v1/authors/{author_id}/resummarize_all", response_model=TaskStartedResponse)
async def resummarize_all_videos(
    author_id: str,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    include_fallback: bool = False,
) -> TaskStartedResponse:
    background_tasks.add_task(run_resummarize_author, author_id, include_fallback)
    return TaskStartedResponse(status="started", message="Batch summarization started")


@router.post("/api/v1/authors/{author_id}/resummarize_pending", response_model=TaskStartedResponse)
async def resummarize_pending_videos(
    author_id: str,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
) -> TaskStartedResponse:
    background_tasks.add_task(run_resummarize_author_pending, author_id)
    return TaskStartedResponse(status="started", message="Pending summarization started")


@router.post("/api/v1/authors/{author_id}/compress_short_summaries", response_model=TaskStartedResponse)
async def compress_short_summaries(
    author_id: str,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
) -> TaskStartedResponse:
    background_tasks.add_task(run_generate_short_summaries, author_id)
    return TaskStartedResponse(status="started", message="Short summary compression started")


@router.post("/api/v1/authors/{author_id}/generate_categories", response_model=TaskStartedResponse)
async def generate_author_categories(
    author_id: str,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
) -> TaskStartedResponse:
    background_tasks.add_task(run_generate_author_categories, author_id)
    return TaskStartedResponse(status="started", message="Category analysis started")


@router.post("/api/v1/authors/{author_id}/reprocess_asr", response_model=TaskStartedResponse)
async def reprocess_author_asr(
    author_id: str,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
) -> TaskStartedResponse:
    background_tasks.add_task(run_reprocess_author_asr, author_id)
    return TaskStartedResponse(status="started", message="Transcript reprocess started")
