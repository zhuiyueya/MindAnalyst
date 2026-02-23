from __future__ import annotations

from dataclasses import asdict

from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.results import ChatResult
from src.rag.engine import RAGEngine


class ChatService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def chat(self, query: str, author_id: str | None) -> ChatResult:
        engine = RAGEngine(self.session)
        resp = await engine.chat(query, author_id=author_id)
        citations = [asdict(c) for c in resp.citations]
        return ChatResult(answer=resp.answer, citations=citations)
