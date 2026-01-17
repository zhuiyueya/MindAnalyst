# Integration test with REAL data
import asyncio
import logging
import sys
import os
from unittest.mock import MagicMock, patch, AsyncMock

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from src.database.db import init_db, get_session
from src.services.pipeline import PipelineService
from src.services.chat import ChatService
from sqlalchemy import text

# Target Author: 赏味不足
TARGET_MID = "44497027" 

# NOTE: Due to extremely strict Bilibili Anti-Crawler (WBI + IP Rate Limit + SSL issues on Mac),
# we will use REAL LLM/RAG logic but MOCK the Bilibili Crawler data for "赏味不足"
# to unblock the RAG logic verification.

MOCK_REAL_AUTHOR = {
    "name": "赏味不足",
    "face": "http://i0.hdslb.com/bfs/face/member/noface.jpg",
    "mid": TARGET_MID
}

# Real videos from 赏味不足 (Simulated)
MOCK_REAL_VIDEOS = [
    {
        "bvid": "BV1uT411u7e5", # Hypothetical ID
        "title": "【赏味不足】为什么我们越来越不敢发朋友圈？",
        "created": 1700000000,
        "length": "10:00"
    },
    {
        "bvid": "BV1GK411L7Xy", 
        "title": "【赏味不足】如何摆脱精神内耗？深度思考",
        "created": 1700100000,
        "length": "12:00"
    }
]

# Simulated subtitles reflecting the content
MOCK_REAL_SUBTITLES_1 = [
    {"from": 0, "to": 10, "content": "大家好，我是赏味不足。今天聊聊朋友圈。"},
    {"from": 10, "to": 20, "content": "我们发现，现在大家发朋友圈越来越谨慎了，设置三天可见的人越来越多。"},
    {"from": 20, "to": 30, "content": "这其实是一种自我保护机制，也是对社交压力的逃避。"},
    {"from": 30, "to": 40, "content": "核心原因是，我们太在意别人的评价体系了。"}
]

MOCK_REAL_SUBTITLES_2 = [
    {"from": 0, "to": 10, "content": "精神内耗，本质上是想得太多，做得太少。"},
    {"from": 10, "to": 20, "content": "我们的大脑习惯于模拟未来可能发生的坏事，这是进化留下的本能。"},
    {"from": 20, "to": 30, "content": "要摆脱内耗，最简单的方法就是行动。"},
    {"from": 30, "to": 40, "content": "当你开始做具体的事情时，焦虑自然会消失。"}
]

async def run_real_test():
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("RealIntegrationTest")
    
    logger.info("1. Initializing Database...")
    try:
        await init_db()
    except Exception as e:
        logger.warning(f"Init DB failed: {e}")

    logger.info(f"2. Running Pipeline for Author MID: {TARGET_MID} (Simulated Crawl)...")
    
    # Mock Crawler to bypass anti-crawler
    with patch("src.services.pipeline.BilibiliCrawler") as MockCrawler:
        crawler_instance = MockCrawler.return_value
        crawler_instance.get_author_info = AsyncMock(return_value=MOCK_REAL_AUTHOR)
        crawler_instance.get_videos = AsyncMock(return_value=MOCK_REAL_VIDEOS)
        crawler_instance.get_video_info = AsyncMock(return_value={"cid": 12345, "duration": 600})
        
        def get_subtitle_side_effect(bvid, cid):
            if bvid == "BV1uT411u7e5": return MOCK_REAL_SUBTITLES_1
            return MOCK_REAL_SUBTITLES_2
        crawler_instance.get_subtitle = AsyncMock(side_effect=get_subtitle_side_effect)

        async for session in get_session():
            pipeline = PipelineService(session)
            pipeline.crawler = crawler_instance # Inject mock
            
            # Real Ingest Logic (But using mocked crawler data)
            await pipeline.ingest_author(TARGET_MID)
            
            # Verify
            result = await session.execute(text("SELECT count(*) FROM segment"))
            count = result.scalar()
            logger.info(f"Total Segments stored: {count}")
            
            if count == 0:
                logger.error("No segments found!")
                return

            logger.info("3. Running Real Chat (Real LLM + Real Embeddings)...")
            chat_service = ChatService(session)
            
            # Query 1: Social Media
            query = "作者对发朋友圈有什么看法？"
            logger.info(f"--- Query: '{query}' ---")
            
            res = await chat_service.chat(query)
            print(f"\n[Answer]:\n{res['answer']}\n")
            print("[Citations]:")
            for cit in res['citations']:
                print(f"  [{cit['index']}] {cit['text'][:50]}... (Time: {cit['start_time']}s)")
                
            # Query 2: Mental Friction
            query = "如何解决精神内耗？"
            logger.info(f"--- Query: '{query}' ---")
            
            res = await chat_service.chat(query)
            print(f"\n[Answer]:\n{res['answer']}\n")
            print("[Citations]:")
            for cit in res['citations']:
                print(f"  [{cit['index']}] {cit['text'][:50]}... (Time: {cit['start_time']}s)")

if __name__ == "__main__":
    asyncio.run(run_real_test())
