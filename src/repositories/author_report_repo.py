from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.models.models import AuthorReport


class AuthorReportRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_by_author_desc(self, author_id: str) -> list[AuthorReport]:
        stmt = select(AuthorReport).where(AuthorReport.author_id == author_id).order_by(AuthorReport.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
