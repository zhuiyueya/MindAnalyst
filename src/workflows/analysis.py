
import logging
from typing import List, Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from src.models.models import ContentItem, Segment, Summary, AuthorReport, Author
from src.adapters.llm.service import LLMService
from src.database.db import get_session

logger = logging.getLogger(__name__)

class AnalysisWorkflow:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.llm = LLMService()

    async def _resolve_author(self, content: ContentItem) -> Optional[Author]:
        if content.author:
            return content.author
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

        classified = await self.llm.classify_content_type(full_text)
        if classified:
            content.content_type = classified
            content.content_type_source = "classifier"
            self.session.add(content)
            await self.session.commit()
            return classified

        return "generic"

    def _extract_report_version(self, profile_key: Optional[str]) -> str:
        if not profile_key:
            return "v1"
        tail = profile_key.split("/")[-1]
        return tail if tail.startswith("v") else "v1"

    async def generate_content_summary(self, content: ContentItem, segments: List[Segment], existing_summary: Summary = None):
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
        
        if "error" in result:
            logger.warning(f"Summary generation failed for {content.title}: {result['error']}")
            return

        normalized = result.get("normalized") if isinstance(result, dict) else None
        if not normalized:
            normalized = result

        if existing_summary:
            logger.info(f"Updating existing summary for {content.title}")
            existing_summary.content = normalized.get("summary", "")
            existing_summary.json_data = result
            self.session.add(existing_summary)
        else:
            # Save to Summary table
            summary = Summary(
                content_id=content.id,
                summary_type="structured",
                content=normalized.get("summary", ""),
                json_data=result
            )
            self.session.add(summary)
            
        await self.session.commit()
        logger.info(f"Saved summary for {content.title}")

    async def generate_author_report(self, author_id: str):
        """
        Generate author-level report from existing summaries.
        """
        logger.info(f"Generating report for author {author_id}...")
        author = await self.session.get(Author, author_id)
        if not author:
            logger.warning("Author not found for report generation.")
            return

        stmt = select(Summary, ContentItem.content_type).join(ContentItem).where(ContentItem.author_id == author_id).order_by(Summary.created_at.desc())
        result = await self.session.execute(stmt)
        rows = result.all()

        if not rows:
            logger.warning("No summaries found for author report.")
            return

        grouped: Dict[str, List[Summary]] = {}
        for summary, content_type in rows:
            key = content_type or "generic"
            grouped.setdefault(key, []).append(summary)

        if author.author_type:
            grouped = {author.author_type: [summary for summary, _ in rows]}

        for content_type, summaries in grouped.items():
            summary_data = [s.json_data for s in summaries if s.json_data]
            if not summary_data:
                continue

            result = await self.llm.generate_author_report(summary_data, content_type)
            if "error" in result:
                logger.warning(f"Report generation failed: {result['error']}")
                continue

            raw = result.get("raw") if isinstance(result, dict) else None
            report_markdown = raw.get("report_markdown", "") if isinstance(raw, dict) else ""
            report = AuthorReport(
                author_id=author_id,
                content_type=content_type,
                report_type="report.author",
                report_version=self._extract_report_version(result.get("profile") if isinstance(result, dict) else None),
                content=report_markdown,
                json_data=result if isinstance(result, dict) else {"raw": raw}
            )
            self.session.add(report)

        await self.session.commit()
        logger.info(f"Saved author reports for {author_id}")
