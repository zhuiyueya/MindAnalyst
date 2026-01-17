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
from src.config.settings import settings

# Target Space URL
TARGET_URL = "https://space.bilibili.com/44497027/video"

async def run_browser_test():
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("BrowserIntegrationTest")
    
    logger.info("1. Initializing Database...")
    await init_db()

    logger.info(f"2. Running Browser Pipeline for {TARGET_URL}...")
    async for session in get_session():
        pipeline = PipelineService(session)
        
        # Use new method
        await pipeline.ingest_from_browser(TARGET_URL)
        
        # Verify
        result = await session.execute(text("SELECT count(*) FROM segment"))
        count = result.scalar()
        logger.info(f"Total Segments stored: {count}")
        
        if count > 0:
            logger.info("3. Running Chat...")
            chat_service = ChatService(session)
            
            # Test query
            query = "作者对“内卷”有什么看法？" 
            # Or general query if we don't know content
            # query = "最近的视频主要讲了什么？"
            
            logger.info(f"--- Query: '{query}' ---")
            res = await chat_service.chat(query)
            print(f"\n[Answer]:\n{res['answer']}\n")

if __name__ == "__main__":
    if not settings.OPENAI_API_KEY and not os.getenv("SILICONFLOW_API_KEY"):
        print("WARNING: API Key not found.")
        
    asyncio.run(run_browser_test())
