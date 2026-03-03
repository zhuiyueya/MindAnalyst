import logging
import re
from typing import Any, Optional, cast

from src.adapters.llm.service import LLMService

logger = logging.getLogger(__name__)


class RagRouter:
    def __init__(self):
        self.llm = LLMService()

    async def route(self, query: str, author_id: Optional[str] = None) -> dict[str, Any]:
        """Return routing decision.

        Output schema:
        {
          "route": "author_report" | "summary_chunk" | "summary_short",
          "tags": ["实操", "观点" ...],
          "query": "..."   # optional rewritten query
        }
        """
        normalized = (query or "").strip()
        if normalized:
            # Explicit tag forcing syntax (frontend test UI)
            # Examples:
            # - tag:观点,金句 你的问题
            # - #tag=实操 如何...
            m = re.match(r"^\s*(?:#?tag\s*[:=]\s*)([^\s]+)\s*(.*)$", normalized, re.IGNORECASE)
            if m:
                tag_str = (m.group(1) or "").strip()
                rest_q = (m.group(2) or "").strip() or normalized
                forced_tags = [x.strip() for x in re.split(r"[,，]", tag_str) if x.strip()]
                return {"route": "summary_chunk", "tags": forced_tags, "query": rest_q}

            # Heuristic fallback for offline / no-LLM environments
            if author_id and any(k in normalized for k in ["是谁", "什么人", "核心思想", "核心观点", "体系", "理念", "总结"]):
                return {"route": "author_report", "tags": [], "query": normalized}
            if any(k in normalized for k in ["有没有", "是否", "提到", "聊过", "讲过"]):
                return {"route": "summary_short", "tags": [], "query": normalized}
            if any(k in normalized for k in ["怎么办", "怎么做", "方法", "步骤", "建议", "实操"]):
                return {"route": "summary_chunk", "tags": ["实操"], "query": normalized}
            if any(k in normalized for k in ["观点", "认知", "洞见", "金句", "打破"]):
                return {"route": "summary_chunk", "tags": ["观点", "金句"], "query": normalized}

        try:
            intent = await self.llm.classify_rag_intent(query=query)
        except Exception as e:
            logger.warning("RAG router failed, fallback to summary_chunk: %s", e)
            intent = None

        data: dict[str, Any] = intent.raw if intent is not None else {"route": "summary_chunk", "tags": [], "query": query}

        route = (intent.route if intent is not None else None) or None
        if route == "author_report" and not author_id:
            route = "summary_chunk"

        tags: list[str] = intent.tags if intent is not None else []
        q = intent.query if intent is not None else query

        return {"route": route or "summary_chunk", "tags": tags, "query": q}
