from __future__ import annotations

from typing import Optional

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.models.models import LLMCallLog


class LlmCallLogRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list(
        self,
        *,
        task_type: Optional[str],
        content_type: Optional[str],
        profile_key: Optional[str],
        status: Optional[str],
        model: Optional[str],
        start_time,
        end_time,
        limit: int,
        offset: int,
    ) -> dict[str, object]:
        filters = []
        if task_type:
            filters.append(LLMCallLog.task_type == task_type)
        if content_type:
            filters.append(LLMCallLog.content_type == content_type)
        if profile_key:
            filters.append(LLMCallLog.profile_key == profile_key)
        if status:
            filters.append(LLMCallLog.status == status)
        if model:
            filters.append(LLMCallLog.model == model)
        if start_time:
            filters.append(LLMCallLog.created_at >= start_time)
        if end_time:
            filters.append(LLMCallLog.created_at <= end_time)

        count_stmt = select(func.count()).select_from(LLMCallLog)
        if filters:
            count_stmt = count_stmt.where(*filters)
        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = select(LLMCallLog).order_by(LLMCallLog.created_at.desc())
        if filters:
            stmt = stmt.where(*filters)
        stmt = stmt.offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        logs = list(result.scalars().all())

        return {
            "items": [log.model_dump() for log in logs],
            "total": total,
            "limit": limit,
            "offset": offset,
        }
