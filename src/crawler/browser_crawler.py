import logging
import asyncio
from typing import List, Dict, Optional
from playwright.async_api import async_playwright, Page, Browser

logger = logging.getLogger(__name__)

class BrowserCrawler:
    """
    Crawler that connects to an existing local Chrome instance to bypass anti-crawler protections.
    Requires Chrome to be started with: --remote-debugging-port=9222
    """
    def __init__(self, cdp_url: str = "http://localhost:9222"):
        self.cdp_url = cdp_url
        self.browser: Optional[Browser] = None
        
    async def connect(self):
        """Connect to local browser"""
        try:
            p = await async_playwright().start()
            self.browser = await p.chromium.connect_over_cdp(self.cdp_url)
            logger.info(f"Connected to browser at {self.cdp_url}")
        except Exception as e:
            logger.error(f"Failed to connect to browser: {e}")
            raise ConnectionError(f"Could not connect to Chrome at {self.cdp_url}. Make sure it is running with --remote-debugging-port=9222")

    async def get_videos_from_page(self, url: str, limit: int = 0) -> List[Dict]:
        """
        Navigate to a Bilibili page (Space or Video list) and extract video links.
        Assumes the browser is already logged in or has access.
        limit: Max videos to return. 0 for all found.
        """
        if not self.browser:
            await self.connect()
            
        context = self.browser.contexts[0]
        page = await context.new_page()
        
        videos = []
        try:
            logger.info(f"Navigating to {url}...")
            await page.goto(url, wait_until="domcontentloaded")
            
            # Wait for lazy loading
            await asyncio.sleep(3)
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(2)
            
            # Extract videos
            links = await page.query_selector_all("a")
            seen = set()
            
            for el in links:
                if limit > 0 and len(videos) >= limit:
                    break
                    
                href = await el.get_attribute("href")
                if href and "/video/BV" in href:
                    # Clean bvid
                    parts = href.split("/video/")
                    if len(parts) > 1:
                        bvid = parts[1].split("/")[0].split("?")[0]
                        if bvid not in seen:
                            title = await el.get_attribute("title") or await el.inner_text()
                            title_clean = title.strip()
                            
                            # Filter out charging videos
                            if "充电专属" in title_clean:
                                logger.info(f"Skipping charging video: {bvid}")
                                continue
                                
                            if title_clean and len(title_clean) > 0:
                                seen.add(bvid)
                                videos.append({
                                    "bvid": bvid, 
                                    "title": title_clean,
                                    "url": f"https://www.bilibili.com/video/{bvid}"
                                })
            
            logger.info(f"Found {len(videos)} videos on page.")
            
        except Exception as e:
            logger.error(f"Error scraping page: {e}")
        finally:
            await page.close()
            
        return videos

    async def close(self):
        # We don't close the browser itself as it's the user's local instance
        pass
