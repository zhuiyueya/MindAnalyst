from __future__ import annotations

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.models.models import Segment


class SegmentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def has_any_for_content(self, content_id: str) -> bool:
        stmt = select(Segment.id).where(Segment.content_id == content_id).limit(1)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def list_for_content(self, content_id: str) -> list[Segment]:
        stmt = select(Segment).where(Segment.content_id == content_id).order_by(Segment.segment_index)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def delete_for_content(self, content_id: str) -> None:
        await self.session.execute(delete(Segment).where(Segment.content_id == content_id))
