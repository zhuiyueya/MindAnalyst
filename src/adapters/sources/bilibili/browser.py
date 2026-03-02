import asyncio
from dataclasses import dataclass
from playwright.async_api import async_playwright, Browser, BrowserContext, ElementHandle, Page, Playwright
from typing import List, Optional, Sequence
import logging

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AuthorInfo:
    """作者信息"""

    mid: str
    name: str
    face: str
    url: str


@dataclass(frozen=True, slots=True)
class VideoInfo:
    """视频信息"""

    bvid: str
    title: str
    url: str


@dataclass(frozen=True, slots=True)
class ScrapePageResult:
    """页面爬取结果"""

    author: Optional[AuthorInfo]
    videos: List[VideoInfo]

class BrowserCrawler:
    """
    启动一个新的 Chromium 实例，用于页面爬取。
    默认使用可视化模式（headful）以提升稳定性。
    """
    def __init__(self, headless: bool = False):
        self.browser: Optional[Browser] = None
        self.playwright: Optional[Playwright] = None
        self.headless = headless
        
    async def connect(self):
        """启动一个新的浏览器实例"""
        try:
            self.playwright = await async_playwright().start()
            # 优先使用系统已安装的 Chrome（通常比 Playwright 缓存的 CFT/Chromium 更稳定）
            try:
                self.browser = await self.playwright.chromium.launch(
                    channel="chrome",
                    headless=self.headless,
                    args=["--disable-blink-features=AutomationControlled"],
                )
            except Exception as e:
                logger.warning(f"Failed to launch system Chrome, falling back to bundled chromium: {e}")
                # 直接启动 Playwright 管理的 Chromium
                self.browser = await self.playwright.chromium.launch(
                    headless=self.headless,
                    args=["--disable-blink-features=AutomationControlled"],
                )
            logger.info(f"Launched new browser (headless={self.headless})")
        except Exception as e:
            logger.error(f"Failed to launch browser: {e}")
            raise

    async def _get_context(self) -> BrowserContext:
        if not self.browser:
            await self.connect()

        if not self.browser:
            raise RuntimeError("浏览器启动失败：browser 为空")

        # 处理 launch() 模式下的 context 创建
        if not self.browser.contexts:
            return await self.browser.new_context()

        return self.browser.contexts[0]

    async def _new_page(self) -> Page:
        context = await self._get_context()
        return await context.new_page()

    def _normalize_url(self, url: str) -> str:
        # 若是 space 根路径，自动跳转到视频列表页，避免双重导航（主页 -> 视频页）
        if "/space.bilibili.com/" in url and "/video" not in url:
            if "?" in url:
                url = url.split("?")[0]
            if not url.endswith("/"):
                url += "/"
            url += "video"
            logger.info(f"Auto-appending /video to space URL: {url}")

        return url

    async def _initial_load(self, page: Page, url: str) -> None:
        logger.info(f"Navigating to {url}...")
        await page.goto(url, wait_until="domcontentloaded")

        # 等待懒加载
        await asyncio.sleep(3)

    async def _extract_author(self, page: Page, url: str) -> Optional[AuthorInfo]:
        # 1. 尝试提取作者信息（空间页）
        try:
            # 作者名称：多 selector 兜底
            author_name_el = (
                await page.query_selector("#h-name")
                or await page.query_selector(".nickname")
                or await page.query_selector(".h-name")
            )
            author_face_el = (
                await page.query_selector("#h-avatar")
                or await page.query_selector(".h-avatar img")
                or await page.query_selector(".b-avatar img")
                or await page.query_selector(".b-avatar__layer__res img")
                or await page.query_selector("img[data-onload='onAvtSrcLoad']")
                or await page.query_selector(".h-avatar")
            )

            if not author_name_el:
                return None

            name = await author_name_el.inner_text()
            face = ""
            if author_face_el:
                face_attr = await author_face_el.get_attribute("src")
                if face_attr:
                    face = face_attr
                else:
                    nested_img = await author_face_el.query_selector("img")
                    if nested_img:
                        nested_src = await nested_img.get_attribute("src")
                        if nested_src:
                            face = nested_src

            if face.startswith("//"):
                face = f"https:{face}"

            # 尽量从 url 推断 mid
            mid = url.split("space.bilibili.com/")[1].split("/")[0] if "space.bilibili.com" in url else ""

            author = AuthorInfo(
                mid=mid,
                name=name.strip(),
                face=face,
                url=f"https://space.bilibili.com/{mid}",
            )
            logger.info(f"Found author: {author.name}")
            return author
        except Exception as ae:
            logger.warning(f"Could not extract author info: {ae}")
            return None

    async def _scroll_to_bottom(self, page: Page, times: int, sleep_s: float) -> None:
        for _ in range(times):
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(sleep_s)

    async def _select_video_items(self, page: Page) -> Sequence[ElementHandle]:
        # 从当前页提取视频条目
        video_items = await page.query_selector_all(
            ".bili-grid-video-card .bili-video-card, .bili-video-card, .list-item, .small-item, .cube-list li, .submit-video .small-item, .video-list .video-item, .feed-card"
        )

        if not video_items:
            # 兜底：直接查找 BV 链接
            logger.info("No list items found on current page, falling back to link search...")
            video_items = await page.query_selector_all("a[href*='/video/BV']")

        return video_items

    async def _parse_video_item(self, page: Page, el: ElementHandle) -> Optional[VideoInfo]:
        # 判断元素本身是容器还是链接
        tag_name = await page.evaluate("el => el.tagName", el)

        link_el: Optional[ElementHandle] = None
        title = ""

        # 策略 A：容器卡片
        if tag_name != "A":
            # 1) 尝试标题容器
            title_container = await el.query_selector(".bili-video-card__title")
            if title_container:
                title_attr = await title_container.get_attribute("title")
                if title_attr:
                    title = title_attr
                link_el = await title_container.query_selector("a")

            # 2) 兜底：通用链接 selector
            if not link_el:
                link_el = (
                    await el.query_selector("a.title")
                    or await el.query_selector("a.cover")
                    or await el.query_selector("a[href*='/video/BV']")
                )

            # 3) 兜底：图片 alt
            if not title:
                img_el = await el.query_selector("img")
                if img_el:
                    alt = await img_el.get_attribute("alt")
                    if alt:
                        title = alt

            # 4) 兜底：链接文本或 title
            if not title and link_el:
                title_attr2 = await link_el.get_attribute("title")
                if title_attr2:
                    title = title_attr2
                else:
                    title = await link_el.inner_text()
        else:
            # 策略 B：元素本身是链接
            link_el = el
            title_attr3 = await el.get_attribute("title")
            if title_attr3:
                title = title_attr3
            else:
                title = await el.inner_text()

        # 充电标签过滤（仅容器需要检查内部标签）
        if tag_name != "A":
            charge_tag = await el.query_selector(".charge-tag")
            if charge_tag:
                txt = await charge_tag.inner_text()
                if "充电" in txt:
                    return None

        # 标题关键字过滤
        if title and "充电专属" in title:
            return None

        if not link_el:
            return None

        href = await link_el.get_attribute("href")
        if not href or "/video/BV" not in href:
            return None

        parts = href.split("/video/")
        if len(parts) <= 1:
            return None

        bvid = parts[1].split("/")[0].split("?")[0]
        title_clean = title.strip() if title else ""

        if title_clean and "充电专属" in title_clean:
            return None

        if not title_clean:
            return None

        return VideoInfo(bvid=bvid, title=title_clean, url=f"https://www.bilibili.com/video/{bvid}")

    async def _find_next_button(self, page: Page) -> Optional[ElementHandle]:
        # <button class="vui_button ... vui_pagenation--btn-side">下一页</button>
        side_btns = await page.query_selector_all("button.vui_pagenation--btn-side")
        for btn in side_btns:
            text = await btn.inner_text()
            is_disabled = await btn.get_attribute("disabled")
            # disabled 属性存在（即使为空字符串）也代表不可用；缺失则为 None
            if "下一页" in text and is_disabled is None:
                return btn

        return None

    async def get_videos_from_page(self, url: str, limit: int = 0) -> ScrapePageResult:
        """
        访问 B 站页面（空间页/视频列表页），提取视频链接与作者信息。
        默认假设浏览器已登录或具备访问权限。
        limit: 最大返回视频数；0 表示不限制。
        返回：ScrapePageResult(author=..., videos=[...])
        """

        async def _scrape_once() -> ScrapePageResult:
            page = await self._new_page()
            author: Optional[AuthorInfo] = None
            videos: List[VideoInfo] = []

            try:
                normalized_url = self._normalize_url(url)
                await self._initial_load(page, normalized_url)

                author = await self._extract_author(page, normalized_url)

                # 初次滚动
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(2)

                # 2. 提取视频（分页循环）
                seen: set[str] = set()
                page_num = 1

                while True:
                    logger.info(f"Scraping page {page_num}...")

                    # 滚动触发懒加载（ 3 次，每次 1 秒）
                    await self._scroll_to_bottom(page, times=3, sleep_s=1)

                    video_items = await self._select_video_items(page)

                    current_page_new_count = 0
                    for el in video_items:
                        if limit > 0 and len(videos) >= limit:
                            break

                        video = await self._parse_video_item(page, el)
                        if not video:
                            continue

                        if video.bvid in seen:
                            continue

                        seen.add(video.bvid)
                        videos.append(video)
                        current_page_new_count += 1

                    logger.info(
                        f"Page {page_num}: Found {current_page_new_count} new videos. Total: {len(videos)}"
                    )

                    if limit > 0 and len(videos) >= limit:
                        logger.info(f"Reached limit {limit}. Stopping.")
                        break

                    next_btn = await self._find_next_button(page)
                    if next_btn:
                        logger.info("Navigating to next page...")
                        await next_btn.click()
                        page_num += 1
                        await asyncio.sleep(5)  # 等待加载
                    else:
                        logger.info("No next page or reached end.")
                        break

                logger.info(f"Found {len(videos)} videos on page.")
                return ScrapePageResult(author=author, videos=videos)
            except Exception as e:
                logger.error(f"Error scraping page: {e}")
                return ScrapePageResult(author=author, videos=videos)
            finally:
                await page.close()

        try:
            return await _scrape_once()
        except Exception as e:
            msg = str(e)
            if "Target crashed" not in msg and "has been closed" not in msg:
                raise

            logger.warning(f"Browser/page crashed, restarting browser and retrying once: {e}")
            try:
                await self.close()
            except Exception:
                pass

            self.browser = None
            self.playwright = None
            await self.connect()
            return await _scrape_once()

    async def close(self):
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
