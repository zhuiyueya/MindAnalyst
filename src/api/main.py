from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from sqlalchemy import delete, func
from dotenv import load_dotenv
import os
from datetime import datetime

# Load environment variables (for HF_ENDPOINT etc.)
load_dotenv()

from src.database.db import get_session, init_db
from src.models.models import Author, ContentItem, Segment, Summary, AuthorReport, LLMCallLog
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

def _compute_status_fields(content_quality: str, has_segments: bool, has_summary: bool) -> Dict[str, Any]:
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
        "has_segments": has_segments
    }

def _parse_datetime(value: str) -> datetime:
    if not value:
        raise HTTPException(status_code=400, detail="Datetime value is required")
    try:
        normalized = value.strip()
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        return datetime.fromisoformat(normalized)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid datetime format: {value}") from exc

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
    authors_data = []
    for author in authors:
        stmt_contents = select(ContentItem).where(ContentItem.author_id == author.id)
        res_contents = await session.execute(stmt_contents)
        contents = res_contents.scalars().all()

        asr_counts = {"ready": 0, "pending": 0, "fallback": 0, "missing": 0}
        summary_counts = {"ready": 0, "pending": 0, "skipped_fallback": 0, "blocked": 0}
        quality_counts = {"full": 0, "summary": 0, "missing": 0}

        for content in contents:
            stmt_seg = select(Segment.id).where(Segment.content_id == content.id).limit(1)
            res_seg = await session.execute(stmt_seg)
            has_segments = res_seg.scalar_one_or_none() is not None

            stmt_sum = select(Summary.id).where(Summary.content_id == content.id).limit(1)
            res_sum = await session.execute(stmt_sum)
            has_summary = res_sum.scalar_one_or_none() is not None

            status_fields = _compute_status_fields(content.content_quality, has_segments, has_summary)
            asr_counts[status_fields["asr_status"]] += 1
            summary_counts[status_fields["summary_status"]] += 1
            quality_counts[content.content_quality] = quality_counts.get(content.content_quality, 0) + 1

        author_data = author.model_dump()
        author_data["author_status"] = {
            "total_videos": len(contents),
            "asr_status_counts": asr_counts,
            "summary_status_counts": summary_counts,
            "content_quality_counts": quality_counts
        }
        authors_data.append(author_data)

    return authors_data

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

    stmt_contents = select(ContentItem).where(ContentItem.author_id == author_id)
    res_contents = await session.execute(stmt_contents)
    contents = res_contents.scalars().all()

    asr_counts = {"ready": 0, "pending": 0, "fallback": 0, "missing": 0}
    summary_counts = {"ready": 0, "pending": 0, "skipped_fallback": 0, "blocked": 0}
    quality_counts = {"full": 0, "summary": 0, "missing": 0}

    for content in contents:
        stmt_seg = select(Segment.id).where(Segment.content_id == content.id).limit(1)
        res_seg = await session.execute(stmt_seg)
        has_segments = res_seg.scalar_one_or_none() is not None

        stmt_sum = select(Summary.id).where(Summary.content_id == content.id).limit(1)
        res_sum = await session.execute(stmt_sum)
        has_summary = res_sum.scalar_one_or_none() is not None

        status_fields = _compute_status_fields(content.content_quality, has_segments, has_summary)
        asr_counts[status_fields["asr_status"]] += 1
        summary_counts[status_fields["summary_status"]] += 1
        quality_counts[content.content_quality] = quality_counts.get(content.content_quality, 0) + 1

    author_status = {
        "total_videos": len(contents),
        "asr_status_counts": asr_counts,
        "summary_status_counts": summary_counts,
        "content_quality_counts": quality_counts
    }

    return {
        "author": author,
        "latest_report": latest_report,
        "reports": reports_data,
        "reports_by_type": reports_by_type,
        "author_status": author_status
    }

@app.get("/api/v1/authors/{author_id}/videos")
async def get_author_videos(author_id: str, session: AsyncSession = Depends(get_session)):
    stmt = select(ContentItem).where(ContentItem.author_id == author_id).order_by(ContentItem.published_at.desc())
    result = await session.execute(stmt)
    videos = result.scalars().all()
    
    video_list = []
    for v in videos:
        stmt_sum = select(Summary.id).where(Summary.content_id == v.id).limit(1)
        res_sum = await session.execute(stmt_sum)
        has_summary = res_sum.scalar_one_or_none() is not None

        stmt_seg = select(Segment.id).where(Segment.content_id == v.id).limit(1)
        res_seg = await session.execute(stmt_seg)
        has_segments = res_seg.scalar_one_or_none() is not None

        v_dict = v.model_dump()
        v_dict["has_summary"] = has_summary
        v_dict.update(_compute_status_fields(v.content_quality, has_segments, has_summary))
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

    has_segments = len(segments) > 0
    has_summary = summary is not None
    video_data = video.model_dump()
    video_data.update(_compute_status_fields(video.content_quality, has_segments, has_summary))

    return {
        "video": video_data,
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

@app.get("/api/v1/llm_calls")
async def list_llm_calls(
    session: AsyncSession = Depends(get_session),
    task_type: Optional[str] = None,
    content_type: Optional[str] = None,
    profile_key: Optional[str] = None,
    status: Optional[str] = None,
    model: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
):
    limit = max(1, min(limit, 200))
    offset = max(0, offset)

    filters = []
    if task_type:
        filters.append(LLMCallLog.task_type == task_type)
    if content_type:
        filters.append(LLMCallLog.content_type == content_type)
    if profile_key:
        filters.append(LLMCallLog.profile_key == profile_key)
    if status:
        filters.append(LLMCallLog.status == status)
    if model:
        filters.append(LLMCallLog.model == model)
    if start_time:
        filters.append(LLMCallLog.created_at >= _parse_datetime(start_time))
    if end_time:
        filters.append(LLMCallLog.created_at <= _parse_datetime(end_time))

    count_stmt = select(func.count()).select_from(LLMCallLog)
    if filters:
        count_stmt = count_stmt.where(*filters)
    total = (await session.execute(count_stmt)).scalar_one()

    stmt = select(LLMCallLog).order_by(LLMCallLog.created_at.desc())
    if filters:
        stmt = stmt.where(*filters)
    stmt = stmt.offset(offset).limit(limit)
    result = await session.execute(stmt)
    logs = result.scalars().all()

    return {
        "items": [log.model_dump() for log in logs],
        "total": total,
        "limit": limit,
        "offset": offset
    }

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

@app.post("/api/v1/authors/{author_id}/resummarize_pending")
async def resummarize_pending_videos(
    author_id: str,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session)
):
    author = await session.get(Author, author_id)
    if not author:
        raise HTTPException(status_code=404, detail="Author not found")

    background_tasks.add_task(run_resummarize_author_pending, author_id)
    return {"status": "started", "message": "Pending summarization started"}

@app.post("/api/v1/authors/{author_id}/compress_short_summaries")
async def compress_short_summaries(
    author_id: str,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session)
):
    author = await session.get(Author, author_id)
    if not author:
        raise HTTPException(status_code=404, detail="Author not found")

    background_tasks.add_task(run_generate_short_summaries, author_id)
    return {"status": "started", "message": "Short summary compression started"}

@app.post("/api/v1/authors/{author_id}/generate_categories")
async def generate_author_categories(
    author_id: str,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session)
):
    author = await session.get(Author, author_id)
    if not author:
        raise HTTPException(status_code=404, detail="Author not found")

    background_tasks.add_task(run_generate_author_categories, author_id)
    return {"status": "started", "message": "Category analysis started"}

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

async def run_resummarize_author_pending(author_id: str):
    async for session in get_session():
        analysis = AnalysisWorkflow(session)
        try:
            stmt = select(ContentItem).where(ContentItem.author_id == author_id)
            res = await session.execute(stmt)
            contents = res.scalars().all()

            logger.info(f"Re-summarizing pending videos for author {author_id}")

            for content in contents:
                if content.content_quality in {"summary", "missing"}:
                    logger.info(f"Skipping {content.title} (fallback or missing content)")
                    continue

                stmt_sum = select(Summary.id).where(Summary.content_id == content.id).limit(1)
                res_sum = await session.execute(stmt_sum)
                has_summary = res_sum.scalar_one_or_none() is not None
                if has_summary:
                    logger.info(f"Skipping {content.title} (summary already exists)")
                    continue

                stmt_seg = select(Segment).where(Segment.content_id == content.id).order_by(Segment.segment_index)
                res_seg = await session.execute(stmt_seg)
                segments = res_seg.scalars().all()
                if not segments:
                    logger.info(f"Skipping {content.title} (no segments)")
                    continue

                await analysis.generate_content_summary(content, segments)
        except Exception as e:
            logger.error(f"Pending summarization failed: {e}")
        break

async def run_generate_short_summaries(author_id: str):
    async for session in get_session():
        analysis = AnalysisWorkflow(session)
        try:
            await analysis.generate_short_summaries_for_author(author_id)
        except Exception as e:
            logger.error(f"Short summary compression failed: {e}")
        break

async def run_generate_author_categories(author_id: str):
    async for session in get_session():
        analysis = AnalysisWorkflow(session)
        try:
            await analysis.generate_author_categories_and_tag(author_id)
        except Exception as e:
            logger.error(f"Category generation failed: {e}")
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
            await workflow.process_content(content, reuse_audio_only=True)
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
                await workflow.process_content(content, reuse_audio_only=True)
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
        req.author_id = f"https://space.bilibili.com/{req.author_id}"
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
