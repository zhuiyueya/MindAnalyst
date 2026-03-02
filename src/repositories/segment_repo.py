from __future__ import annotations

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from src.models.models import Segment


class SegmentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def has_any_for_content(self, content_id: str) -> bool:
        stmt = select(col(Segment.id)).where(col(Segment.content_id) == content_id).limit(1)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def list_for_content(self, content_id: str) -> list[Segment]:
        stmt = select(Segment).where(col(Segment.content_id) == content_id).order_by(col(Segment.segment_index))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_contents_grouped(self, content_ids: list[str]) -> dict[str, list[Segment]]:
        grouped: dict[str, list[Segment]] = {}
        if not content_ids:
            return grouped
        stmt = (
            select(Segment)
            .where(col(Segment.content_id).in_(content_ids))
            .order_by(col(Segment.content_id), col(Segment.segment_index))
        )
        result = await self.session.execute(stmt)
        for seg in result.scalars().all():
            if seg.content_id:
                grouped.setdefault(seg.content_id, []).append(seg)
        return grouped

    async def delete_for_content(self, content_id: str) -> None:
        await self.session.execute(delete(Segment).where(col(Segment.content_id) == content_id))
