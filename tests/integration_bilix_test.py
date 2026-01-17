import asyncio
import logging
import sys
import os
from sqlalchemy import text

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from src.database.db import init_db, get_session
from src.services.pipeline import PipelineService
from src.services.chat import ChatService

# Target Author: 赏味不足
# Using Space URL (Blocked by Anti-Crawler)
# TARGET_URL = "https://space.bilibili.com/44497027"
# Using Single Video URL (Works)
TARGET_URL = "https://www.bilibili.com/video/BV1AM4y1E7zQ"

async def run_test():
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("IntegrationTest")
    
    logger.info("1. Initializing Database...")
    await init_db()

    logger.info(f"2. Running Pipeline for {TARGET_URL} (Limit 2)...")
    async for session in get_session():
        pipeline = PipelineService(session)
        
        # Ingest with limit=2 (Will fetch single video)
        await pipeline.ingest_author(TARGET_URL, limit=2)
        
        # Verify
        result = await session.execute(text("SELECT count(*) FROM segment"))
        count = result.scalar()
        logger.info(f"Total Segments stored: {count}")
        
        if count > 0:
            logger.info("3. Running Chat...")
            chat_service = ChatService(session)
            
            query = "什么是电池思维？"
            logger.info(f"--- Query: '{query}' ---")
            
            res = await chat_service.chat(query)
            print(f"\n[Answer]:\n{res['answer']}\n")
            print("[Citations]:")
            for cit in res['citations']:
                print(f"  [{cit['index']}] {cit['text'][:50]}... (Time: {cit['start_time']}s)")

if __name__ == "__main__":
    # Ensure settings are loaded
    from src.config.settings import settings
    if not settings.OPENAI_API_KEY and not os.getenv("SILICONFLOW_API_KEY"):
        print("WARNING: API Key not found. ASR/Chat might fail.")
        
    asyncio.run(run_test())
