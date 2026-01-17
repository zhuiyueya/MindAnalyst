import asyncio
from typing import List, Dict
import os
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from src.models.models import Author, ContentItem, Segment, Summary
from src.crawler.bilibili import BilibiliCrawler
from src.database.db import get_session
from sentence_transformers import SentenceTransformer
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PipelineService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.crawler = BilibiliCrawler()
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

    async def ingest_author(self, mid: str):
        """Ingest author and their recent videos"""
        # 1. Get Author Info
        info = await self.crawler.get_author_info(mid)
        
        # Check if exists
        stmt = select(Author).where(Author.external_id == str(mid))
        result = await self.session.execute(stmt)
        author = result.scalar_one_or_none()
        
        if not author:
            author = Author(
                platform="bilibili",
                external_id=str(mid),
                name=info["name"],
                homepage_url=f"https://space.bilibili.com/{mid}",
                avatar_url=info["face"]
            )
            self.session.add(author)
            await self.session.commit()
            await self.session.refresh(author)
            logger.info(f"Created author: {author.name}")
        
        # 2. Get Videos (Top 10 for MVP)
        videos = await self.crawler.get_videos(mid, page=1, page_size=10)
        
        for v in videos:
            bvid = v["bvid"]
            # Check if content exists
            stmt = select(ContentItem).where(ContentItem.external_id == bvid)
            result = await self.session.execute(stmt)
            content = result.scalar_one_or_none()
            
            if not content:
                # Need detailed info for duration etc.
                # v_info = await self.crawler.get_video_info(bvid) # Optional
                content = ContentItem(
                    author_id=author.id,
                    platform="bilibili",
                    external_id=bvid,
                    title=v["title"],
                    url=f"https://www.bilibili.com/video/{bvid}",
                    # duration=v_info["duration"]
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
        
        # Get CID (usually from extra_data or fetch info)
        # For simple video list, we might not have cid. Fetch info.
        try:
            v_info = await self.crawler.get_video_info(content.external_id)
            cid = v_info["cid"]
            
            # Get subtitles
            subtitles = await self.crawler.get_subtitle(content.external_id, cid)
            
            if not subtitles:
                logger.warning(f"No subtitles for {content.external_id}")
                return

            # Chunking Strategy (Simple MVP: Merge lines until ~500 chars)
            segments = self._create_chunks(subtitles)
            
            for i, chunk in enumerate(segments):
                text_content = chunk["text"]
                # Embedding
                if self.embedder:
                    vector = self.embedder.encode(text_content).tolist()
                else:
                    vector = [0.0] * 768 # Dummy
                
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
            
            # 4. Generate Summary (Mock for now, or call LLM)
            # await self.generate_summary(content, segments)
            
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
