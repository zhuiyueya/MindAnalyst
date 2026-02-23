from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.results import ChatResult
from src.rag.engine import RAGEngine


class ChatService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def chat(self, query: str, author_id: str | None) -> ChatResult:
        engine = RAGEngine(self.session)
        data = await engine.chat(query, author_id=author_id)
        return ChatResult(answer=str(data.get("answer") or ""), citations=list(data.get("citations") or []))
