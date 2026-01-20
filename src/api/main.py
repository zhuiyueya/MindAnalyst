from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from sqlalchemy import delete
from dotenv import load_dotenv
import os

# Load environment variables (for HF_ENDPOINT etc.)
load_dotenv()

from src.database.db import get_session, init_db
from src.models.models import Author, ContentItem, Segment, Summary, AuthorReport
from src.workflows.ingestion import IngestionWorkflow
from src.workflows.analysis import AnalysisWorkflow
from src.adapters.storage.service import StorageService
from src.rag.engine import RAGEngine
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
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

class AuthorTypeRequest(BaseModel):
    author_type: Optional[str] = None

class ContentTypeRequest(BaseModel):
    content_type: Optional[str] = None
    
class ChatResponse(BaseModel):
    answer: str
    citations: List[dict]

# API Endpoints

@app.get("/api/v1/authors")
async def list_authors(session: AsyncSession = Depends(get_session)):
    stmt = select(Author)
    result = await session.execute(stmt)
    authors = result.scalars().all()
    # Populate extra fields like video count if needed
    # For now, just return author objects
    return authors

@app.get("/api/v1/authors/{author_id}")
async def get_author(author_id: str, session: AsyncSession = Depends(get_session)):
    author = await session.get(Author, author_id)
    if not author:
        raise HTTPException(status_code=404, detail="Author not found")
    
    stmt = select(AuthorReport).where(AuthorReport.author_id == author_id).order_by(AuthorReport.created_at.desc())
    result = await session.execute(stmt)
    reports = result.scalars().all()
    reports_data = [report.model_dump() for report in reports]
    reports_by_type: Dict[str, List[Dict[str, Any]]] = {}
    for report in reports_data:
        key = report.get("content_type") or "generic"
        reports_by_type.setdefault(key, []).append(report)
    latest_report = reports_data[0] if reports_data else None

    return {
        "author": author,
        "latest_report": latest_report,
        "reports": reports_data,
        "reports_by_type": reports_by_type
    }

@app.get("/api/v1/authors/{author_id}/videos")
async def get_author_videos(author_id: str, session: AsyncSession = Depends(get_session)):
    stmt = select(ContentItem).where(ContentItem.author_id == author_id).order_by(ContentItem.published_at.desc())
    result = await session.execute(stmt)
    videos = result.scalars().all()
    
    # We might want to include summary status
    video_list = []
    for v in videos:
        # Check if summary exists
        # This is N+1 query, but for MVP it's okay (or optimize with join)
        stmt_sum = select(Summary).where(Summary.content_id == v.id)
        res_sum = await session.execute(stmt_sum)
        summary = res_sum.scalar_one_or_none()
        
        v_dict = v.model_dump()
        v_dict["has_summary"] = bool(summary)
        video_list.append(v_dict)
        
    return video_list

@app.get("/api/v1/videos/{video_id}")
async def get_video_detail(video_id: str, session: AsyncSession = Depends(get_session)):
    # video_id can be UUID or BVID? Let's assume UUID for now as it is primary key.
    # But frontend might pass BVID if we didn't expose UUID. 
    # Let's try UUID first, if fails try BVID.
    
    video = await session.get(ContentItem, video_id)
    if not video:
        # Try external_id
        stmt = select(ContentItem).where(ContentItem.external_id == video_id)
        result = await session.execute(stmt)
        video = result.scalar_one_or_none()
        
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
        
    # Get Summary
    stmt_sum = select(Summary).where(Summary.content_id == video.id)
    res_sum = await session.execute(stmt_sum)
    summary = res_sum.scalar_one_or_none()
    
    # Get Segments (Transcript)
    stmt_seg = select(Segment).where(Segment.content_id == video.id).order_by(Segment.segment_index)
    res_seg = await session.execute(stmt_seg)
    segments = res_seg.scalars().all()

    return {
        "video": video.model_dump(),
        "summary": summary.model_dump() if summary else None,
        "segments": [s.model_dump(exclude={"embedding"}) for s in segments],
    }

@app.post("/api/v1/authors/{author_id}/set_type")
async def set_author_type(
    author_id: str,
    req: AuthorTypeRequest,
    session: AsyncSession = Depends(get_session)
):
    author = await session.get(Author, author_id)
    if not author:
        raise HTTPException(status_code=404, detail="Author not found")

    author_type = req.author_type.strip() if req.author_type else None
    author.author_type = author_type or None
    author.author_type_source = "user" if author_type else None
    session.add(author)

    stmt = select(ContentItem).where(ContentItem.author_id == author_id)
    result = await session.execute(stmt)
    contents = result.scalars().all()
    for content in contents:
        if author_type:
            content.content_type = author_type
            content.content_type_source = "author_inherit"
        elif content.content_type_source == "author_inherit":
            content.content_type = None
            content.content_type_source = None
        session.add(content)

    await session.commit()
    return {"author_id": author_id, "author_type": author.author_type}

@app.post("/api/v1/videos/{video_id}/set_type")
async def set_video_type(
    video_id: str,
    req: ContentTypeRequest,
    session: AsyncSession = Depends(get_session)
):
    video = await session.get(ContentItem, video_id)
    if not video:
        stmt = select(ContentItem).where(ContentItem.external_id == video_id)
        result = await session.execute(stmt)
        video = result.scalar_one_or_none()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    if video.author_id:
        author = await session.get(Author, video.author_id)
        if author and author.author_type:
            raise HTTPException(status_code=400, detail="Author type set; clear author type before overriding video type")

    content_type = req.content_type.strip() if req.content_type else None
    video.content_type = content_type or None
    video.content_type_source = "user" if content_type else None
    session.add(video)
    await session.commit()
    await session.refresh(video)
    return {"video": video.model_dump()}

@app.get("/api/v1/videos/{video_id}/playback")
async def get_video_playback_url(video_id: str, session: AsyncSession = Depends(get_session)):
    # Logic: 
    # 1. Get video content item to find extra_data or construct object name
    # 2. Check if we have original file in MinIO.
    #    The naming convention in ingestion.py was: f"{content.external_id}_{os.path.basename(audio_path)}"
    #    But we deleted the local file. We uploaded it.
    #    We need to know the object name. 
    #    Ideally, ContentItem should store 'storage_object_name'. 
    #    But we didn't add that field. 
    #    Workaround: Search MinIO for object starting with BVID? 
    #    Or just try to reconstruct it? We don't know the extension (.aac, .mp3).
    #    Let's use a helper to list objects or assume we can find it.
    
    #    For now, let's look at ingestion.py again. 
    #    object_name = f"{content.external_id}_{os.path.basename(audio_path)}"
    #    And audio_path comes from crawler.download_audio.
    
    #    For MVP, let's list objects in bucket with prefix matching external_id.
    
    video = await session.get(ContentItem, video_id)
    if not video:
         # Try external_id
        stmt = select(ContentItem).where(ContentItem.external_id == video_id)
        result = await session.execute(stmt)
        video = result.scalar_one_or_none()
        
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
        
    storage = StorageService()
    # List objects with prefix
    objects = storage.client.list_objects(storage.bucket_name, prefix=video.external_id, recursive=True)
    
    # Find first match
    target_obj = None
    for obj in objects:
        if obj.object_name.startswith(video.external_id):
            target_obj = obj.object_name
            break
            
    if not target_obj:
        raise HTTPException(status_code=404, detail="Media file not found in storage")
        
    url = storage.get_file_url(target_obj)
    return {"url": url}

@app.post("/api/v1/authors/{author_id}/regenerate_report")
async def regenerate_author_report(
    author_id: str, 
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session)
):
    # Verify author exists
    author = await session.get(Author, author_id)
    if not author:
        raise HTTPException(status_code=404, detail="Author not found")
        
    background_tasks.add_task(run_regenerate_report, author_id)
    return {"status": "started", "message": "Report regeneration started"}

@app.post("/api/v1/authors/{author_id}/resummarize_all")
async def resummarize_all_videos(
    author_id: str, 
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    include_fallback: bool = False
):
    author = await session.get(Author, author_id)
    if not author:
        raise HTTPException(status_code=404, detail="Author not found")
        
    background_tasks.add_task(run_resummarize_author, author_id, include_fallback)
    return {"status": "started", "message": "Batch summarization started"}

@app.post("/api/v1/videos/{video_id}/resummarize")
async def resummarize_video(
    video_id: str, 
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    include_fallback: bool = False
):
    # Verify video
    video = await session.get(ContentItem, video_id)
    if not video:
        # Try external_id
        stmt = select(ContentItem).where(ContentItem.external_id == video_id)
        result = await session.execute(stmt)
        video = result.scalar_one_or_none()
        
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
        
    background_tasks.add_task(run_resummarize_video, video.id, include_fallback)
    return {"status": "started", "message": "Video summarization started"}

@app.post("/api/v1/authors/{author_id}/reprocess_asr")
async def reprocess_author_asr(
    author_id: str,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session)
):
    author = await session.get(Author, author_id)
    if not author:
        raise HTTPException(status_code=404, detail="Author not found")

    background_tasks.add_task(run_reprocess_author_asr, author_id)
    return {"status": "started", "message": "Transcript reprocess started"}

@app.post("/api/v1/videos/{video_id}/reprocess_asr")
async def reprocess_video_asr(
    video_id: str,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session)
):
    video = await session.get(ContentItem, video_id)
    if not video:
        stmt = select(ContentItem).where(ContentItem.external_id == video_id)
        result = await session.execute(stmt)
        video = result.scalar_one_or_none()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    background_tasks.add_task(run_reprocess_video_asr, video.id)
    return {"status": "started", "message": "Transcript reprocess started"}

# Background Task Functions

async def run_regenerate_report(author_id: str):
    async for session in get_session():
        analysis = AnalysisWorkflow(session)
        try:
            await analysis.generate_author_report(author_id)
        except Exception as e:
            logger.error(f"Report regeneration failed: {e}")
        break

async def run_resummarize_video(content_id: str, include_fallback: bool = False):
    async for session in get_session():
        analysis = AnalysisWorkflow(session)
        try:
            content = await session.get(ContentItem, content_id)
            if not content:
                return
            
            # Fetch segments
            stmt = select(Segment).where(Segment.content_id == content_id).order_by(Segment.segment_index)
            res = await session.execute(stmt)
            segments = res.scalars().all()
            
            if not segments:
                logger.warning(f"No segments found for {content.title}, cannot summarize.")
                return

            if content.content_quality == "summary" and not include_fallback:
                logger.info(f"Skipping {content.title} (fallback transcript).")
                return
            
            # Check for existing summary to update
            stmt_sum = select(Summary).where(Summary.content_id == content_id)
            res_sum = await session.execute(stmt_sum)
            existing_summary = res_sum.scalar_one_or_none()
            
            await analysis.generate_content_summary(content, segments, existing_summary=existing_summary)
            
        except Exception as e:
            logger.error(f"Video summarization failed: {e}")
        break

async def run_resummarize_author(author_id: str, include_fallback: bool = False):
    async for session in get_session():
        analysis = AnalysisWorkflow(session)
        try:
            # Get all contents
            stmt = select(ContentItem).where(ContentItem.author_id == author_id)
            res = await session.execute(stmt)
            contents = res.scalars().all()
            
            logger.info(f"Re-summarizing {len(contents)} videos for author {author_id}")
            
            for content in contents:
                # Fetch segments
                stmt_seg = select(Segment).where(Segment.content_id == content.id).order_by(Segment.segment_index)
                res_seg = await session.execute(stmt_seg)
                segments = res_seg.scalars().all()
                
                if not segments:
                    logger.info(f"Skipping {content.title} (no segments)")
                    continue

                if content.content_quality == "summary" and not include_fallback:
                    logger.info(f"Skipping {content.title} (fallback transcript)")
                    continue

                stmt_sum = select(Summary).where(Summary.content_id == content.id)
                res_sum = await session.execute(stmt_sum)
                existing_summary = res_sum.scalar_one_or_none()
                
                await analysis.generate_content_summary(content, segments, existing_summary=existing_summary)
                    
        except Exception as e:
            logger.error(f"Batch summarization failed: {e}")
        break

async def run_reprocess_video_asr(content_id: str):
    async for session in get_session():
        workflow = IngestionWorkflow(session)
        try:
            content = await session.get(ContentItem, content_id)
            if not content:
                return

            await session.execute(delete(Segment).where(Segment.content_id == content_id))
            await session.commit()
            await workflow.process_content(content)
        except Exception as e:
            logger.error(f"Transcript reprocess failed: {e}")
        break

async def run_reprocess_author_asr(author_id: str):
    async for session in get_session():
        workflow = IngestionWorkflow(session)
        try:
            stmt = select(ContentItem).where(ContentItem.author_id == author_id)
            res = await session.execute(stmt)
            contents = res.scalars().all()
            logger.info(f"Reprocessing transcripts for {len(contents)} videos (author {author_id})")

            for content in contents:
                stmt_seg = select(Segment.id).where(Segment.content_id == content.id).limit(1)
                res_seg = await session.execute(stmt_seg)
                has_segment = res_seg.scalar_one_or_none() is not None
                needs_reprocess = (not has_segment) or content.content_quality == "summary"

                if not needs_reprocess:
                    continue

                await session.execute(delete(Segment).where(Segment.content_id == content.id))
                await session.commit()
                await workflow.process_content(content)
        except Exception as e:
            logger.error(f"Transcript reprocess failed: {e}")
        break

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
    # If it's a URL, or we suspect API issues (which we do now), use browser.
    # Actually, let's default to browser for stability given API rate limits.
    # But for backward compatibility with pure MID inputs:
    if "bilibili.com" in req.author_id or "http" in req.author_id:
        use_browser = True
    else:
        # If just MID, also use browser?
        # Construct a URL for it to force browser usage
        # Or just set use_browser = True and handle MID in ingestion
        # But ingest_from_browser expects a URL.
        # Let's convert MID to URL here if we want to force browser.
        # req.author_id = f"https://space.bilibili.com/{req.author_id}"
        # use_browser = True
        pass # Keep old logic for now, user should provide URL if they want browser
    
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
