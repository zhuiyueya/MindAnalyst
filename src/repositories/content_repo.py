from __future__ import annotations

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.models.models import ContentItem


class ContentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_by_author(self, author_id: str) -> list[ContentItem]:
        stmt = select(ContentItem).where(ContentItem.author_id == author_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_author_ordered(self, author_id: str) -> list[ContentItem]:
        stmt = select(ContentItem).where(ContentItem.author_id == author_id).order_by(ContentItem.published_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id_or_external_id(self, video_id: str) -> Optional[ContentItem]:
        video = await self.session.get(ContentItem, video_id)
        if video:
            return video
        stmt = select(ContentItem).where(ContentItem.external_id == video_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
