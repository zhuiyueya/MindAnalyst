from __future__ import annotations

from typing import Optional

from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from src.models.models import ContentItem, Summary


class SummaryRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def has_any_for_content(self, content_id: str) -> bool:
        stmt = select(col(Summary.id)).where(col(Summary.content_id) == content_id).limit(1)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def get_for_content(self, content_id: str) -> Optional[Summary]:
        stmt = select(Summary).where(col(Summary.content_id) == content_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_latest_by_contents(self, content_ids: list[str]) -> dict[str, Summary]:
        latest: dict[str, Summary] = {}
        if not content_ids:
            return latest
        stmt_latest = (
            select(Summary)
            .where(col(Summary.content_id).in_(content_ids))
            .order_by(col(Summary.content_id), desc(col(Summary.created_at)))
        )
        result = await self.session.execute(stmt_latest)
        for s in result.scalars().all():
            if s.content_id and s.content_id not in latest:
                latest[s.content_id] = s
        return latest

    async def list_structured_with_content_by_author_desc(self, author_id: str) -> list[tuple[Summary, ContentItem]]:
        stmt = (
            select(Summary, ContentItem)
            .join(ContentItem, col(Summary.content_id) == col(ContentItem.id))
            .where(ContentItem.author_id == author_id)
            .where(col(Summary.summary_type) == "structured")
            .order_by(desc(col(Summary.created_at)))
        )
        result = await self.session.execute(stmt)
        return [(row[0], row[1]) for row in result.all()]

    async def list_with_content_type_by_author_desc(self, author_id: str) -> list[tuple[Summary, Optional[str]]]:
        stmt = (
            select(Summary, ContentItem.content_type)
            .join(ContentItem, col(Summary.content_id) == col(ContentItem.id))
            .where(ContentItem.author_id == author_id)
            .order_by(desc(col(Summary.created_at)))
        )
        result = await self.session.execute(stmt)
        return [(row[0], row[1]) for row in result.all()]
