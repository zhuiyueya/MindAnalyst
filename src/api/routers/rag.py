from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks

from src.api.schemas.rag import RagReindexRequest
from src.services.rag_service import RagService

router = APIRouter()


@router.post("/api/v1/rag/reindex")
async def rag_reindex(req: RagReindexRequest, background_tasks: BackgroundTasks):
    return RagService(background_tasks).start_reindex(req.author_id)
