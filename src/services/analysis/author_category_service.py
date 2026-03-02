import logging
from typing import Any, Dict, List, cast

from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.llm.service import LLMService
from src.core.config import settings
from src.models.models import Author, ContentItem, Summary
from src.repositories.summary_repo import SummaryRepository

logger = logging.getLogger(__name__)


class AuthorCategoryService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.llm = LLMService()
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
            batch_result: Any = await self.llm.select_batch_candidates(batch)
            if isinstance(batch_result, dict):
                batch_result_dict = cast(Dict[str, Any], batch_result)
                selected = batch_result_dict.get("selected_ids")
                if isinstance(selected, list):
                    selected_list = cast(List[Any], selected)
                    candidate_ids.extend(
                        [str(x) for x in selected_list if str(x).strip()]
                    )

        candidate_ids_set = set(candidate_ids)
        candidate_items = [item for item in items if item["video_id"] in candidate_ids_set]
        if not candidate_items:
            candidate_items = items

        final_result: Any = await self.llm.select_final_candidates(candidate_items)
        final_ids_raw: Any = None
        category_list_raw: Any = None
        if isinstance(final_result, dict):
            final_result_dict = cast(Dict[str, Any], final_result)
            final_ids_raw = final_result_dict.get("selected_ids")
            category_list_raw = final_result_dict.get("category_list")

        final_ids: List[str]
        if isinstance(final_ids_raw, list):
            final_ids_list = cast(List[Any], final_ids_raw)
            final_ids = [str(x) for x in final_ids_list if str(x).strip()]
        else:
            final_ids = [item["video_id"] for item in candidate_items][:20]

        category_list: List[str]
        if isinstance(category_list_raw, list):
            category_list_list = cast(List[Any], category_list_raw)
            category_list = [
                str(x)
                for x in category_list_list
                if str(x).strip()
            ]
        else:
            category_list = []

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

        author_category_result: Any = await self.llm.generate_author_categories(category_list, final_long_items)
        final_categories: Any = None
        if isinstance(author_category_result, dict):
            author_category_result_dict = cast(Dict[str, Any], author_category_result)
            final_categories = author_category_result_dict.get("category_list")
        if isinstance(final_categories, list) and final_categories:
            final_categories_list = cast(List[Any], final_categories)
            category_list = [
                str(x)
                for x in final_categories_list
                if str(x).strip()
            ]

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
            tag_result: Any = await self.llm.tag_video_category(category_list, {"summary_content": summary.content})
            category: Any = None
            if isinstance(tag_result, dict):
                tag_result_dict = cast(Dict[str, Any], tag_result)
                category = tag_result_dict.get("category")
            if category:
                summary.video_category = str(category)
                self.session.add(summary)
                await self.session.commit()
                tagged += 1

        return {
            "candidate_count": len(candidate_items),
            "final_count": len(final_items),
            "tagged": tagged,
            "category_list": category_list
        }
