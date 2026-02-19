from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks

from src.api.schemas.rag import RagReindexRequest
from src.api.schemas.common import RagReindexResponse
from src.services.rag_service import RagService

router = APIRouter()


@router.post("/api/v1/rag/reindex", response_model=RagReindexResponse)
async def rag_reindex(req: RagReindexRequest, background_tasks: BackgroundTasks) -> RagReindexResponse:
    result = RagService(background_tasks).start_reindex(req.author_id)
    return RagReindexResponse(status=result.status, scope=result.scope, author_id=result.author_id)
