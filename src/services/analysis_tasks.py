from __future__ import annotations

import logging

from src.database.db import get_session
from src.services.ingestion_service import IngestionOrchestrationService
from src.services.analysis.author_category_service import AuthorCategoryService
from src.services.analysis.author_report_service import AuthorReportService
from src.services.analysis.author_summary_service import AuthorSummaryService

logger = logging.getLogger(__name__)


async def run_regenerate_report(author_id: str) -> None:
    async for session in get_session():
        service = AuthorReportService(session)
        try:
            await service.generate_author_report(author_id)
        except Exception as e:
            logger.error("Report regeneration failed: %s", e)
        break


async def run_resummarize_video(content_id: str, include_fallback: bool = False) -> None:
    async for session in get_session():
        service = AuthorSummaryService(session)
        try:
            await service.resummarize_video(content_id, include_fallback=include_fallback)
        except Exception as e:
            logger.error("Video summarization failed: %s", e)
        break


async def run_resummarize_author(author_id: str, include_fallback: bool = False) -> None:
    async for session in get_session():
        service = AuthorSummaryService(session)
        try:
            await service.resummarize_author(author_id, include_fallback=include_fallback)
        except Exception as e:
            logger.error("Batch summarization failed: %s", e)
        break


async def run_resummarize_author_pending(author_id: str) -> None:
    async for session in get_session():
        service = AuthorSummaryService(session)
        try:
            await service.resummarize_author_pending(author_id)
        except Exception as e:
            logger.error("Pending summarization failed: %s", e)
        break


async def run_generate_short_summaries(author_id: str) -> None:
    async for session in get_session():
        service = AuthorSummaryService(session)
        try:
            await service.generate_short_summaries_for_author(author_id)
        except Exception as e:
            logger.error("Short summary compression failed: %s", e)
        break


async def run_generate_author_categories(author_id: str) -> None:
    async for session in get_session():
        service = AuthorCategoryService(session)
        try:
            await service.generate_author_categories_and_tag(author_id)
        except Exception as e:
            logger.error("Category generation failed: %s", e)
        break


async def run_generate_category_reports(author_id: str) -> None:
    async for session in get_session():
        service = AuthorReportService(session)
        try:
            await service.generate_category_reports_for_author(author_id)
        except Exception as e:
            logger.error("Category report generation failed: %s", e)
        break


async def run_reprocess_video_asr(content_id: str) -> None:
    async for session in get_session():
        service = IngestionOrchestrationService(session)
        try:
            await service.reprocess_video_asr(content_id)
        except Exception as e:
            logger.error("Transcript reprocess failed: %s", e)
        break


async def run_reprocess_author_asr(author_id: str) -> None:
    async for session in get_session():
        service = IngestionOrchestrationService(session)
        try:
            await service.reprocess_author_asr(author_id)
        except Exception as e:
            logger.error("Transcript reprocess failed: %s", e)
        break
