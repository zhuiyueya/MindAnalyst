from __future__ import annotations

from typing import Any, Optional, cast

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.utils import compute_status_fields
from src.domain.results import AuthorDetailResult, AuthorsListResult
from src.repositories.author_repo import AuthorRepository
from src.repositories.content_repo import ContentRepository
from src.repositories.segment_repo import SegmentRepository
from src.repositories.summary_repo import SummaryRepository
from src.repositories.author_report_repo import AuthorReportRepository


class AuthorService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.authors = AuthorRepository(session)
        self.contents = ContentRepository(session)
        self.segments = SegmentRepository(session)
        self.summaries = SummaryRepository(session)
        self.reports = AuthorReportRepository(session)

    async def list_authors(self) -> AuthorsListResult:
        authors = await self.authors.list_all()
        authors_data: list[dict[str, Any]] = []

        for author in authors:
            contents = await self.contents.list_by_author(str(author.id))

            asr_counts = {"ready": 0, "pending": 0, "fallback": 0, "missing": 0}
            summary_counts = {"ready": 0, "pending": 0, "skipped_fallback": 0, "blocked": 0}
            quality_counts: dict[str, int] = {"full": 0, "summary": 0, "missing": 0}

            for content in contents:
                has_segments = await self.segments.has_any_for_content(str(content.id))
                has_summary = await self.summaries.has_any_for_content(str(content.id))

                status_fields = compute_status_fields(content.content_quality, has_segments, has_summary)
                asr_counts[str(status_fields["asr_status"])] += 1
                summary_counts[str(status_fields["summary_status"])] += 1
                quality_counts[content.content_quality] = quality_counts.get(content.content_quality, 0) + 1

            author_data = author.model_dump()
            author_data["author_status"] = {
                "total_videos": len(contents),
                "asr_status_counts": asr_counts,
                "summary_status_counts": summary_counts,
                "content_quality_counts": quality_counts,
            }
            authors_data.append(author_data)

        return AuthorsListResult(items=authors_data)

    async def get_author_detail(self, author_id: str) -> AuthorDetailResult:
        author = await self.authors.get(author_id)
        if not author:
            raise HTTPException(status_code=404, detail="Author not found")

        reports = await self.reports.list_by_author_desc(author_id)
        reports_data: list[dict[str, Any]] = [report.model_dump() for report in reports]

        reports_by_type: dict[str, list[dict[str, Any]]] = {}
        for report in reports_data:
            key = report.get("content_type") or "generic"
            reports_by_type.setdefault(str(key), []).append(report)

        latest_report: Optional[dict[str, Any]] = reports_data[0] if reports_data else None

        category_reports_by_type: dict[str, dict[str, dict[str, Any]]] = {}
        for report in reports_data:
            if report.get("report_type") != "report.author.category":
                continue
            key = report.get("content_type") or "generic"
            json_data = report.get("json_data")
            if isinstance(json_data, dict):
                json_data_dict = cast(dict[str, Any], json_data)
                category_value = json_data_dict.get("category")
                if isinstance(category_value, str) and category_value:
                    bucket = category_reports_by_type.setdefault(str(key), {})
                    if category_value not in bucket:
                        bucket[category_value] = report

        contents = await self.contents.list_by_author(author_id)

        asr_counts = {"ready": 0, "pending": 0, "fallback": 0, "missing": 0}
        summary_counts = {"ready": 0, "pending": 0, "skipped_fallback": 0, "blocked": 0}
        quality_counts: dict[str, int] = {"full": 0, "summary": 0, "missing": 0}

        for content in contents:
            has_segments = await self.segments.has_any_for_content(str(content.id))
            has_summary = await self.summaries.has_any_for_content(str(content.id))

            status_fields = compute_status_fields(content.content_quality, has_segments, has_summary)
            asr_counts[str(status_fields["asr_status"])] += 1
            summary_counts[str(status_fields["summary_status"])] += 1
            quality_counts[content.content_quality] = quality_counts.get(content.content_quality, 0) + 1

        author_status: dict[str, Any] = {
            "total_videos": len(contents),
            "asr_status_counts": asr_counts,
            "summary_status_counts": summary_counts,
            "content_quality_counts": quality_counts,
        }

        return AuthorDetailResult(
            author=author.model_dump(),
            latest_report=latest_report,
            reports=reports_data,
            reports_by_type=reports_by_type,
            category_reports_by_type=category_reports_by_type,
            author_status=author_status,
        )
