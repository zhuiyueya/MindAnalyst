import asyncio
from typing import List, Dict, Optional
import os
import tempfile
import uuid
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from src.models.models import Author, ContentItem, Segment
from src.adapters.sources.bilibili.bilix import BilixCrawler
from src.adapters.sources.bilibili.browser import BrowserCrawler
from src.adapters.asr.service import ASRService
from src.adapters.storage.service import StorageService
from src.database.db import get_session
from sentence_transformers import SentenceTransformer
import logging

logger = logging.getLogger(__name__)

class IngestionWorkflow:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.crawler = BilixCrawler()
        self.browser_crawler = None # Lazy init
        self.asr = ASRService()
        self.storage = StorageService() # MinIO
        
        # Load embedding model lazily or globally. For MVP, load here.
        if os.getenv("MOCK_EMBEDDING"):
            self.embedder = None
            logger.info("Using MOCK embedding")
        else:
            try:
                self.embedder = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
            except Exception as e:
                logger.warning(f"Failed to load local embedder: {e}")
                self.embedder = None

    async def _store_author_avatar(self, avatar_url: str, author_external_id: str) -> Optional[str]:
        if not avatar_url:
            return None

        tmp_path = None
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(avatar_url)
                resp.raise_for_status()
                content_type = resp.headers.get("content-type", "")
                if "png" in content_type:
                    ext = ".png"
                elif "webp" in content_type:
                    ext = ".webp"
                elif "jpeg" in content_type or "jpg" in content_type:
                    ext = ".jpg"
                else:
                    ext = os.path.splitext(avatar_url.split("?")[0])[1] or ".jpg"

                with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp_file:
                    tmp_file.write(resp.content)
                    tmp_path = tmp_file.name

            object_name = f"avatars/{author_external_id}_{uuid.uuid4().hex}{ext}"
            await self.storage.upload_file(tmp_path, object_name)
            return self.storage.get_file_url(object_name)
        except Exception as e:
            logger.warning(f"Failed to store avatar {avatar_url}: {e}")
            return None
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception as rm_e:
                    logger.warning(f"Failed to remove temp avatar file {tmp_path}: {rm_e}")

    async def ingest_from_browser(self, url: str, limit: int = 0):
        """
        Use BrowserCrawler to get videos from a page (e.g. Space) and ingest them.
        limit: Max videos to process.
        """
        # Always launch browser in headless=False mode for debugging if needed, 
        # or True if you want it background.
        # But wait, BrowserCrawler defaults to headless=False in our new code.
        if not self.browser_crawler:
            self.browser_crawler = BrowserCrawler(headless=False)
            
        try:
            # 1. Scrape Videos
            result = await self.browser_crawler.get_videos_from_page(url, limit=limit)
        except Exception as e:
            logger.error(f"Browser crawler failed: {e}")
            return
        finally:
            # Close browser when done
            if self.browser_crawler:
                await self.browser_crawler.close()
                self.browser_crawler = None

        videos = result.get("videos", [])
        author_data = result.get("author", None)
        
        if not videos:
            logger.warning(f"No videos found on {url}")
            return
            
        # 2. Process Author
        # Use scraped author info if available, otherwise try bilix
        first_vid = videos[0]
        author = None
        
        try:
            mid = author_data["mid"] if author_data else "0"
            
            # If we didn't scrape author info (e.g. not on Space page), or avatar missing, try fallback
            if not author_data or not mid or not author_data.get("face"):
                logger.info(f"Fetching author info for BVID: {first_vid['bvid']}")
                # Add try-except for bilix call
                try:
                    bilix_author = await self.crawler.get_author_info(first_vid['bvid'])
                    mid = str(bilix_author["mid"])
                    author_data = {
                        "mid": mid,
                        "name": bilix_author["name"],
                        "face": bilix_author["face"],
                        "url": f"https://space.bilibili.com/{mid}"
                    }
                except Exception as bilix_e:
                    logger.warning(f"Bilix fallback failed: {bilix_e}")
                    # Keep mid as "0" if failed
                    author_data = {
                        "mid": "0",
                        "name": "Unknown Author",
                        "face": "",
                        "url": ""
                    }

            # Create/Get Author
            stmt = select(Author).where(Author.external_id == mid)
            result_db = await self.session.execute(stmt)
            author = result_db.scalar_one_or_none()
            
            stored_avatar_url = None
            if author_data and author_data.get("face"):
                if not author or not author.avatar_url or author.avatar_url == author_data.get("face"):
                    stored_avatar_url = await self._store_author_avatar(author_data.get("face"), mid)

            if not author:
                author = Author(
                    platform="bilibili",
                    external_id=mid,
                    name=author_data["name"],
                    homepage_url=author_data["url"],
                    avatar_url=stored_avatar_url or author_data["face"]
                )
                self.session.add(author)
                await self.session.commit()
                await self.session.refresh(author)
                logger.info(f"Created author: {author.name}")
            else:
                # Optional: Update author info
                if author.name == "Unknown Author" and author_data["name"] != "Unknown Author":
                    author.name = author_data["name"]
                if stored_avatar_url:
                    author.avatar_url = stored_avatar_url
                elif not author.avatar_url and author_data.get("face"):
                    author.avatar_url = author_data["face"]
                self.session.add(author)
                await self.session.commit()
                logger.info(f"Updated author info: {author.name}")
                
        except Exception as e:
            logger.error(f"Failed to get/create author: {e}. Creating dummy author.")
            # Fallback: Create a dummy author if we can't fetch info
            # Check if dummy exists
            dummy_mid = "0"
            stmt = select(Author).where(Author.external_id == dummy_mid)
            result = await self.session.execute(stmt)
            author = result.scalar_one_or_none()
            
            if not author:
                author = Author(
                    platform="bilibili",
                    external_id=dummy_mid,
                    name="Unknown Author",
                    homepage_url="",
                    avatar_url=""
                )
                self.session.add(author)
                await self.session.commit()
                await self.session.refresh(author)

        # 3. Ingest Videos
        for v in videos:
            bvid = v["bvid"]
            
            # Correct title using bilix API if needed (e.g. RPA got partial data)
            # This adds latency but ensures data quality
            try:
                # We can optimize this by only calling if title looks suspicious, 
                # but for MVP let's trust API more than RPA
                v_info_meta = await self.crawler.get_video_info(bvid)
                if v_info_meta.get("title") and v_info_meta["title"] != "Unknown Title":
                    if v["title"] != v_info_meta["title"]:
                        logger.info(f"Correcting title for {bvid}: '{v['title']}' -> '{v_info_meta['title']}'")
                        v["title"] = v_info_meta["title"]
            except Exception as e:
                logger.warning(f"Failed to fetch metadata for {bvid}: {e}")

            # Check if content exists
            stmt = select(ContentItem).where(ContentItem.external_id == bvid)
            result = await self.session.execute(stmt)
            content = result.scalar_one_or_none()
            
            if not content:
                content = ContentItem(
                    author_id=author.id if author else None,
                    platform="bilibili",
                    external_id=bvid,
                    title=v["title"],
                    url=v["url"],
                    type="video",
                    content_quality="summary",
                    extra_data=v
                )
                self.session.add(content)
                await self.session.commit()
                await self.session.refresh(content)
                
                # 3. Process Content (Transcribe/Segment/Embed)
                await self.process_content(content)
            else:
                 # If content exists but quality is summary, retry to get full content
                if content.content_quality == 'summary':
                    logger.info(f"Content exists but quality is 'summary'. Retrying: {bvid}")
                    # Delete existing segments to avoid duplication
                    from sqlalchemy import delete
                    await self.session.execute(delete(Segment).where(Segment.content_id == content.id))
                    # We keep the content item but re-process
                    await self.session.commit()
                    
                    await self.process_content(content)
                else:
                    logger.info(f"Content already exists (quality={content.content_quality}): {bvid} - {v['title']}, skipping.")
        
        # NOTE: Author report generation is now manual.

    async def ingest_author(self, mid_or_url: str, limit: int = 10):
        """Ingest author and their recent videos"""
        # 1. Get Author Info
        info = await self.crawler.get_author_info(mid_or_url)
        mid = str(info["mid"])
        
        # Check if exists
        stmt = select(Author).where(Author.external_id == mid)
        result = await self.session.execute(stmt)
        author = result.scalar_one_or_none()
        
        stored_avatar_url = None
        if info.get("face"):
            stored_avatar_url = await self._store_author_avatar(info.get("face"), mid)

        if not author:
            author = Author(
                platform="bilibili",
                external_id=mid,
                name=info["name"],
                homepage_url=f"https://space.bilibili.com/{mid}",
                avatar_url=stored_avatar_url or info["face"]
            )
            self.session.add(author)
            await self.session.commit()
            await self.session.refresh(author)
            logger.info(f"Created author: {author.name}")
        else:
            if stored_avatar_url:
                author.avatar_url = stored_avatar_url
                self.session.add(author)
                await self.session.commit()
        
        # 2. Get Videos
        videos = await self.crawler.get_videos(mid_or_url, limit=limit)
        
        for v in videos:
            bvid = v["bvid"]
            # Check if content exists
            stmt = select(ContentItem).where(ContentItem.external_id == bvid)
            result = await self.session.execute(stmt)
            content = result.scalar_one_or_none()
            
            if not content:
                content = ContentItem(
                    author_id=author.id,
                    platform="bilibili",
                    external_id=bvid,
                    title=v["title"],
                    url=f"https://www.bilibili.com/video/{bvid}",
                    # duration=v.get("length", 0) # bilix might return duration in seconds or string
                    type="video",
                    content_quality="summary",
                    extra_data=v
                )
                self.session.add(content)
                await self.session.commit()
                await self.session.refresh(content)
                logger.info(f"Created content: {content.title}")
                
                # 3. Process Content (Transcribe/Segment/Embed)
                await self.process_content(content)
            else:
                 # If content exists but quality is summary, retry to get full content
                if content.content_quality == 'summary':
                    logger.info(f"Content exists but quality is 'summary'. Retrying: {bvid}")
                    # Delete existing segments to avoid duplication
                    from sqlalchemy import delete
                    await self.session.execute(delete(Segment).where(Segment.content_id == content.id))
                    # We keep the content item but re-process
                    await self.session.commit()
                    
                    await self.process_content(content)
                else:
                    logger.info(f"Content already exists (quality={content.content_quality}): {bvid} - {v['title']}, skipping.")
        
        # NOTE: Author report generation is now manual.

    async def process_content(self, content: ContentItem):
        """Fetch subtitles, segment, and embed"""
        logger.info(f"Processing content: {content.title}")
        
        try:
            v_info = await self.crawler.get_video_info(content.external_id)
            cid = v_info["cid"]
            
            # 1. Try Get subtitles
            subtitles = await self.crawler.get_subtitle(content.external_id, cid)
            
            # 2. Fallback: ASR
            if not subtitles:
                logger.info(f"No subtitles for {content.external_id}, trying ASR...")
                audio_path = await self.crawler.download_audio(content.external_id)
                if audio_path:
                    try:
                        # Upload to MinIO
                        object_name = f"{content.external_id}_{os.path.basename(audio_path)}"
                        # Note: We need await if upload is async, but MinIO client is sync. 
                        # We can run in executor if needed, but for MVP sync is fine or wrap it.
                        # Actually StorageService.upload_file is defined as async but calls sync minio.
                        await self.storage.upload_file(audio_path, object_name)
                        
                        transcription = await self.asr.transcribe(audio_path)
                        # Process transcription result
                        # OpenAI 'verbose_json' returns 'segments' list if supported by SiliconFlow
                        # or just 'text'.
                        # Let's handle both.
                        if hasattr(transcription, 'segments') and transcription.segments:
                            # Convert to our subtitle format
                            # segment has: id, seek, start, end, text, ...
                            for seg in transcription.segments:
                                subtitles.append({
                                    "from": seg.start,
                                    "to": seg.end,
                                    "content": seg.text
                                })
                        elif transcription.text:
                            # Just text, chunk it roughly? 
                            # Or treat as one big chunk.
                            logger.info("ASR returned plain text without segments.")
                            subtitles = [{
                                "from": 0,
                                "to": v_info.get("duration", 60),
                                "content": transcription.text
                            }]
                            
                    except Exception as asr_e:
                        logger.error(f"ASR failed for {content.external_id}: {asr_e}")
                    finally:
                        # Clean up audio file
                        if audio_path and os.path.exists(audio_path):
                            try:
                                os.remove(audio_path)
                                logger.info(f"Deleted local audio file: {audio_path}")
                            except Exception as rm_e:
                                logger.warning(f"Failed to delete {audio_path}: {rm_e}")
            
            # 3. Fallback: Description
            if not subtitles and v_info.get("desc"):
                logger.warning(f"No subtitles/ASR for {content.external_id}, using description.")
                subtitles = [{
                    "from": 0,
                    "to": v_info.get("duration", 60),
                    "content": f"[Description] {v_info.get('desc')}"
                }]
            
            if not subtitles:
                logger.warning(f"No content found for {content.external_id}")
                content.content_quality = "missing"
                self.session.add(content)
                await self.session.commit()
                return

            # Determine quality
            quality = "full"
            if len(subtitles) == 1 and subtitles[0]["content"].startswith("[Description]"):
                quality = "summary"
            
            # Update content quality
            content.content_quality = quality
            self.session.add(content)

            # Chunking Strategy
            chunks = self._create_chunks(subtitles)
            
            saved_segments = []
            for i, chunk in enumerate(chunks):
                text_content = chunk["text"]
                # Embedding
                if self.embedder:
                    vector = self.embedder.encode(text_content).tolist()
                else:
                    vector = [0.0] * 384 # Dummy
                
                segment = Segment(
                    content_id=content.id,
                    segment_index=i,
                    start_time_ms=int(chunk["from"] * 1000),
                    end_time_ms=int(chunk["to"] * 1000),
                    text=text_content,
                    embedding=vector
                )
                self.session.add(segment)
                saved_segments.append(segment)
            
            await self.session.commit()
            logger.info(f"Saved {len(saved_segments)} segments for {content.title} (Quality: {quality})")
            
            # NOTE: Summary generation is now manual.
            
        except Exception as e:
            logger.error(f"Error processing {content.external_id}: {e}")

    def _create_chunks(self, subtitles: List[Dict], target_length: int = 300) -> List[Dict]:
        """
        Merge subtitles into chunks.
        subtitles format: [{'from': 0.5, 'to': 2.5, 'content': 'hello'}, ...]
        """
        chunks = []
        current_chunk = {"from": 0.0, "to": 0.0, "text": ""}
        
        for sub in subtitles:
            # Init start time
            if not current_chunk["text"]:
                current_chunk["from"] = sub["from"]
            
            # Append text
            text = sub["content"]
            if current_chunk["text"]:
                current_chunk["text"] += " " + text
            else:
                current_chunk["text"] = text
                
            current_chunk["to"] = sub["to"]
            
            # Check length
            if len(current_chunk["text"]) >= target_length:
                chunks.append(current_chunk)
                current_chunk = {"from": 0.0, "to": 0.0, "text": ""}
                
        # Last chunk
        if current_chunk["text"]:
            chunks.append(current_chunk)
            
        return chunks

