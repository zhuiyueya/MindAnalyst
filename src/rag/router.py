import logging
import re
from typing import Any, Dict, List, Optional

from src.adapters.llm.service import LLMService

logger = logging.getLogger(__name__)


class RagRouter:
    def __init__(self):
        self.llm = LLMService()

    async def route(self, query: str, author_id: Optional[str] = None) -> Dict[str, Any]:
        """Return routing decision.

        Output schema:
        {
          "route": "author_report" | "summary_chunk" | "summary_short",
          "tags": ["实操", "观点" ...],
          "query": "..."   # optional rewritten query
        }
        """
        prompt = (
            "你是检索路由助手。根据用户问题，决定检索策略。\n"
            "可选 route: author_report / summary_chunk / summary_short\n"
            "规则：\n"
            "- 如果用户在问‘某作者是谁/核心思想/体系/理念/总结’，优先 author_report（需要 author_id 才可用）。\n"
            "- 如果用户在问‘怎么办/方法/步骤/建议/实操’，使用 summary_chunk，并优先 tags 包含 实操。\n"
            "- 如果用户在问‘观点/认知/金句/洞见/打破认知’，使用 summary_chunk，并 tags 包含 观点、金句（按需）。\n"
            "- 如果用户在问‘有没有聊过某话题/提到过XXX吗’，使用 summary_short。\n"
            "输出严格 JSON：{\"route\":..., \"tags\":[...], \"query\":...}。tags 可为空数组。query 可原样返回。"
        )

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
            data = await self.llm.classify_rag_intent(query=query, prompt=prompt)
        except Exception as e:
            logger.warning("RAG router failed, fallback to summary_chunk: %s", e)
            data = {"route": "summary_chunk", "tags": [], "query": query}

        route = data.get("route") if isinstance(data, dict) else None
        if route == "author_report" and not author_id:
            route = "summary_chunk"

        tags = data.get("tags") if isinstance(data, dict) else []
        if not isinstance(tags, list):
            tags = []
        tags = [str(x).strip() for x in tags if str(x).strip()]

        q = data.get("query") if isinstance(data, dict) else None
        q = q.strip() if isinstance(q, str) and q.strip() else query

        return {"route": route or "summary_chunk", "tags": tags, "query": q}
