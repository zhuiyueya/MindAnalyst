import logging
import asyncio
from typing import List
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import select
from src.database.db import init_db, get_session
from src.services.pipeline import PipelineService
from src.services.chat import ChatService
from src.models.models import Author
from src.api.schemas import IngestRequest, IngestResponse, ChatRequest, ChatResponse, AuthorResponse
from contextlib import asynccontextmanager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("API")

# Lifespan context to init DB
@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield

app = FastAPI(title="Mind Analyst API", lifespan=lifespan)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # For dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def process_author(mid: str, limit: int):
    """Background task to process Author via Space URL"""
    logger.info(f"Starting background processing for author {mid}")
    # Construct Space URL
    url = f"https://space.bilibili.com/{mid}/video"
    
    async for session in get_session():
        pipeline = PipelineService(session)
        try:
            await pipeline.ingest_from_browser(url, limit=limit)
        except Exception as e:
            logger.error(f"Error processing author {mid}: {e}")
        logger.info(f"Finished processing author {mid}")
        break # get_session yields once

@app.post("/api/v1/ingest", response_model=IngestResponse)
async def ingest_author(request: IngestRequest, background_tasks: BackgroundTasks):
    """
    Ingest an Author by Bilibili MID.
    Processing happens in background.
    """
    if not request.mid:
        raise HTTPException(status_code=400, detail="No MID provided")
    
    background_tasks.add_task(process_author, request.mid, request.limit)
    
    return IngestResponse(
        message=f"Processing started for author {request.mid}",
        task_id=request.mid
    )

@app.get("/api/v1/authors", response_model=List[AuthorResponse])
async def get_authors():
    """Get list of ingested authors"""
    async for session in get_session():
        stmt = select(Author)
        result = await session.execute(stmt)
        authors = result.scalars().all()
        return [
            AuthorResponse(
                id=str(a.id), 
                name=a.name, 
                platform=a.platform, 
                avatar_url=a.avatar_url
            ) for a in authors
        ]
        break

@app.post("/api/v1/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Chat with the knowledge base. Optionally filtered by author_id.
    """
    async for session in get_session():
        chat_service = ChatService(session)
        try:
            result = await chat_service.chat(request.query, author_id=request.author_id)
            return ChatResponse(
                answer=result["answer"],
                citations=result["citations"]
            )
        except Exception as e:
            logger.error(f"Chat error: {e}")
            raise HTTPException(status_code=500, detail=str(e))
        break

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
