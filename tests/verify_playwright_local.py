import asyncio
from playwright.async_api import async_playwright
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("PlaywrightLocalTest")

async def test_connect_existing_chrome(mid: str):
    async with async_playwright() as p:
        try:
            # Connect to the local Chrome instance launched with --remote-debugging-port=9222
            browser = await p.chromium.connect_over_cdp("http://localhost:9222")
            logger.info("Successfully connected to local Chrome!")
            
            # Get the current context (or create a new page in it)
            context = browser.contexts[0]
            page = await context.new_page()
            
            url = f"https://space.bilibili.com/{mid}/video"
            logger.info(f"Navigating to {url}...")
            
            await page.goto(url, wait_until="domcontentloaded")
            logger.info("Page loaded.")
            
            # Wait a bit for JS rendering
            await asyncio.sleep(5)
            
            # Scroll to trigger lazy load
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(2)
            
            # Try to grab video titles
            # Debug: print some links to see structure
            links = await page.query_selector_all("a")
            logger.info(f"Total links on page: {len(links)}")
            
            videos = []
            seen = set()
            
            # Broader search for any video link
            for el in links:
                href = await el.get_attribute("href")
                if href and "/video/BV" in href:
                    # Clean bvid
                    parts = href.split("/video/")
                    if len(parts) > 1:
                        bvid = parts[1].split("/")[0].split("?")[0]
                        if bvid not in seen:
                            title = await el.get_attribute("title") or await el.inner_text()
                            if title and len(title.strip()) > 0:
                                seen.add(bvid)
                                videos.append({"bvid": bvid, "title": title.strip()})
            
            logger.info(f"Captured {len(videos)} unique videos:")
            for v in videos[:5]:
                logger.info(v)
                
            await page.close()
            # Do NOT close browser, as it is the user's local browser
            # await browser.close() 
            
        except Exception as e:
            logger.error(f"Failed to connect or scrape: {e}")
            logger.info("Make sure Chrome is running with: --remote-debugging-port=9222")

if __name__ == "__main__":
    # 赏味不足 MID
    mid = "44497027"
    asyncio.run(test_connect_existing_chrome(mid))
