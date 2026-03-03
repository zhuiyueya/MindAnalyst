from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.utils import parse_datetime
from src.adapters.llm.types import LLMCallRecord
from src.domain.results import LlmCallsPageResult
from src.models.models import LLMCallLog
from src.repositories.llm_call_log_repo import LlmCallLogRepository


logger = logging.getLogger(__name__)


class LlmCallService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = LlmCallLogRepository(session)

    async def record_call_safe(self, record: LLMCallRecord) -> None:
        try:
            usage = record.usage.model_dump() if record.usage is not None else {}
            log = LLMCallLog(
                task_type=record.task_type,
                content_type=record.content_type,
                profile_key=record.profile_key,
                model=record.model,
                system_prompt=record.system_prompt,
                user_prompt=record.user_prompt,
                request_meta=record.request_meta,
                response_text=record.response_text,
                response_meta={
                    **(record.response_meta or {}),
                    **({"usage": usage} if usage else {}),
                    **({"parse_warnings": record.parse_warnings} if record.parse_warnings else {}),
                },
                prompt_tokens=usage.get("prompt_tokens"),
                completion_tokens=usage.get("completion_tokens"),
                total_tokens=usage.get("total_tokens"),
                status=record.status,
                error_message=record.error_message,
            )
            await self.repo.add(log)
        except Exception as exc:
            logger.warning("Failed to record LLM call log: %s", exc)
            return

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
