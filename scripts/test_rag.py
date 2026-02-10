import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Optional

from sqlmodel import select


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.database.db import get_session, init_db
from src.models.models import Author
from src.rag.engine import RAGEngine
from src.rag.indexing import RagIndexingService

logger = logging.getLogger(__name__)


DEFAULT_QUERIES = [
    "浩浩宽是谁？他的核心思想是什么？",
    "被领导穿小鞋了怎么办？",
    "在关于钱这块有什么打破现有认知的？",
    "他有没有聊过养猫？",
]


async def _pick_author_id(author_id: Optional[str]) -> Optional[str]:
    if author_id:
        return author_id

    async for session in get_session():
        res = await session.execute(select(Author).order_by(Author.created_at.asc()).limit(1))
        author = res.scalar_one_or_none()
        return author.id if author else None

    return None


async def main() -> None:
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser()
    parser.add_argument("--author-id", default=None)
    parser.add_argument("--no-reindex", action="store_true")
    parser.add_argument("--query", action="append", default=[])
    args = parser.parse_args()

    await init_db()

    author_id = await _pick_author_id(args.author_id)
    if not author_id:
        raise SystemExit("No author found in DB. Please ingest data first or pass --author-id")

    async for session in get_session():
        if not args.no_reindex:
            logger.info("Reindexing rag_index_item for author_id=%s", author_id)
            indexer = RagIndexingService(session)
            result = await indexer.reindex_author(author_id)
            logger.info("Reindex result: %s", json.dumps(result, ensure_ascii=False))
        else:
            logger.info("Skipping reindex (--no-reindex)")

        engine = RAGEngine(session)
        queries = args.query or DEFAULT_QUERIES

        for q in queries:
            logger.info("\n=== QUERY: %s", q)
            resp = await engine.chat(q, author_id=author_id)
            answer = (resp.get("answer") or "").strip()
            citations = resp.get("citations") or []

            logger.info("Answer (first 500 chars): %s", answer[:500])
            logger.info("Citations count: %s", len(citations))
            for c in citations[:5]:
                logger.info(
                    "  - idx=%s source_type=%s tag=%s title=%s summary_id=%s content_id=%s",
                    c.get("index"),
                    c.get("source_type"),
                    c.get("tag"),
                    c.get("title"),
                    c.get("summary_id"),
                    c.get("content_id"),
                )

        break


if __name__ == "__main__":
    asyncio.run(main())
