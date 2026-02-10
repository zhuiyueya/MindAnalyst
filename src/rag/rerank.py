
from typing import List, Optional
from src.adapters.llm.service import LLMService
from src.models.models import RagIndexItem
import logging

logger = logging.getLogger(__name__)

class RerankService:
    def __init__(self):
        self.llm = LLMService()

    async def rerank(self, query: str, items: List[RagIndexItem], top_k: int = 5, content_type: Optional[str] = None) -> List[RagIndexItem]:
        """
        Rerank recalled items using LLM
        """
        if not items:
            return []
            
        doc_texts: List[str] = []
        for it in items:
            if getattr(it, "text_for_embedding", None):
                doc_texts.append(str(it.text_for_embedding))
            else:
                doc_texts.append(str(it.text_raw or ""))
        top_indices = await self.llm.rerank(query, doc_texts, top_n=top_k, content_type=content_type)

        if not top_indices:
            logger.info("Rerank returned empty indices; fallback to original order top_k=%s", top_k)
            return items[:top_k]

        reranked_items = [items[i] for i in top_indices if isinstance(i, int) and 0 <= i < len(items)]
        if not reranked_items:
            logger.info("Rerank returned only invalid indices=%s; fallback to original order top_k=%s", top_indices, top_k)
            return items[:top_k]

        return reranked_items
