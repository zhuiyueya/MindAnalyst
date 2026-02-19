from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.utils import parse_datetime
from src.domain.results import LlmCallsPageResult
from src.repositories.llm_call_log_repo import LlmCallLogRepository


class LlmCallService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = LlmCallLogRepository(session)

    async def list_llm_calls(
        self,
        *,
        task_type: str | None,
        content_type: str | None,
        profile_key: str | None,
        status: str | None,
        model: str | None,
        start_time: str | None,
        end_time: str | None,
        limit: int,
        offset: int,
    ) -> LlmCallsPageResult:
        limit = max(1, min(limit, 200))
        offset = max(0, offset)

        start_dt = parse_datetime(start_time) if start_time else None
        end_dt = parse_datetime(end_time) if end_time else None

        data = await self.repo.list(
            task_type=task_type,
            content_type=content_type,
            profile_key=profile_key,
            status=status,
            model=model,
            start_time=start_dt,
            end_time=end_dt,
            limit=limit,
            offset=offset,
        )

        return LlmCallsPageResult(
            items=list(data.get("items") or []),
            total=int(data.get("total") or 0),
            limit=int(data.get("limit") or limit),
            offset=int(data.get("offset") or offset),
        )
