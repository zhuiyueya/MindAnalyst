from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas.common import LlmCallsListResponse
from src.database.db import get_session
from src.services.llm_call_service import LlmCallService

router = APIRouter()


@router.get("/api/v1/llm_calls", response_model=LlmCallsListResponse)
async def list_llm_calls(
    session: AsyncSession = Depends(get_session),
    task_type: Optional[str] = None,
    content_type: Optional[str] = None,
    profile_key: Optional[str] = None,
    status: Optional[str] = None,
    model: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> LlmCallsListResponse:
    result = await LlmCallService(session).list_llm_calls(
        task_type=task_type,
        content_type=content_type,
        profile_key=profile_key,
        status=status,
        model=model,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
        offset=offset,
    )

    return LlmCallsListResponse(items=result.items, total=result.total, limit=result.limit, offset=result.offset)
