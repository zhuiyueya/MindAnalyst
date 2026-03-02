import logging
import re
from typing import Any, Dict, List, Tuple, cast
from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.embedding.provider import embed_text
from src.models.models import ContentItem, RagIndexItem, Summary
from src.repositories.rag_index_repo import RagIndexRepository

logger = logging.getLogger(__name__)


_TAG_RE = re.compile(r"\[([^\]]+)\]")


def _clean_markdown_noise(text: str) -> str:
    cleaned = text
    cleaned = cleaned.replace("**", "")
    cleaned = re.sub(r"^\s*#{1,6}\s+", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"^\s*---+\s*$", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _split_by_tags(text: str) -> List[Tuple[str, str]]:
    if not text:
        return []

    matches = list(_TAG_RE.finditer(text))
    if not matches:
        return []

    chunks: List[Tuple[str, str]] = []
    for idx, m in enumerate(matches):
        tag = (m.group(1) or "").strip()
        start = m.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if tag and body:
            chunks.append((tag, body))
    return chunks


class RagIndexingService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = RagIndexRepository(session)

    async def reindex_author(self, author_id: str) -> Dict[str, Any]:
        rows = await self.repo.list_latest_structured_summaries_by_author(author_id)
        if not rows:
            return {"author_id": author_id, "indexed": 0, "skipped": 0, "error": "no_summaries"}

        latest_by_content: Dict[str, Tuple[Summary, ContentItem]] = {}
        for summary, content in rows:
            if summary.content_id and summary.content_id not in latest_by_content:
                latest_by_content[summary.content_id] = (summary, content)

        indexed = 0
        skipped = 0

        for summary, content in latest_by_content.values():
            await self._delete_existing_for_summary(summary.id)
            inc_indexed, inc_skipped = await self._index_one_summary(summary, content)
            indexed += inc_indexed
            skipped += inc_skipped

        return {"author_id": author_id, "indexed": indexed, "skipped": skipped, "latest_summary_count": len(latest_by_content)}

    async def _delete_existing_for_summary(self, summary_id: str) -> None:
        await self.repo.delete_by_summary_id(summary_id)

    async def _index_one_summary(self, summary: Summary, content: ContentItem) -> Tuple[int, int]:
        indexed = 0
        skipped = 0

        category = (summary.video_category or "").strip() or "通用领域"

        logger.info(
            "RAG reindex summary: summary_id=%s content_id=%s author_id=%s category=%s",
            summary.id,
            content.id,
            content.author_id,
            category,
        )

        # 1) summary.content chunks
        chunks = _split_by_tags(summary.content or "")
        if not chunks:
            logger.info("RAG chunk split empty: summary_id=%s", summary.id)
        items: List[RagIndexItem] = []
        for chunk_index, (tag, body) in enumerate(chunks, start=1):
            text_raw = _clean_markdown_noise(body)
            if not text_raw:
                skipped += 1
                continue
            text_for_embedding = f"领域: {category}  | 内容: {text_raw}"
            emb = embed_text(text_for_embedding)
            item = RagIndexItem(
                source_type="summary_chunk",
                author_id=content.author_id,
                content_id=content.id,
                summary_id=summary.id,
                tag=tag,
                chunk_index=chunk_index,
                video_category=category,
                text_raw=text_raw,
                text_for_embedding=text_for_embedding,
                embedding=emb,
            )
            items.append(item)
            indexed += 1

        # 2) short_json
        sj: Dict[str, Any] = summary.short_json or {}
        is_trash = bool(sj.get("is_trash"))
        short_summary = (sj.get("summary") or "").strip()
        if (not is_trash) and short_summary:
            keywords_value: Any = sj.get("keywords")
            if isinstance(keywords_value, list):
                keywords_list = cast(List[Any], keywords_value)
                keywords_str = ",".join([str(x) for x in keywords_list if str(x).strip()])
            else:
                keywords_str = str(keywords_value or "")

            text_raw = (short_summary + (f"\n关键词: {keywords_str}" if keywords_str else "")).strip()
            text_for_embedding = text_raw
            emb = embed_text(text_for_embedding)
            item = RagIndexItem(
                source_type="summary_short",
                author_id=content.author_id,
                content_id=content.id,
                summary_id=summary.id,
                tag=None,
                chunk_index=None,
                video_category=category,
                text_raw=text_raw,
                text_for_embedding=text_for_embedding,
                embedding=emb,
            )
            items.append(item)
            indexed += 1
        else:
            skipped += 1

        logger.info(
            "RAG reindex summary done: summary_id=%s indexed=%s skipped=%s",
            summary.id,
            indexed,
            skipped,
        )

        await self.repo.add_items(items)
        return indexed, skipped
