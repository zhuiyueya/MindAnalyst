from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from src.rag.engine import RAGEngine


class ChatService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def chat(self, query: str, author_id: str | None) -> object:
        engine = RAGEngine(self.session)
        return await engine.chat(query, author_id=author_id)
