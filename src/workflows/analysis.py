
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

    async def generate_content_summary(self, content: ContentItem, segments: List[Segment], existing_summary: Summary = None):
        """
        Generate structured summary for a single content item using LLM.
        If existing_summary is provided, update it instead of creating new.
        """
        logger.info(f"Generating summary for {content.title}...")
        
        # Combine segment texts
        full_text = "\n".join([s.text for s in segments])
        
        # Call LLM
        result = await self.llm.generate_summary(full_text)
        
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
        
        # Fetch recent summaries
        stmt = select(Summary).join(ContentItem).where(ContentItem.author_id == author_id).order_by(Summary.created_at.desc()).limit(50)
        result = await self.session.execute(stmt)
        summaries = result.scalars().all()
        
        if not summaries:
            logger.warning("No summaries found for author report.")
            return

        summary_data = [s.json_data for s in summaries if s.json_data]
        
        # Call LLM
        result = await self.llm.generate_author_report(summary_data)
        
        if "error" in result:
            logger.warning(f"Report generation failed: {result['error']}")
            return

        # Save to AuthorReport table
        report = AuthorReport(
            author_id=author_id,
            content=result.get("report_markdown", ""),
            json_data=result
        )
        self.session.add(report)
        await self.session.commit()
        logger.info(f"Saved author report for {author_id}")
