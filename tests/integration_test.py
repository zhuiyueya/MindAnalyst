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

    logger.info(f"2. Running Pipeline for Author MID: {TARGET_MID} (Semi-Real Mode)...")
    
    # We patch `get_videos` because the "List API" is unstable/blocked.
    # But we let `get_video_info` and `get_subtitle` run for REAL to fetch description/subs.
    with patch("src.services.pipeline.BilibiliCrawler.get_videos", new_callable=AsyncMock) as mock_get_videos:
        # Provide REAL BVIDs manually
        mock_get_videos.return_value = [
            {
                "bvid": "BV1AM4y1E7zQ", 
                "title": "拒绝电池思维——不要寻找最优解，而是寻找多个可执行的解",
                "created": 1700000000,
                "length": "10:00"
            }
        ]
        
        # We also need to patch get_author_info if it fails, but let's try letting it run or mock it if needed.
        # For stability, let's mock author info too, but let video content be real.
        with patch("src.services.pipeline.BilibiliCrawler.get_author_info", new_callable=AsyncMock) as mock_get_author:
            mock_get_author.return_value = {
                "name": "赏味不足 (Real Content Test)",
                "face": "http://i0.hdslb.com/bfs/face/member/noface.jpg",
                "mid": TARGET_MID
            }

            async for session in get_session():
                pipeline = PipelineService(session)
                # Crawler is NOT fully mocked, only get_videos and get_author_info are patched.
                # get_video_info and get_subtitle will call the REAL BilibiliCrawler methods.
                
                await pipeline.ingest_author(TARGET_MID)
                
                # Verify
                result = await session.execute(text("SELECT count(*) FROM segment"))
                count = result.scalar()
                logger.info(f"Total Segments stored: {count}")
                
                if count == 0:
                    logger.error("No segments found!")
                    return

                logger.info("3. Running Real Chat...")
                chat_service = ChatService(session)
                
                # Query based on the video description we likely fetched
                query = "什么是电池思维？"
                logger.info(f"--- Query: '{query}' ---")
                
                res = await chat_service.chat(query)
                print(f"\n[Answer]:\n{res['answer']}\n")
                print("[Citations]:")
                for cit in res['citations']:
                    print(f"  [{cit['index']}] {cit['text'][:50]}... (Time: {cit['start_time']}s)")

if __name__ == "__main__":
    asyncio.run(run_real_test())
