
from typing import List, Optional
from src.adapters.llm.service import LLMService
from src.models.models import Segment
import logging

logger = logging.getLogger(__name__)

class RerankService:
    def __init__(self):
        self.llm = LLMService()

    async def rerank(self, query: str, segments: List[Segment], top_k: int = 5, content_type: Optional[str] = None) -> List[Segment]:
        """
        Rerank segments using LLM
        """
        if not segments:
            return []
            
        doc_texts = [s.text for s in segments]
        top_indices = await self.llm.rerank(query, doc_texts, top_n=top_k, content_type=content_type)
        
        reranked_segments = [segments[i] for i in top_indices]
        return reranked_segments
