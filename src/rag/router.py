import logging
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
