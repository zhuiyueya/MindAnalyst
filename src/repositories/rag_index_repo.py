from __future__ import annotations

from typing import Any, List, Optional, cast

from sqlalchemy import func, delete, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import col, select

from src.adapters.embedding.provider import embed_text
from src.models.models import ContentItem, RagIndexItem, Summary
from src.rag.types import RagDoc


class RagIndexRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def delete_by_summary_id(self, summary_id: str) -> None:
        await self.session.execute(delete(RagIndexItem).where(col(RagIndexItem.summary_id) == summary_id))
        await self.session.commit()

    async def add_items(self, items: List[RagIndexItem]) -> None:
        for it in items:
            self.session.add(it)
        await self.session.commit()

    async def list_latest_structured_summaries_by_author(self, author_id: str) -> list[tuple[Summary, ContentItem]]:
        stmt = (
            select(Summary, ContentItem)
            .join(ContentItem, col(Summary.content_id) == col(ContentItem.id))
            .where(col(ContentItem.author_id) == author_id)
            .where(col(Summary.summary_type) == "structured")
            .order_by(desc(col(Summary.created_at)))
        )
        result = await self.session.execute(stmt)
        rows = result.tuples().all()
        return list(rows)

    async def hybrid_search(
        self,
        query: str,
        *,
        author_id: Optional[str] = None,
        source_type: str = "summary_chunk",
        tags: Optional[List[str]] = None,
        limit: int = 20,
        dense_limit: int = 40,
        sparse_limit: int = 40,
    ) -> List[RagDoc]:
        tags = tags or []
        tags = [str(x).strip() for x in tags if str(x).strip()]

        query_vec = embed_text(query)

        base = (
            select(RagIndexItem)
            .options(selectinload(cast(Any, RagIndexItem.content_item)))
            .join(ContentItem, col(RagIndexItem.content_id) == col(ContentItem.id))
        )
        base = base.where(col(RagIndexItem.source_type) == source_type)
        if author_id:
            base = base.where(col(RagIndexItem.author_id) == author_id)
        if tags:
            base = base.where(col(RagIndexItem.tag).in_(tags))

        dense_stmt = base.order_by(cast(Any, RagIndexItem.embedding).l2_distance(query_vec)).limit(max(limit, dense_limit))
        dense_res = await self.session.execute(dense_stmt)
        dense_items = list(dense_res.scalars().all())

        tsquery = func.plainto_tsquery("simple", query)
        sparse_stmt = base.where(col(RagIndexItem.tsv).op("@@")(tsquery))
        sparse_stmt = sparse_stmt.order_by(desc(func.ts_rank(col(RagIndexItem.tsv), tsquery))).limit(max(limit, sparse_limit))
        sparse_res = await self.session.execute(sparse_stmt)
        sparse_items = list(sparse_res.scalars().all())

        merged: list[RagIndexItem] = []
        seen: set[str] = set()
        for item in dense_items + sparse_items:
            item_id = str(getattr(item, "id", ""))
            if not item_id or item_id in seen:
                continue
            seen.add(item_id)
            merged.append(item)
            if len(merged) >= limit:
                break

        docs: list[RagDoc] = []
        for it in merged:
            content = getattr(it, "content_item", None)
            title = getattr(content, "title", None) if content else None
            url = getattr(content, "url", None) if content else None
            content_type_value = getattr(content, "content_type", None) if content else None

            text = str(it.text_raw or it.text_for_embedding or "")
            tag = str(it.tag).strip() if getattr(it, "tag", None) else None

            docs.append(
                RagDoc(
                    rag_id=str(it.id),
                    source_type=str(it.source_type),
                    summary_id=str(it.summary_id),
                    content_id=str(it.content_id),
                    title=str(title or "Unknown"),
                    url=str(url or ""),
                    tag=tag,
                    text=text,
                    content_type=str(content_type_value) if content_type_value else None,
                )
            )

        return docs
