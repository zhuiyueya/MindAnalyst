import asyncio
from playwright.async_api import async_playwright, Page, Browser
from typing import List, Dict, Optional
import logging
import os
import re

logger = logging.getLogger(__name__)

class BrowserCrawler:
    """
    Crawler that launches a new Chromium instance or connects to an existing one.
    Defaults to launching a new headful browser for stability.
    """
    def __init__(self, headless: bool = False):
        self.browser: Optional[Browser] = None
        self.playwright = None
        self.headless = headless
        
    async def connect(self):
        """Launch a new browser instance"""
        try:
            self.playwright = await async_playwright().start()
            # Launch new browser instead of connecting to existing CDP
            # This avoids local Chrome state corruption issues
            self.browser = await self.playwright.chromium.launch(
                headless=self.headless,
                args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
            )
            logger.info(f"Launched new browser (headless={self.headless})")
        except Exception as e:
            logger.error(f"Failed to launch browser: {e}")
            raise

    async def get_videos_from_page(self, url: str, limit: int = 0) -> Dict:
        """
        Navigate to a Bilibili page (Space or Video list) and extract video links + author info.
        Assumes the browser is already logged in or has access.
        limit: Max videos to return. 0 for all found.
        Returns: {"author": {...}, "videos": [...]}
        """
        if not self.browser:
            await self.connect()
            
        # Handle context creation for launch() mode
        if not self.browser.contexts:
            context = await self.browser.new_context()
        else:
            context = self.browser.contexts[0]
            
        page = await context.new_page()
        
        result = {"author": None, "videos": []}
        
        try:
            # Optimization: If URL is a space root, go directly to video list
            # This avoids double navigation (Home -> Video List)
            if "/space.bilibili.com/" in url and "/video" not in url:
                if "?" in url:
                    url = url.split("?")[0]
                if not url.endswith("/"):
                    url += "/"
                url += "video"
                logger.info(f"Auto-appending /video to space URL: {url}")

            logger.info(f"Navigating to {url}...")
            await page.goto(url, wait_until="domcontentloaded")
            
            # Wait for lazy loading
            await asyncio.sleep(3)
            
            # 1. Try to extract Author Info (if on Space page)
            try:
                # Try multiple selectors for author name
                author_name_el = await page.query_selector("#h-name") or await page.query_selector(".nickname") or await page.query_selector(".h-name")
                author_face_el = await page.query_selector("#h-avatar") or await page.query_selector(".h-avatar img") or await page.query_selector(".h-avatar")
                
                if author_name_el:
                    name = await author_name_el.inner_text()
                    face = await author_face_el.get_attribute("src") if author_face_el else ""
                    # Extract mid from url if possible
                    mid = url.split("space.bilibili.com/")[1].split("/")[0] if "space.bilibili.com" in url else ""
                    
                    result["author"] = {
                        "mid": mid,
                        "name": name.strip(),
                        "face": face,
                        "url": f"https://space.bilibili.com/{mid}"
                    }
                    logger.info(f"Found author: {name}")
            except Exception as ae:
                logger.warning(f"Could not extract author info: {ae}")

            # Scroll
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(2)
            
            # 2. Extract Videos (Pagination Loop)
            videos = []
            seen = set()
            page_num = 1
            
            # Auto-redirect removed (handled at start)
            pass
            
            while True:
                logger.info(f"Scraping page {page_num}...")
                
                # Scroll to bottom to trigger lazy loading
                for _ in range(3):
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await asyncio.sleep(1)
                
                # Extract from current page
                video_items = await page.query_selector_all(".bili-grid-video-card .bili-video-card, .bili-video-card, .list-item, .small-item, .cube-list li, .submit-video .small-item, .video-list .video-item, .feed-card")
                
                if not video_items:
                    # Fallback to generic link search
                    logger.info("No list items found on current page, falling back to link search...")
                    video_items = await page.query_selector_all("a[href*='/video/BV']")

                current_page_new_count = 0
                for el in video_items:
                    if limit > 0 and len(videos) >= limit:
                        break
                    
                    # Check if el is a container or a link itself
                    tag_name = await page.evaluate("el => el.tagName", el)
                    
                    # Initialize variables
                    link_el = None
                    title = ""
                    
                    # Strategy A: It's a Card Container (div/li)
                    if tag_name != "A":
                        # 1. Try to find title container
                        title_container = await el.query_selector(".bili-video-card__title")
                        
                        if title_container:
                            title = await title_container.get_attribute("title")
                            link_el = await title_container.query_selector("a")
                        
                        # 2. Fallback: Try generic title/link selectors inside card
                        if not link_el:
                            link_el = await el.query_selector("a.title") or await el.query_selector("a.cover") or await el.query_selector("a[href*='/video/BV']")
                        
                        # 3. Fallback: Try Image Alt text for title
                        if not title:
                            img_el = await el.query_selector("img")
                            if img_el:
                                title = await img_el.get_attribute("alt")
                                
                        # 4. Fallback: Try to find title in link text or title attribute
                        if not title and link_el:
                             title = await link_el.get_attribute("title") or await link_el.inner_text()

                    # Strategy B: It's a Link
                    else:
                        link_el = el
                        title = await el.get_attribute("title") or await el.inner_text()

                    # Check for Charging Tag (Exclude premium videos)
                    # Need to check inside 'el' if it's a container
                    if tag_name != "A":
                        charge_tag = await el.query_selector(".charge-tag")
                        if charge_tag:
                            txt = await charge_tag.inner_text()
                            if "充电" in txt:
                                continue
                        
                    # Exclude if title contains charging keywords
                    if title and "充电专属" in title:
                        continue

                    # Finalize Video Object
                    if not link_el:
                        continue
                        
                    href = await link_el.get_attribute("href")
                    if href and "/video/BV" in href:
                        parts = href.split("/video/")
                        if len(parts) > 1:
                            bvid = parts[1].split("/")[0].split("?")[0]
                            if bvid not in seen:
                                title_clean = title.strip() if title else ""
                                
                                if "充电专属" in title_clean:
                                    continue
                                    
                                if title_clean and len(title_clean) > 0:
                                    seen.add(bvid)
                                    videos.append({
                                        "bvid": bvid, 
                                        "title": title_clean,
                                        "url": f"https://www.bilibili.com/video/{bvid}"
                                    })
                                    current_page_new_count += 1
                
                logger.info(f"Page {page_num}: Found {current_page_new_count} new videos. Total: {len(videos)}")

                # Check limit
                if limit > 0 and len(videos) >= limit:
                    logger.info(f"Reached limit {limit}. Stopping.")
                    break
                
                # Check if we are stuck (no new videos found on this page despite navigation)
                # But wait, maybe the page just has old videos? 
                # If we are strictly paging, we should see new videos unless we are at end.
                # If current_page_new_count == 0, it likely means we reached end or all on this page were seen.
                # However, scraping multiple pages might have duplicates? No, usually distinct.
                # Let's trust the 'Next' button state mostly.
                
                # Try to go to next page
                next_btn = None
                # Try strict selector based on user feedback
                # <button class="vui_button ... vui_pagenation--btn-side">下一页</button>
                side_btns = await page.query_selector_all("button.vui_pagenation--btn-side")
                
                for btn in side_btns:
                    text = await btn.inner_text()
                    is_disabled = await btn.get_attribute("disabled")
                    # If disabled attribute exists (even empty string), it is disabled.
                    # get_attribute returns None if missing.
                    if "下一页" in text and is_disabled is None:
                        next_btn = btn
                        break
                
                if next_btn:
                    logger.info("Navigating to next page...")
                    await next_btn.click()
                    page_num += 1
                    await asyncio.sleep(5) # Wait for load
                else:
                    logger.info("No next page or reached end.")
                    break
        
            result["videos"] = videos
            logger.info(f"Found {len(videos)} videos on page.")
            
        except Exception as e:
            logger.error(f"Error scraping page: {e}")
        finally:
            await page.close()
            
        return result

    async def close(self):
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
