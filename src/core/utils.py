from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import HTTPException


def compute_status_fields(content_quality: str, has_segments: bool, has_summary: bool) -> dict[str, Any]:
    using_fallback = content_quality == "summary"
    if content_quality == "missing":
        asr_status = "missing"
    elif using_fallback:
        asr_status = "fallback"
    elif has_segments:
        asr_status = "ready"
    else:
        asr_status = "pending"

    if has_summary:
        summary_status = "ready"
    elif content_quality == "missing":
        summary_status = "blocked"
    elif using_fallback:
        summary_status = "skipped_fallback"
    else:
        summary_status = "pending"

    return {
        "asr_status": asr_status,
        "summary_status": summary_status,
        "using_fallback": using_fallback,
        "has_segments": has_segments,
    }


def parse_datetime(value: str) -> datetime:
    if not value:
        raise HTTPException(status_code=400, detail="Datetime value is required")
    try:
        normalized = value.strip()
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        return datetime.fromisoformat(normalized)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid datetime format: {value}") from exc
