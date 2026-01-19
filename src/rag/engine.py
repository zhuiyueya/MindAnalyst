import os
from src.adapters.llm.service import LLMService
from src.models.models import Segment, ContentItem, Summary
from src.rag.retrieval import RetrievalService
from src.rag.rerank import RerankService
from typing import List, Dict
from sqlalchemy.ext.asyncio import AsyncSession
import logging

logger = logging.getLogger(__name__)

class RAGEngine:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.retrieval = RetrievalService(session)
        self.reranker = RerankService()
        self.llm = LLMService()

    def _resolve_content_type(self, segments: List[Segment]) -> str:
        for seg in segments:
            if seg.content and seg.content.content_type:
                return seg.content.content_type
        return "generic"

    async def retrieve(self, query: str, author_id: str = None, top_k: int = 10) -> List[Segment]:
        """
        Two-stage retrieval:
        1. Hybrid Search (Content-level Summary + Segment Vector)
        2. Rerank
        """
        # 1. Recall
        # Recall more candidates for reranking (e.g. 20)
        candidates = await self.retrieval.retrieve_candidates(query, author_id, limit=top_k * 2)
        
        if not candidates:
            return []

        # 2. Rerank
        content_type = self._resolve_content_type(candidates)
        reranked_segments = await self.reranker.rerank(query, candidates, top_k=top_k, content_type=content_type)
        return reranked_segments

    async def chat(self, query: str, author_id: str = None) -> Dict:
        """RAG Chat"""
        # 1. Retrieve
        segments = await self.retrieve(query, author_id=author_id)
        
        if not segments:
            return {"answer": "未找到相关内容。", "citations": []}
            
        # 2. Assemble Context
        context_str = ""
        citations = []
        
        for i, seg in enumerate(segments):
            # Format: [i] Title (00:00): Text
            start_sec = seg.start_time_ms // 1000
            time_str = f"{start_sec//60:02d}:{start_sec%60:02d}"
            title = seg.content.title if seg.content else "Unknown"
            
            context_str += f"[{i+1}] 《{title}》时间戳 {time_str}: {seg.text}\n\n"
            
            citations.append({
                "index": i+1,
                "segment_id": seg.id,
                "text": seg.text,
                "start_time": start_sec,
                "title": title,
                "url": f"https://www.bilibili.com/video/{seg.content.external_id}?t={start_sec}" if seg.content else ""
            })
            
        content_type = self._resolve_content_type(segments)

        # 3. Generate Answer
        answer = await self.llm.generate_rag_answer(query, context_str, content_type)

        return {
            "answer": answer,
            "citations": citations
        }
