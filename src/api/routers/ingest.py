from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks

from src.api.schemas.ingest import IngestRequest, IngestResponse
from src.services.ingestion_service import IngestionService

router = APIRouter()


@router.post("/api/v1/ingest", response_model=IngestResponse)
async def ingest_author(req: IngestRequest, background_tasks: BackgroundTasks) -> IngestResponse:
    result = IngestionService(background_tasks).start_ingest(req.author_id, req.limit, use_browser=True)
    return IngestResponse(status=result.status, message=result.message)
