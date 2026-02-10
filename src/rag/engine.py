import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.adapters.llm.service import LLMService
from src.models.models import AuthorReport, ContentItem, RagIndexItem
from src.rag.retrieval import RetrievalService
from src.rag.rerank import RerankService
from src.rag.router import RagRouter

logger = logging.getLogger(__name__)

class RAGEngine:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.retrieval = RetrievalService(session)
        self.reranker = RerankService()
        self.llm = LLMService()
        self.router = RagRouter()

    def _resolve_content_type_from_items(self, items: List[RagIndexItem]) -> str:
        for it in items:
            content = getattr(it, "content_item", None)
            if content and getattr(content, "content_type", None):
                return content.content_type
        return "generic"

    async def _load_author_reports(self, author_id: str, limit: int = 5) -> List[AuthorReport]:
        stmt = (
            select(AuthorReport)
            .where(AuthorReport.author_id == author_id)
            .order_by(AuthorReport.created_at.desc())
            .limit(limit)
        )
        res = await self.session.execute(stmt)
        return res.scalars().all()

    async def retrieve(
        self,
        query: str,
        author_id: Optional[str] = None,
        source_type: str = "summary_chunk",
        tags: Optional[List[str]] = None,
        top_k: int = 10,
    ) -> List[RagIndexItem]:
        candidates = await self.retrieval.retrieve_candidates(
            query,
            author_id=author_id,
            source_type=source_type,
            tags=tags,
            limit=top_k * 2,
        )

        if not candidates:
            return []

        content_type = self._resolve_content_type_from_items(candidates)
        reranked = await self.reranker.rerank(query, candidates, top_k=top_k, content_type=content_type)
        return reranked

    def _build_item_context_and_citations(self, items: List[RagIndexItem]) -> tuple[str, List[Dict[str, Any]]]:
        context_parts: List[str] = []
        citations: List[Dict[str, Any]] = []

        for i, it in enumerate(items, start=1):
            content: Optional[ContentItem] = getattr(it, "content_item", None)
            title = content.title if content else "Unknown"
            url = content.url if content else ""
            tag = (it.tag or "").strip() if it.source_type == "summary_chunk" else ""

            prefix = f"[{i}]"
            if tag:
                prefix += f" [{tag}]"
            prefix += f" 《{title}》"

            context_text = it.text_raw or it.text_for_embedding or ""
            context_parts.append(f"{prefix}: {context_text}")

            citations.append(
                {
                    "index": i,
                    "rag_id": it.id,
                    "source_type": it.source_type,
                    "summary_id": it.summary_id,
                    "content_id": it.content_id,
                    "title": title,
                    "url": url,
                    "tag": tag or None,
                    "text": context_text,
                }
            )

        return "\n\n".join(context_parts).strip(), citations

    async def chat(self, query: str, author_id: str = None) -> Dict:
        """RAG Chat"""
        route_decision = await self.router.route(query, author_id=author_id)
        route = route_decision.get("route")
        tags = route_decision.get("tags") or []
        routed_query = route_decision.get("query") or query

        if route == "author_report" and author_id:
            reports = await self._load_author_reports(author_id, limit=10)
            if not reports:
                return {"answer": "未找到相关作者报告。", "citations": []}

            context_parts = []
            citations: List[Dict[str, Any]] = []
            for idx, rep in enumerate(reports, start=1):
                context_parts.append(f"[R{idx}] report_type={rep.report_type} version={rep.report_version}\n{rep.content}")
                citations.append(
                    {
                        "index": idx,
                        "report_id": rep.id,
                        "report_type": rep.report_type,
                        "created_at": rep.created_at.isoformat() if rep.created_at else None,
                    }
                )
            context_str = "\n\n".join(context_parts)
            answer = await self.llm.generate_rag_answer(query, context_str, content_type="generic")
            return {"answer": answer, "citations": citations}

        source_type = "summary_short" if route == "summary_short" else "summary_chunk"
        items = await self.retrieve(routed_query, author_id=author_id, source_type=source_type, tags=tags, top_k=10)

        if not items:
            return {"answer": "未找到相关内容。", "citations": []}

        context_str, citations = self._build_item_context_and_citations(items)
        content_type = self._resolve_content_type_from_items(items)
        answer = await self.llm.generate_rag_answer(query, context_str, content_type)

        return {"answer": answer, "citations": citations}
