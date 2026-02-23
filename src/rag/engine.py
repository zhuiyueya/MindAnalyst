import logging
from typing import Any, List, Optional, cast

from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.llm.service import LLMService
from src.rag.context_builder import build_context_and_citations
from src.rag.retrieval import RetrievalService
from src.rag.rerank import RerankService
from src.rag.router import RagRouter
from src.rag.types import Citation, RagChatResponse, RagDoc
from src.repositories.author_report_repo import AuthorReportRepository

logger = logging.getLogger(__name__)

class RAGEngine:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.retrieval = RetrievalService(session)
        self.reranker = RerankService()
        self.llm = LLMService()
        self.router = RagRouter()
        self.reports = AuthorReportRepository(session)

    def _resolve_content_type_from_docs(self, docs: List[RagDoc]) -> str:
        for d in docs:
            if d.content_type:
                return d.content_type
        return "generic"

    async def retrieve(
        self,
        query: str,
        author_id: Optional[str] = None,
        source_type: str = "summary_chunk",
        tags: Optional[List[str]] = None,
        top_k: int = 10,
    ) -> List[RagDoc]:
        candidates = await self.retrieval.retrieve_candidates(
            query,
            author_id=author_id,
            source_type=source_type,
            tags=tags,
            limit=top_k * 2,
        )

        if not candidates:
            return []

        content_type = self._resolve_content_type_from_docs(candidates)
        reranked = await self.reranker.rerank(query, candidates, top_k=top_k, content_type=content_type)
        return reranked

    async def chat(self, query: str, author_id: Optional[str] = None) -> RagChatResponse:
        """RAG Chat"""
        route_decision = await self.router.route(query, author_id=author_id)
        route_raw = route_decision.get("route")
        route: Optional[str] = route_raw if isinstance(route_raw, str) and route_raw else None

        tags_raw = route_decision.get("tags")
        if isinstance(tags_raw, list):
            tags: list[str] = []
            for t in cast(list[Any], tags_raw):
                if isinstance(t, str) and t:
                    tags.append(t)
        else:
            tags = []

        routed_query_raw = route_decision.get("query")
        routed_query: str = routed_query_raw if isinstance(routed_query_raw, str) and routed_query_raw else query

        if route == "author_report" and author_id:
            reports = await self.reports.list_by_author_desc(author_id, limit=10)
            if not reports:
                return RagChatResponse(answer="未找到相关作者报告。", citations=[])

            context_parts: List[str] = []
            citations: List[Citation] = []
            for idx, rep in enumerate(reports, start=1):
                context_parts.append(f"[R{idx}] report_type={rep.report_type} version={rep.report_version}\n{rep.content}")
                citations.append(
                    Citation(
                        index=idx,
                        report_id=str(rep.id),
                        report_type=str(rep.report_type),
                        created_at=rep.created_at,
                    )
                )
            context_str = "\n\n".join(context_parts)
            answer = await self.llm.generate_rag_answer(query, context_str, content_type="generic")
            return RagChatResponse(answer=answer, citations=citations)

        source_type = "summary_short" if route == "summary_short" else "summary_chunk"
        items = await self.retrieve(routed_query, author_id=author_id, source_type=source_type, tags=tags, top_k=10)

        if not items:
            return RagChatResponse(answer="未找到相关内容。", citations=[])

        context_str, citations = build_context_and_citations(items)
        content_type = self._resolve_content_type_from_docs(items)
        answer = await self.llm.generate_rag_answer(query, context_str, content_type)

        return RagChatResponse(answer=answer, citations=citations)
