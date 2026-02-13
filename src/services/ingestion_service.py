from __future__ import annotations

import logging

from fastapi import BackgroundTasks

from src.database.db import get_session
from src.workflows.ingestion import IngestionWorkflow

logger = logging.getLogger(__name__)


class IngestionService:
    def __init__(self, background_tasks: BackgroundTasks):
        self.background_tasks = background_tasks

    def start_ingest(self, author_id: str, limit: int, use_browser: bool) -> dict[str, str]:
        normalized = author_id
        if "bilibili.com" not in normalized and "http" not in normalized:
            normalized = f"https://space.bilibili.com/{normalized}"

        self.background_tasks.add_task(run_ingestion_task, normalized, limit, use_browser)
        return {"status": "started", "message": f"Ingestion started for {normalized}"}


async def run_ingestion_task(mid_or_url: str, limit: int, use_browser: bool) -> None:
    logger.info("Starting background processing for author %s", mid_or_url)
    async for session in get_session():
        workflow = IngestionWorkflow(session)
        try:
            if use_browser:
                await workflow.ingest_from_browser(mid_or_url, limit=limit)
            else:
                await workflow.ingest_author(mid_or_url, limit=limit)
        except Exception as e:
            logger.error("Ingestion failed: %s", e)
        break
