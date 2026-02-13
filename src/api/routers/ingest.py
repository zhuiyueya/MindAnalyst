from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks

from src.api.schemas.ingest import IngestRequest
from src.services.ingestion_service import IngestionService

router = APIRouter()


@router.post("/api/v1/ingest")
async def ingest_author(req: IngestRequest, background_tasks: BackgroundTasks):
    return IngestionService(background_tasks).start_ingest(req.author_id, req.limit, use_browser=True)
