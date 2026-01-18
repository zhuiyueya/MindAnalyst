
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from src.models.models import Segment, ContentItem
from sentence_transformers import SentenceTransformer
import os
import logging

logger = logging.getLogger(__name__)

class RetrievalService:
    def __init__(self, session: AsyncSession):
        self.session = session
        # Use same embedding model
        if os.getenv("MOCK_EMBEDDING"):
             self.embedder = None
        else:
             try:
                 self.embedder = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
             except Exception as e:
                 logger.warning(f"Failed to load embedder: {e}")
                 self.embedder = None

    async def retrieve_candidates(self, query: str, author_id: str = None, limit: int = 20) -> List[Segment]:
        """
        Vector Search on Segments (Recall)
        """
        if self.embedder:
            query_vec = self.embedder.encode(query).tolist()
        else:
            query_vec = [0.1] * 384
            
        stmt = select(Segment).join(ContentItem)
        if author_id:
            stmt = stmt.where(ContentItem.author_id == author_id)
            
        stmt = stmt.order_by(Segment.embedding.l2_distance(query_vec)).limit(limit)
        result = await self.session.execute(stmt)
        segments = result.scalars().all()
        
        # Load content info
        for seg in segments:
            stmt_c = select(ContentItem).where(ContentItem.id == seg.content_id)
            res_c = await self.session.execute(stmt_c)
            seg.content = res_c.scalar_one()

        return segments
