import logging
from typing import Any, Dict, List, Optional, cast

from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.llm.service import LLMService
from src.services.llm_call_service import LlmCallService
from src.models.models import Author, ContentItem, Segment, Summary
from src.repositories.content_repo import ContentRepository
from src.repositories.segment_repo import SegmentRepository
from src.repositories.summary_repo import SummaryRepository

logger = logging.getLogger(__name__)


class AuthorSummaryService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.llm = LLMService()
        self.llm_calls = LlmCallService(session)
        self.contents = ContentRepository(session)
        self.segments = SegmentRepository(session)
        self.summaries = SummaryRepository(session)

    async def resummarize_video(self, content_id: str, include_fallback: bool = False) -> None:
        content = await self.contents.get(content_id)
        if not content:
            return

        segments = await self.segments.list_for_content(content_id)

        if not segments:
            logger.warning("No segments found for %s, cannot summarize.", content.title)
            return

        if content.content_quality == "summary" and not include_fallback:
            logger.info("Skipping %s (fallback transcript).", content.title)
            return

        existing_summary = await self.summaries.get_for_content(content_id)

        await self.generate_content_summary(content, segments, existing_summary=existing_summary)

    async def resummarize_author(self, author_id: str, include_fallback: bool = False) -> None:
        contents = await self.contents.list_by_author(author_id)

        logger.info("Re-summarizing %s videos for author %s", len(contents), author_id)

        for content in contents:
            segments = await self.segments.list_for_content(content.id)

            if not segments:
                logger.info("Skipping %s (no segments)", content.title)
                continue

            if content.content_quality == "summary" and not include_fallback:
                logger.info("Skipping %s (fallback transcript)", content.title)
                continue

            existing_summary = await self.summaries.get_for_content(content.id)

            await self.generate_content_summary(content, segments, existing_summary=existing_summary)

    async def resummarize_author_pending(self, author_id: str) -> None:
        contents = await self.contents.list_by_author(author_id)

        logger.info("Re-summarizing pending videos for author %s", author_id)

        for content in contents:
            if content.content_quality in {"summary", "missing"}:
                logger.info("Skipping %s (fallback or missing content)", content.title)
                continue

            segments = await self.segments.list_for_content(content.id)
            if not segments:
                logger.info("Skipping %s (no segments)", content.title)
                continue

            await self.generate_content_summary(content, segments)

    async def _resolve_author(self, content: ContentItem) -> Optional[Author]:
        if not content.author_id:
            return None
        return await self.session.get(Author, content.author_id)

    async def _resolve_content_type(self, content: ContentItem, full_text: str) -> str:
        author = await self._resolve_author(content)
        if author and author.author_type:
            if content.content_type != author.author_type or content.content_type_source != "author_inherit":
                content.content_type = author.author_type
                content.content_type_source = "author_inherit"
                self.session.add(content)
                await self.session.commit()
            return author.author_type

        if content.content_type:
            return content.content_type

        classified_res = await self.llm.classify_content_type(full_text)
        if classified_res.call:
            await self.llm_calls.record_call_safe(classified_res.call)
        if classified_res.content_type:
            content.content_type = classified_res.content_type
            content.content_type_source = "classifier"
            self.session.add(content)
            await self.session.commit()
            return classified_res.content_type

        return "generic"

    async def generate_content_summary(
        self,
        content: ContentItem,
        segments: List[Segment],
        existing_summary: Optional[Summary] = None,
    ):
        """
        Generate structured summary for a single content item using LLM.
        If existing_summary is provided, update it instead of creating new.
        """
        logger.info(f"Generating summary for {content.title}...")
        
        # Combine segment texts
        full_text = "\n".join([s.text for s in segments])
        
        content_type = await self._resolve_content_type(content, full_text)

        # Call LLM
        result = await self.llm.generate_summary(full_text, content_type)
        if result.call:
            await self.llm_calls.record_call_safe(result.call)
        if result.call and result.call.status == "error":
            logger.warning(f"Summary generation failed for {content.title}: {result.call.error_message}")
            return

        raw_text = str(result.raw_text or "")

        if existing_summary:
            logger.info(f"Updating existing summary for {content.title}")
            existing_summary.content = raw_text
            existing_summary.json_data = {"raw_text": raw_text, "blocks": [b.model_dump() for b in result.blocks], "profile": result.profile, "content_type": result.content_type}
            self.session.add(existing_summary)
        else:
            # Save to Summary table
            json_data = {"raw_text": raw_text, "blocks": [b.model_dump() for b in result.blocks], "profile": result.profile, "content_type": result.content_type}
            summary = Summary(
                content_id=content.id,
                summary_type="structured",
                content=raw_text,
                json_data=json_data
            )
            self.session.add(summary)
            
        await self.session.commit()
        logger.info(f"Saved summary for {content.title}")

    async def generate_short_summaries_for_author(self, author_id: str) -> Dict[str, Any]:
        logger.info("Generating short summaries for author %s", author_id)
        rows = await self.summaries.list_structured_with_content_by_author_desc(author_id)

        latest_by_content: Dict[str, tuple[Summary, ContentItem]] = {}
        for summary, content in rows:
            if summary.content_id and summary.content_id not in latest_by_content:
                latest_by_content[summary.content_id] = (summary, content)

        total = 0
        updated = 0
        skipped = 0
        for summary, content in latest_by_content.values():
            total += 1
            if not summary.content:
                skipped += 1
                continue
            try:
                result = await self.llm.generate_short_summary(summary.content, content.content_type)
                if result.call:
                    await self.llm_calls.record_call_safe(result.call)
                if result.call and result.call.status == "error":
                    skipped += 1
                    continue

                raw_dict: Dict[str, Any] = result.raw if isinstance(result.raw, dict) else {"raw": result.raw}
                summary.short_json = raw_dict
                self.session.add(summary)
                await self.session.commit()
                updated += 1
            except Exception as exc:
                logger.error("Short summary failed for content %s: %s", summary.content_id, exc)
                skipped += 1

        return {"total": total, "updated": updated, "skipped": skipped}
