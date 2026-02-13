from __future__ import annotations

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.models.models import Author


class AuthorRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_all(self) -> list[Author]:
        result = await self.session.execute(select(Author))
        return list(result.scalars().all())

    async def get(self, author_id: str) -> Optional[Author]:
        return await self.session.get(Author, author_id)
