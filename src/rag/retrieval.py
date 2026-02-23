from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.repositories.rag_index_repo import RagIndexRepository
from src.rag.types import RagDoc


class RetrievalService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = RagIndexRepository(session)

    async def retrieve_candidates(
        self,
        query: str,
        author_id: Optional[str] = None,
        source_type: str = "summary_chunk",
        tags: Optional[List[str]] = None,
        limit: int = 20,
        dense_limit: int = 40,
        sparse_limit: int = 40,
    ) -> List[RagDoc]:
        return await self.repo.hybrid_search(
            query,
            author_id=author_id,
            source_type=source_type,
            tags=tags,
            limit=limit,
            dense_limit=dense_limit,
            sparse_limit=sparse_limit,
        )
