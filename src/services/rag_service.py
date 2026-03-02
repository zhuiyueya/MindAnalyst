from __future__ import annotations

import logging

from fastapi import BackgroundTasks

from src.database.db import get_session
from src.domain.results import RagReindexResult
from src.rag.indexing import RagIndexingService
from src.repositories.author_repo import AuthorRepository

logger = logging.getLogger(__name__)


class RagService:
    def __init__(self, background_tasks: BackgroundTasks):
        self.background_tasks = background_tasks

    def start_reindex(self, author_id: str | None) -> RagReindexResult:
        if author_id:
            self.background_tasks.add_task(run_rag_reindex_author_task, author_id)
            return RagReindexResult(status="started", scope="author", author_id=author_id)
        self.background_tasks.add_task(run_rag_reindex_all_task)
        return RagReindexResult(status="started", scope="all", author_id=None)


async def run_rag_reindex_author_task(author_id: str) -> None:
    logger.info("Starting RAG reindex for author %s", author_id)
    async for session in get_session():
        try:
            indexer = RagIndexingService(session)
            result = await indexer.reindex_author(author_id)
            logger.info("RAG reindex done: %s", result)
        except Exception as e:
            logger.error("RAG reindex failed for author %s: %s", author_id, e)
        break


async def run_rag_reindex_all_task() -> None:
    logger.info("Starting RAG reindex for all authors")
    async for session in get_session():
        try:
            authors = await AuthorRepository(session).list_all()
            indexer = RagIndexingService(session)
            total_indexed = 0
            total_skipped = 0
            for idx, author in enumerate(authors, start=1):
                logger.info("RAG reindex progress: %s/%s author_id=%s", idx, len(authors), author.id)
                result = await indexer.reindex_author(author.id)
                total_indexed += int(result.get("indexed") or 0)
                total_skipped += int(result.get("skipped") or 0)
            logger.info(
                "RAG reindex all done: author_count=%s total_indexed=%s total_skipped=%s",
                len(authors),
                total_indexed,
                total_skipped,
            )
        except Exception as e:
            logger.error("RAG reindex all failed: %s", e)
        break
