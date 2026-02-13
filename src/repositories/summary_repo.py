from __future__ import annotations

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.models.models import Summary


class SummaryRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def has_any_for_content(self, content_id: str) -> bool:
        stmt = select(Summary.id).where(Summary.content_id == content_id).limit(1)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def get_for_content(self, content_id: str) -> Optional[Summary]:
        stmt = select(Summary).where(Summary.content_id == content_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_latest_by_contents(self, content_ids: list[str]) -> dict[str, Summary]:
        latest: dict[str, Summary] = {}
        if not content_ids:
            return latest
        stmt_latest = (
            select(Summary)
            .where(Summary.content_id.in_(content_ids))
            .order_by(Summary.content_id, Summary.created_at.desc())
        )
        result = await self.session.execute(stmt_latest)
        for s in result.scalars().all():
            if s.content_id and s.content_id not in latest:
                latest[s.content_id] = s
        return latest
