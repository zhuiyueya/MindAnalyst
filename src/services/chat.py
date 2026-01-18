import os
from src.services.llm import LLMService
from src.models.models import Segment, ContentItem, Summary
from typing import List, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from sentence_transformers import SentenceTransformer
import os

class ChatService:
    def __init__(self, session: AsyncSession):
        self.session = session
        # Use same embedding model
        if os.getenv("MOCK_EMBEDDING"):
             self.embedder = None
        else:
             self.embedder = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
        
        self.llm = LLMService()

    async def retrieve(self, query: str, author_id: str = None, top_k: int = 10) -> List[Segment]:
        """
        Two-stage retrieval:
        1. Hybrid Search (Content-level Summary + Segment Vector)
        2. Rerank
        """
        # 1. Vector Search on Segments (Recall)
        if self.embedder:
            query_vec = self.embedder.encode(query).tolist()
        else:
            query_vec = [0.1] * 384
            
        stmt = select(Segment).join(ContentItem)
        if author_id:
            stmt = stmt.where(ContentItem.author_id == author_id)
            
        # Recall more candidates for reranking (e.g. 20)
        stmt = stmt.order_by(Segment.embedding.l2_distance(query_vec)).limit(top_k * 2)
        result = await self.session.execute(stmt)
        segments = result.scalars().all()
        
        # Load content info
        for seg in segments:
            stmt_c = select(ContentItem).where(ContentItem.id == seg.content_id)
            res_c = await self.session.execute(stmt_c)
            seg.content = res_c.scalar_one()

        if not segments:
            return []

        # 2. Rerank
        doc_texts = [s.text for s in segments]
        top_indices = await self.llm.rerank(query, doc_texts, top_n=top_k)
        
        reranked_segments = [segments[i] for i in top_indices]
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
            
        # 3. Generate Answer
        system_prompt = """你是一个助手，请基于提供的视频片段回答用户问题。
回答要求：
1. 必须引用片段编号，例如 [1]。
2. 如果片段中没有答案，请诚实回答不知道。
3. 保持客观。
"""
        user_prompt = f"用户问题：{query}\n\n相关片段：\n{context_str}"
        
        if self.llm.client:
            try:
                response = await self.llm.client.chat.completions.create(
                    model=self.llm.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ]
                )
                answer = response.choices[0].message.content
            except Exception as e:
                answer = f"Error calling LLM: {e}"
        else:
            answer = f"【模拟回答】基于片段 [1]，作者提到了相关概念。\n(请配置 OPENAI_API_KEY 以启用真实 LLM 回答)"

        return {
            "answer": answer,
            "citations": citations
        }
