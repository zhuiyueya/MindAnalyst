import os
from typing import List, Dict, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from sqlalchemy import text
from src.models.models import Segment, ContentItem
from sentence_transformers import SentenceTransformer
import openai
from src.config.settings import settings

class ChatService:
    def __init__(self, session: AsyncSession):
        self.session = session
        # Use same embedding model
        if os.getenv("MOCK_EMBEDDING"):
             self.embedder = None
        else:
             self.embedder = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
        
        if settings.OPENAI_API_KEY:
            self.client = openai.AsyncOpenAI(
                api_key=settings.OPENAI_API_KEY,
                base_url=settings.OPENAI_BASE_URL
            )
        else:
            self.client = None

    async def retrieve(self, query: str, author_id: str = None, top_k: int = 5) -> List[Segment]:
        """Simple vector search"""
        if self.embedder:
            query_vec = self.embedder.encode(query).tolist()
        else:
            # Mock embedding vector
            # Must match DB dimension (768)
            query_vec = [0.1] * 768
            
        # pgvector l2_distance or cosine_distance
        # Note: SQLModel doesn't fully support pgvector syntax natively in select() yet easily,
        # so we might use raw SQL or session.exec with specific order_by
        
        # Using l2_distance (<->) operator
        # Join ContentItem to filter by author if needed
        stmt = select(Segment).join(ContentItem)
        
        if author_id:
            stmt = stmt.where(ContentItem.author_id == author_id)
            
        stmt = stmt.order_by(Segment.embedding.l2_distance(query_vec)).limit(top_k)
        result = await self.session.execute(stmt)
        segments = result.scalars().all()
        
        # Manually fetch content to avoid lazy load error in async
        for seg in segments:
            stmt_c = select(ContentItem).where(ContentItem.id == seg.content_id)
            res_c = await self.session.execute(stmt_c)
            seg.content = res_c.scalar_one()
            
        return segments

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
            # Load content to get title/url if needed (lazy loading usually works if session active)
            # For simplicity, we assume seg.content is loaded or we fetch it.
            # We explicitly fetch content to be safe
            # stmt = select(ContentItem).where(ContentItem.id == seg.content_id)
            # res = await self.session.execute(stmt)
            # content_item = res.scalar_one()
            
            # Format: [i] Title (00:00): Text
            start_sec = seg.start_time_ms // 1000
            time_str = f"{start_sec//60:02d}:{start_sec%60:02d}"
            
            context_str += f"[{i+1}] 时间戳 {time_str}: {seg.text}\n\n"
            
            citations.append({
                "index": i+1,
                "segment_id": seg.id,
                "text": seg.text,
                "start_time": start_sec,
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
        
        if self.client:
            try:
                response = await self.client.chat.completions.create(
                    # model="gpt-3.5-turbo", 
                    # Use a model likely available on SiliconFlow free/paid tier or standard
                    model="Qwen/Qwen2.5-7B-Instruct", 
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
