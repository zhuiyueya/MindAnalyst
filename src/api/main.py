from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from src.database.db import get_session, init_db
from src.models.models import Author, ContentItem, Segment
from src.workflows.ingestion import IngestionWorkflow
from src.rag.engine import RAGEngine
from pydantic import BaseModel
from typing import List, Optional
import logging
import asyncio
from contextlib import asynccontextmanager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    yield
    # Shutdown

app = FastAPI(lifespan=lifespan)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic Models
class IngestRequest(BaseModel):
    author_id: str # Can be mid or url
    limit: int = 10
    
class ChatRequest(BaseModel):
    query: str
    author_id: Optional[str] = None
    
class ChatResponse(BaseModel):
    answer: str
    citations: List[dict]

# API Endpoints

@app.get("/api/v1/authors")
async def list_authors(session: AsyncSession = Depends(get_session)):
    stmt = select(Author)
    result = await session.execute(stmt)
    authors = result.scalars().all()
    return authors

@app.post("/api/v1/ingest")
async def ingest_author(
    req: IngestRequest, 
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session)
):
    """
    Trigger background ingestion for an author.
    If input looks like a URL, use BrowserCrawler.
    Otherwise assume MID and use Bilix/Browser.
    """
    logger.info(f"Received ingest request for {req.author_id}")
    
    # Check if we should use BrowserCrawler based on input
    use_browser = False
    if "bilibili.com" in req.author_id or "http" in req.author_id:
        use_browser = True
    
    # We need a new session for background task since the dep session closes
    # But BackgroundTasks with async functions is tricky with sessions.
    # Better approach: Run it immediately (blocking) for MVP or handle session properly.
    # For MVP, let's run it in background but we need to manage session lifecycle.
    # We will instantiate a new session inside the background wrapper.
    
    background_tasks.add_task(run_ingestion_task, req.author_id, req.limit, use_browser)
    
    return {"status": "started", "message": f"Ingestion started for {req.author_id}"}

async def run_ingestion_task(mid_or_url: str, limit: int, use_browser: bool):
    """Background task wrapper"""
    logger.info(f"Starting background processing for author {mid_or_url}")
    async for session in get_session():
        workflow = IngestionWorkflow(session)
        try:
            if use_browser:
                await workflow.ingest_from_browser(mid_or_url, limit=limit)
            else:
                await workflow.ingest_author(mid_or_url, limit=limit)
        except Exception as e:
            logger.error(f"Ingestion failed: {e}")
        # Session closes after async for loop
        break

@app.post("/api/v1/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, session: AsyncSession = Depends(get_session)):
    engine = RAGEngine(session)
    result = await engine.chat(req.query, author_id=req.author_id)
    return result

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
