import logging
from typing import Any, Dict, List, cast

from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.llm.service import LLMService
from src.services.llm_call_service import LlmCallService
from src.core.config import settings
from src.models.models import Author, ContentItem, Summary
from src.repositories.summary_repo import SummaryRepository

logger = logging.getLogger(__name__)


class AuthorCategoryService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.llm = LLMService()
        self.llm_calls = LlmCallService(session)
        self.summaries = SummaryRepository(session)

    async def generate_author_categories_and_tag(self, author_id: str) -> Dict[str, Any]:
        logger.info("Generating categories and tagging videos for author %s", author_id)
        rows = await self.summaries.list_structured_with_content_by_author_desc(author_id)

        latest_by_content: Dict[str, tuple[Summary, ContentItem]] = {}
        for summary, content in rows:
            if summary.content_id and summary.content_id not in latest_by_content:
                latest_by_content[summary.content_id] = (summary, content)

        items: List[Dict[str, Any]] = []
        for summary, content in latest_by_content.values():
            payload: Any = summary.short_json
            payload_dict: Dict[str, Any] = payload if isinstance(payload, dict) else {}
            if payload_dict.get("is_trash") is True:
                continue
            summary_text = payload_dict.get("summary") or ""
            keywords_raw = payload_dict.get("keywords")
            keywords: List[str]
            if isinstance(keywords_raw, list):
                keywords_list = cast(List[Any], keywords_raw)
                keywords = [
                    str(x)
                    for x in keywords_list
                    if str(x).strip()
                ]
            else:
                keywords = []
            if not summary_text:
                continue
            items.append({
                "video_id": content.id,
                "summary": summary_text,
                "keywords": keywords
            })

        if not items:
            return {"error": "no_valid_short_summary"}

        batch_size = max(1, settings.CATEGORY_BATCH_SIZE)
        candidate_ids: List[str] = []
        for i in range(0, len(items), batch_size):
            batch = items[i:i + batch_size]
            batch_result = await self.llm.select_batch_candidates(batch)
            if batch_result.call:
                await self.llm_calls.record_call_safe(batch_result.call)
            if batch_result.selected_ids:
                candidate_ids.extend(batch_result.selected_ids)

        candidate_ids_set = set(candidate_ids)
        candidate_items = [item for item in items if item["video_id"] in candidate_ids_set]
        if not candidate_items:
            candidate_items = items

        final_result = await self.llm.select_final_candidates(candidate_items)
        if final_result.call:
            await self.llm_calls.record_call_safe(final_result.call)

        final_ids: List[str] = final_result.selected_ids or [item["video_id"] for item in candidate_items][:20]
        category_list: List[str] = final_result.category_list

        final_ids_set = set(final_ids)
        final_items = [item for item in candidate_items if item["video_id"] in final_ids_set]
        if not final_items:
            final_items = candidate_items[:20]

        final_long_items: List[Dict[str, Any]] = []
        for item in final_items:
            summary_obj, _ = latest_by_content.get(item["video_id"], (None, None))
            if not summary_obj:
                continue
            final_long_items.append({
                "video_id": item["video_id"],
                "summary_content": summary_obj.content
            })

        author_category_result = await self.llm.generate_author_categories(category_list, final_long_items)
        if author_category_result.call:
            await self.llm_calls.record_call_safe(author_category_result.call)
        if author_category_result.category_list:
            category_list = author_category_result.category_list

        author = await self.session.get(Author, author_id)
        if author:
            author.category_list = category_list
            self.session.add(author)
            await self.session.commit()

        if not category_list:
            return {"error": "category_list_empty", "candidate_count": len(candidate_items)}

        tagged = 0
        for summary, content in latest_by_content.values():
            payload = summary.short_json or {}
            if payload.get("is_trash") is True:
                continue
            if not summary.content:
                continue
            tag_result = await self.llm.tag_video_category(category_list, {"summary_content": summary.content})
            if tag_result.call:
                await self.llm_calls.record_call_safe(tag_result.call)
            if tag_result.category:
                summary.video_category = str(tag_result.category)
                self.session.add(summary)
                await self.session.commit()
                tagged += 1

        return {
            "candidate_count": len(candidate_items),
            "final_count": len(final_items),
            "tagged": tagged,
            "category_list": category_list
        }
