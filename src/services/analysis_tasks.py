from __future__ import annotations

import logging

from sqlalchemy import delete
from sqlmodel import select

from src.database.db import get_session
from src.models.models import ContentItem, Segment, Summary
from src.workflows.analysis import AnalysisWorkflow
from src.workflows.ingestion import IngestionWorkflow

logger = logging.getLogger(__name__)


async def run_regenerate_report(author_id: str) -> None:
    async for session in get_session():
        analysis = AnalysisWorkflow(session)
        try:
            await analysis.generate_author_report(author_id)
        except Exception as e:
            logger.error("Report regeneration failed: %s", e)
        break


async def run_resummarize_video(content_id: str, include_fallback: bool = False) -> None:
    async for session in get_session():
        analysis = AnalysisWorkflow(session)
        try:
            content = await session.get(ContentItem, content_id)
            if not content:
                return

            stmt = select(Segment).where(Segment.content_id == content_id).order_by(Segment.segment_index)
            res = await session.execute(stmt)
            segments = res.scalars().all()

            if not segments:
                logger.warning("No segments found for %s, cannot summarize.", content.title)
                return

            if content.content_quality == "summary" and not include_fallback:
                logger.info("Skipping %s (fallback transcript).", content.title)
                return

            stmt_sum = select(Summary).where(Summary.content_id == content_id)
            res_sum = await session.execute(stmt_sum)
            existing_summary = res_sum.scalar_one_or_none()

            await analysis.generate_content_summary(content, segments, existing_summary=existing_summary)
        except Exception as e:
            logger.error("Video summarization failed: %s", e)
        break


async def run_resummarize_author(author_id: str, include_fallback: bool = False) -> None:
    async for session in get_session():
        analysis = AnalysisWorkflow(session)
        try:
            stmt = select(ContentItem).where(ContentItem.author_id == author_id)
            res = await session.execute(stmt)
            contents = res.scalars().all()

            logger.info("Re-summarizing %s videos for author %s", len(contents), author_id)

            for content in contents:
                stmt_seg = select(Segment).where(Segment.content_id == content.id).order_by(Segment.segment_index)
                res_seg = await session.execute(stmt_seg)
                segments = res_seg.scalars().all()

                if not segments:
                    logger.info("Skipping %s (no segments)", content.title)
                    continue

                if content.content_quality == "summary" and not include_fallback:
                    logger.info("Skipping %s (fallback transcript)", content.title)
                    continue

                stmt_sum = select(Summary).where(Summary.content_id == content.id)
                res_sum = await session.execute(stmt_sum)
                existing_summary = res_sum.scalar_one_or_none()

                await analysis.generate_content_summary(content, segments, existing_summary=existing_summary)
        except Exception as e:
            logger.error("Batch summarization failed: %s", e)
        break


async def run_resummarize_author_pending(author_id: str) -> None:
    async for session in get_session():
        analysis = AnalysisWorkflow(session)
        try:
            stmt = select(ContentItem).where(ContentItem.author_id == author_id)
            res = await session.execute(stmt)
            contents = res.scalars().all()

            logger.info("Re-summarizing pending videos for author %s", author_id)

            for content in contents:
                if content.content_quality in {"summary", "missing"}:
                    logger.info("Skipping %s (fallback or missing content)", content.title)
                    continue

                stmt_sum = select(Summary.id).where(Summary.content_id == content.id).limit(1)
                res_sum = await session.execute(stmt_sum)
                has_summary = res_sum.scalar_one_or_none() is not None
                if has_summary:
                    logger.info("Skipping %s (summary already exists)", content.title)
                    continue

                stmt_seg = select(Segment).where(Segment.content_id == content.id).order_by(Segment.segment_index)
                res_seg = await session.execute(stmt_seg)
                segments = res_seg.scalars().all()
                if not segments:
                    logger.info("Skipping %s (no segments)", content.title)
                    continue

                await analysis.generate_content_summary(content, segments)
        except Exception as e:
            logger.error("Pending summarization failed: %s", e)
        break


async def run_generate_short_summaries(author_id: str) -> None:
    async for session in get_session():
        analysis = AnalysisWorkflow(session)
        try:
            await analysis.generate_short_summaries_for_author(author_id)
        except Exception as e:
            logger.error("Short summary compression failed: %s", e)
        break


async def run_generate_author_categories(author_id: str) -> None:
    async for session in get_session():
        analysis = AnalysisWorkflow(session)
        try:
            await analysis.generate_author_categories_and_tag(author_id)
        except Exception as e:
            logger.error("Category generation failed: %s", e)
        break


async def run_generate_category_reports(author_id: str) -> None:
    async for session in get_session():
        analysis = AnalysisWorkflow(session)
        try:
            await analysis.generate_category_reports_for_author(author_id)
        except Exception as e:
            logger.error("Category report generation failed: %s", e)
        break


async def run_reprocess_video_asr(content_id: str) -> None:
    async for session in get_session():
        workflow = IngestionWorkflow(session)
        try:
            content = await session.get(ContentItem, content_id)
            if not content:
                return

            await session.execute(delete(Segment).where(Segment.content_id == content_id))
            await session.commit()
            await workflow.process_content(content, reuse_audio_only=True)
        except Exception as e:
            logger.error("Transcript reprocess failed: %s", e)
        break


async def run_reprocess_author_asr(author_id: str) -> None:
    async for session in get_session():
        workflow = IngestionWorkflow(session)
        try:
            stmt = select(ContentItem).where(ContentItem.author_id == author_id)
            res = await session.execute(stmt)
            contents = res.scalars().all()
            logger.info("Reprocessing transcripts for %s videos (author %s)", len(contents), author_id)

            for content in contents:
                stmt_seg = select(Segment.id).where(Segment.content_id == content.id).limit(1)
                res_seg = await session.execute(stmt_seg)
                has_segment = res_seg.scalar_one_or_none() is not None
                needs_reprocess = (not has_segment) or content.content_quality == "summary"

                if not needs_reprocess:
                    continue

                await session.execute(delete(Segment).where(Segment.content_id == content.id))
                await session.commit()
                await workflow.process_content(content, reuse_audio_only=True)
        except Exception as e:
            logger.error("Transcript reprocess failed: %s", e)
        break
