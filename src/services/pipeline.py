import asyncio
from typing import List, Dict
import os
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from src.models.models import Author, ContentItem, Segment, Summary
from src.crawler.bilix_crawler import BilixCrawler
from src.crawler.browser_crawler import BrowserCrawler
from src.services.asr import ASRService
from src.database.db import get_session
from sentence_transformers import SentenceTransformer
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PipelineService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.crawler = BilixCrawler()
        self.browser_crawler = None # Lazy init
        self.asr = ASRService()
        
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

    async def ingest_from_browser(self, url: str):
        """
        Use BrowserCrawler to get videos from a page (e.g. Space) and ingest them.
        """
        if not self.browser_crawler:
            self.browser_crawler = BrowserCrawler()
            
        # 1. Scrape Videos
        videos = await self.browser_crawler.get_videos_from_page(url)
        
        if not videos:
            logger.warning(f"No videos found on {url}")
            return
            
        # 2. Process each video using existing logic
        # For simplicity, we create a dummy Author or try to fetch Author info from first video
        
        # Get Author Info from first video to create Author record
        first_vid = videos[0]
        try:
            # Try to get author info via crawler
            logger.info(f"Fetching author info for BVID: {first_vid['bvid']}")
            author_info = await self.crawler.get_author_info(first_vid['bvid'])
            
            # Create/Get Author
            stmt = select(Author).where(Author.external_id == str(author_info["mid"]))
            result = await self.session.execute(stmt)
            author = result.scalar_one_or_none()
            
            if not author:
                author = Author(
                    platform="bilibili",
                    external_id=str(author_info["mid"]),
                    name=author_info["name"],
                    homepage_url=f"https://space.bilibili.com/{author_info['mid']}",
                    avatar_url=author_info["face"]
                )
                self.session.add(author)
                await self.session.commit()
                await self.session.refresh(author)
                logger.info(f"Created author: {author.name}")
                
        except Exception as e:
            logger.error(f"Failed to get author info: {e}. Creating dummy author.")
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
                    extra_data=v
                )
                self.session.add(content)
                await self.session.commit()
                await self.session.refresh(content)
                
                # Process Content (ASR/Embed)
                await self.process_content(content)
                
    async def ingest_author(self, mid_or_url: str, limit: int = 10):
        """Ingest author and their recent videos"""
        # 1. Get Author Info
        info = await self.crawler.get_author_info(mid_or_url)
        mid = str(info["mid"])
        
        # Check if exists
        stmt = select(Author).where(Author.external_id == mid)
        result = await self.session.execute(stmt)
        author = result.scalar_one_or_none()
        
        if not author:
            author = Author(
                platform="bilibili",
                external_id=mid,
                name=info["name"],
                homepage_url=f"https://space.bilibili.com/{mid}",
                avatar_url=info["face"]
            )
            self.session.add(author)
            await self.session.commit()
            await self.session.refresh(author)
            logger.info(f"Created author: {author.name}")
        
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
                    extra_data=v
                )
                self.session.add(content)
                await self.session.commit()
                await self.session.refresh(content)
                logger.info(f"Created content: {content.title}")
                
                # 3. Process Content (Transcribe/Segment/Embed)
                await self.process_content(content)

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
                        if os.path.exists(audio_path):
                            os.remove(audio_path)
            
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
                return

            # Chunking Strategy
            segments = self._create_chunks(subtitles)
            
            for i, chunk in enumerate(segments):
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
            
            await self.session.commit()
            logger.info(f"Saved {len(segments)} segments for {content.title}")
            
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

    async def generate_summary(self, content: ContentItem, segments: List[Segment]):
        # TODO: Call LLM API
        pass
