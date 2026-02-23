from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas.chat import ChatRequest, ChatResponse
from src.database.db import get_session
from src.services.chat_service import ChatService

router = APIRouter()


@router.post("/api/v1/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, session: AsyncSession = Depends(get_session)) -> ChatResponse:
    result = await ChatService(session).chat(req.query, req.author_id)
    return ChatResponse(answer=result.answer, citations=result.citations)
