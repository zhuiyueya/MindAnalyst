from typing import List, Optional

import logging
import os

from sentence_transformers import SentenceTransformer
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from src.models.models import ContentItem, RagIndexItem

logger = logging.getLogger(__name__)


class RetrievalService:
    def __init__(self, session: AsyncSession):
        self.session = session
        if os.getenv("MOCK_EMBEDDING"):
            self.embedder = None
        else:
            try:
                self.embedder = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
            except Exception as e:
                logger.warning("Failed to load embedder: %s", e)
                self.embedder = None

    def _embed(self, text: str) -> List[float]:
        if self.embedder:
            return self.embedder.encode(text).tolist()
        return [0.1] * 384

    async def retrieve_candidates(
        self,
        query: str,
        author_id: Optional[str] = None,
        source_type: str = "summary_chunk",
        tags: Optional[List[str]] = None,
        limit: int = 20,
        dense_limit: int = 40,
        sparse_limit: int = 40,
    ) -> List[RagIndexItem]:
        """Hybrid recall against rag_index_item.

        - Dense: pgvector l2 distance on embedding
        - Sparse: to_tsvector('simple', text_raw) @@ plainto_tsquery('simple', query)
        """
        tags = tags or []
        tags = [str(x).strip() for x in tags if str(x).strip()]

        query_vec = self._embed(query)

        base = (
            select(RagIndexItem)
            .options(selectinload(RagIndexItem.content_item))
            .join(ContentItem, RagIndexItem.content_id == ContentItem.id)
        )
        base = base.where(RagIndexItem.source_type == source_type)
        if author_id:
            base = base.where(RagIndexItem.author_id == author_id)
        if tags:
            base = base.where(RagIndexItem.tag.in_(tags))

        dense_stmt = base.order_by(RagIndexItem.embedding.l2_distance(query_vec)).limit(max(limit, dense_limit))
        dense_res = await self.session.execute(dense_stmt)
        dense_items = dense_res.scalars().all()

        tsquery = func.plainto_tsquery("simple", query)
        sparse_stmt = base.where(RagIndexItem.tsv.op("@@")(tsquery))
        sparse_stmt = sparse_stmt.order_by(func.ts_rank(RagIndexItem.tsv, tsquery).desc()).limit(max(limit, sparse_limit))
        sparse_res = await self.session.execute(sparse_stmt)
        sparse_items = sparse_res.scalars().all()

        merged: List[RagIndexItem] = []
        seen = set()
        for item in dense_items + sparse_items:
            if item.id in seen:
                continue
            seen.add(item.id)
            merged.append(item)
            if len(merged) >= limit:
                break

        return merged
