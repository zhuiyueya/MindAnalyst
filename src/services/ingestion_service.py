from __future__ import annotations

from dataclasses import dataclass
import logging

from fastapi import BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.db import get_session
from src.repositories.content_repo import ContentRepository
from src.repositories.segment_repo import SegmentRepository
from src.workflows.ingestion import IngestionWorkflow

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class IngestStartResult:
    status: str
    message: str


class IngestionService:
    def __init__(self, background_tasks: BackgroundTasks):
        self.background_tasks = background_tasks

    def start_ingest(self, author_id: str, limit: int, use_browser: bool) -> IngestStartResult:
        normalized = author_id
        if "bilibili.com" not in normalized and "http" not in normalized:
            normalized = f"https://space.bilibili.com/{normalized}"

        self.background_tasks.add_task(run_ingestion_task, normalized, limit, use_browser)
        return IngestStartResult(status="started", message=f"Ingestion started for {normalized}")


class IngestionOrchestrationService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.workflow = IngestionWorkflow(session)
        self.contents = ContentRepository(session)
        self.segments = SegmentRepository(session)

    async def reprocess_video_asr(self, content_id: str) -> None:
        content = await self.contents.get(content_id)
        if not content:
            return

        await self.segments.delete_for_content(content_id)
        await self.session.commit()
        await self.workflow.process_content(content, reuse_audio_only=True)

    async def reprocess_author_asr(self, author_id: str) -> None:
        contents = await self.contents.list_by_author(author_id)
        logger.info("Reprocessing transcripts for %s videos (author %s)", len(contents), author_id)

        for content in contents:
            has_segment = await self.segments.has_any_for_content(content.id)
            needs_reprocess = (not has_segment) or content.content_quality == "summary"

            if not needs_reprocess:
                continue

            await self.segments.delete_for_content(content.id)
            await self.session.commit()
            await self.workflow.process_content(content, reuse_audio_only=True)


async def run_ingestion_task(mid_or_url: str, limit: int, use_browser: bool) -> None:
    logger.info("Starting background processing for author %s", mid_or_url)
    async for session in get_session():
        workflow = IngestionWorkflow(session)
        try:
            if use_browser:
                await workflow.ingest_from_browser(mid_or_url, limit=limit)
            else:
                await workflow.ingest_author(mid_or_url, limit=limit)
        except Exception as e:
            logger.error("Ingestion failed: %s", e)
        break
