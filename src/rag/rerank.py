
import logging
from typing import List, Optional

from src.adapters.llm.service import LLMService
from src.rag.types import RagDoc

logger = logging.getLogger(__name__)


class RerankService:
    def __init__(self):
        self.llm = LLMService()

    async def rerank(
        self,
        query: str,
        docs: List[RagDoc],
        top_k: int = 5,
        content_type: Optional[str] = None,
    ) -> List[RagDoc]:
        """Rerank recalled docs using LLM."""

        if not docs:
            return []

        doc_texts: List[str] = [str(d.text or "") for d in docs]
        res = await self.llm.rerank(query, doc_texts, top_n=top_k, content_type=content_type)
        top_indices = res.indices

        if not top_indices:
            logger.info("Rerank returned empty indices; fallback to original order top_k=%s", top_k)
            return docs[:top_k]

        reranked = [docs[i] for i in top_indices if 0 <= i < len(docs)]
        if not reranked:
            logger.info("Rerank returned only invalid indices=%s; fallback to original order top_k=%s", top_indices, top_k)
            return docs[:top_k]

        return reranked
