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

    async def get_videos_from_page(self, url: str, limit: int = 0) -> Dict:
        """
        Navigate to a Bilibili page (Space or Video list) and extract video links + author info.
        Assumes the browser is already logged in or has access.
        limit: Max videos to return. 0 for all found.
        Returns: {"author": {...}, "videos": [...]}
        """
        if not self.browser:
            await self.connect()
            
        context = self.browser.contexts[0]
        page = await context.new_page()
        
        result = {"author": None, "videos": []}
        
        try:
            logger.info(f"Navigating to {url}...")
            await page.goto(url, wait_until="domcontentloaded")
            
            # Wait for lazy loading
            await asyncio.sleep(3)
            
            # 1. Try to extract Author Info (if on Space page)
            try:
                # Try multiple selectors for author name
                author_name_el = await page.query_selector("#h-name") or await page.query_selector(".nickname")
                author_face_el = await page.query_selector("#h-avatar") or await page.query_selector(".h-avatar img")
                
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
            
            # 2. Extract Videos (More precise selectors)
            # Try to find list items first
            # New Bilibili Space usually uses .bili-grid-video-card or .list-item
            # Update: Added .bili-video-card (general), .feed-card (dynamic)
            video_items = await page.query_selector_all(".bili-grid-video-card .bili-video-card, .bili-video-card, .list-item, .small-item, .cube-list li, .submit-video .small-item, .video-list .video-item, .feed-card")
            
            if not video_items:
                # Fallback to generic link search if specific structure not found
                logger.info("No list items found, falling back to link search...")
                video_items = await page.query_selector_all("a[href*='/video/BV']")

            videos = []
            seen = set()
            
            for el in video_items:
                if limit > 0 and len(videos) >= limit:
                    break
                
                # Check if el is a container or a link itself
                tag_name = await page.evaluate("el => el.tagName", el)
                
                # Initialize variables
                link_el = None
                title = ""
                
                # Strategy A: It's a Card Container (div/li)
                # This is the expected path for .bili-video-card
                if tag_name != "A":
                    # 1. Try to find title container (User provided structure)
                    # <div class="bili-video-card__title" title="..."> <a href="...">...</a> </div>
                    title_container = await el.query_selector(".bili-video-card__title")
                    
                    if title_container:
                        title = await title_container.get_attribute("title")
                        link_el = await title_container.query_selector("a")
                    
                    # 2. Fallback: Try generic title/link selectors inside card
                    if not link_el:
                        link_el = await el.query_selector("a.title") or await el.query_selector("a.cover") or await el.query_selector("a[href*='/video/BV']")
                    
                    # 3. Fallback: Try Image Alt text for title if still empty
                    if not title:
                        img_el = await el.query_selector("img")
                        if img_el:
                            title = await img_el.get_attribute("alt")
                            
                    # 4. Fallback: Try to find title in link text or title attribute
                    if not title and link_el:
                         title = await link_el.get_attribute("title") or await link_el.inner_text()

                # Strategy B: It's a Link (Fallback mode)
                else:
                    link_el = el
                    # For a direct link, title is usually the text or title attribute
                    title = await el.get_attribute("title") or await el.inner_text()
                    
                    # Try to find a parent that might contain the title if this is just a cover link
                    # (Skipping complex parent traversal for now to keep it simple, 
                    # assuming fallback captures title links too)

                # 2. Check for Charging Tag
                # <div class="bili-cover-card__tag charge-tag">
                # Only check if we are in a container. If we are just a link, checking for tag inside might be wrong
                # unless the link WRAPS the card (which happens).
                charge_tag = await el.query_selector(".charge-tag")
                
                if charge_tag:
                    txt = await charge_tag.inner_text()
                    if "充电" in txt:
                        logger.info(f"Skipping charging video (tag detected): {title.strip() if title else 'Unknown Title'}")
                        continue

                # 3. Finalize Video Object
                if not link_el:
                    continue
                    
                href = await link_el.get_attribute("href")
                if href and "/video/BV" in href:
                    # Clean bvid
                    parts = href.split("/video/")
                    if len(parts) > 1:
                        bvid = parts[1].split("/")[0].split("?")[0]
                        if bvid not in seen:
                            title_clean = title.strip() if title else ""
                            
                            # Secondary check for charging text in title
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
            
            result["videos"] = videos
            logger.info(f"Found {len(videos)} videos on page.")
            
        except Exception as e:
            logger.error(f"Error scraping page: {e}")
        finally:
            await page.close()
            
        return result

    async def close(self):
        # We don't close the browser itself as it's the user's local instance
        pass
