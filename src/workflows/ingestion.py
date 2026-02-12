from dataclasses import dataclass
from typing import  List, Optional, cast
import os
import tempfile
import uuid
import httpx
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import select
from src.models.models import Author, ContentItem, Segment
from src.adapters.sources.bilibili.bilix import BilixCrawler
from src.adapters.sources.bilibili.browser import BrowserCrawler, AuthorInfo, VideoInfo, ScrapePageResult
from src.adapters.asr.service import ASRService, AsrTranscription
from src.adapters.storage.service import StorageService
import logging

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class VideoMeta:
    duration: int
    desc: str
    cid: Optional[int]


@dataclass(frozen=True, slots=True)
class SubtitleItem:
    start_s: float
    end_s: float
    content: str


@dataclass(frozen=True, slots=True)
class TextChunk:
    start_s: float
    end_s: float
    text: str


@dataclass(frozen=True, slots=True)
class AudioContext:
    audio_path: str
    reuse_object: Optional[str]

class IngestionWorkflow:
    def __init__(self, session: AsyncSession):
        self.session: AsyncSession = session
        self.crawler: BilixCrawler = BilixCrawler()
        self.browser_crawler: Optional[BrowserCrawler] = None  # Lazy init
        self.asr: ASRService = ASRService()
        self.storage: StorageService = StorageService()  # MinIO

    async def _scrape_from_browser(self, url: str, limit: int) -> Optional[ScrapePageResult]:
        """
        使用 BrowserCrawler 爬取页面数据
        返回 (videos, author_data) 或 None（失败时）
        """
        if not self.browser_crawler:
            self.browser_crawler = BrowserCrawler(headless=False)

        try:
            return await self.browser_crawler.get_videos_from_page(url, limit=limit)
        except Exception as e:
            logger.error(f"Browser crawler failed: {e}")
            return None
        finally:
            # Close browser when done
            if self.browser_crawler:
                await self.browser_crawler.close()
                self.browser_crawler = None

    async def _fetch_author_with_fallback(
        self,
        author_data: Optional[AuthorInfo],
        first_video: VideoInfo
    ) -> AuthorInfo:
        """
        获取作者信息，如果失败则使用 bilix API 作为 fallback
        始终返回有效的 AuthorInfo
        """
        if author_data and author_data.mid and author_data.face:
            return author_data

        logger.info(f"Fetching author info for BVID: {first_video.bvid}")
        try:
            bilix_author = await self.crawler.get_author_info(first_video.bvid)
            mid = str(bilix_author.mid)
            return AuthorInfo(
                mid=mid,
                name=bilix_author.name,
                face=bilix_author.face,
                url=f"https://space.bilibili.com/{mid}"
            )
        except Exception as e:
            logger.warning(f"Bilix fallback failed: {e}")
            # 返回默认作者数据
            return AuthorInfo(
                mid="0",
                name="Unknown Author",
                face="",
                url=""
            )

    async def _get_or_create_author_in_db(
        self,
        author_data: AuthorInfo
    ) -> Author:
        """
        在数据库中获取或创建作者
        处理 avatar 存储、创建、更新等所有数据库操作
        如果发生异常，返回 dummy author
        """
        try:
            mid = author_data.mid

            # 查询现有作者
            stmt = select(Author).where(Author.external_id == mid)
            result_db = await self.session.execute(stmt)
            author = result_db.scalar_one_or_none()

            # 存储 avatar
            stored_avatar_url: Optional[str] = None
            if author_data.face:
                if not author or not author.avatar_url or author.avatar_url == author_data.face:
                    stored_avatar_url = await self._store_author_avatar(author_data.face, mid)

            if not author:
                # 创建新作者
                author = Author(
                    platform="bilibili",
                    external_id=mid,
                    name=author_data.name,
                    homepage_url=author_data.url,
                    avatar_url=stored_avatar_url or author_data.face
                )
                self.session.add(author)
                await self.session.commit()
                await self.session.refresh(author)
                logger.info(f"Created author: {author.name}")
            else:
                # 更新作者信息
                if author.name == "Unknown Author" and author_data.name != "Unknown Author":
                    author.name = author_data.name
                if stored_avatar_url:
                    author.avatar_url = stored_avatar_url
                elif not author.avatar_url and author_data.face:
                    author.avatar_url = author_data.face
                self.session.add(author)
                await self.session.commit()
                logger.info(f"Updated author info: {author.name}")

            return author

        except Exception as e:
            logger.error(f"Failed to get/create author: {e}. Creating dummy author.")
            return await self._get_or_create_dummy_author()

    async def _get_or_create_dummy_author(self) -> Author:
        """获取或创建 dummy author（fallback）"""
        dummy_mid = "0"
        stmt = select(Author).where(Author.external_id == dummy_mid)
        result = await self.session.execute(stmt)
        author = result.scalar_one_or_none()

        if not author:
            author = Author(
                platform="bilibili",
                external_id=dummy_mid,
                name="Unknown Author",
                homepage_url="",
                avatar_url=""
            )
            self.session.add(author)
            await self.session.commit()
            await self.session.refresh(author)

        return author

    async def _correct_video_title(self, video: VideoInfo) -> VideoInfo:
        """
        检查视频标题是否为 unknown，如果是则尝试从 API 获取正确标题。
        返回修正后的 VideoInfo。
        """
        try:
            v_info_meta = await self.crawler.get_video_info(video.bvid)
            if v_info_meta.title and v_info_meta.title != "Unknown Title":
                if video.title != v_info_meta.title:
                    logger.info(
                        f"Correcting title for {video.bvid}: '{video.title}' -> '{v_info_meta.title}'"
                    )
                    return VideoInfo(bvid=video.bvid, title=v_info_meta.title, url=video.url)
        except Exception as e:
            logger.warning(f"Failed to fetch metadata for {video.bvid}: {e}")

        return video

    async def _ingest_single_video(self, video: VideoInfo, author: Author) -> None:
        """处理单个视频：创建 ContentItem 并调用 process_content"""
        bvid = video.bvid

        # 检查内容是否已存在
        stmt = select(ContentItem).where(ContentItem.external_id == bvid)
        result = await self.session.execute(stmt)
        content = result.scalar_one_or_none()

        if not content:
            content = ContentItem(
                author_id=author.id,
                platform="bilibili",
                external_id=bvid,
                title=video.title,
                url=video.url,
                type="video",
                content_quality="summary",
                extra_data={"bvid": video.bvid, "title": video.title, "url": video.url}
            )
            self.session.add(content)
            await self.session.commit()
            await self.session.refresh(content)

            await self.process_content(content)
        else:
            # 如果内容存在但质量是 summary，重试获取完整内容
            if content.content_quality == 'summary':
                logger.info(f"Content exists but quality is 'summary'. Retrying: {bvid}")
                where_clause = cast(ColumnElement[bool], Segment.content_id == content.id)
                await self.session.execute(delete(Segment).where(where_clause))
                await self.session.commit()
                await self.process_content(content)
            else:
                logger.info(
                    f"Content already exists (quality={content.content_quality}): {bvid} - {video.title}, skipping."
                )

    async def _ingest_videos(self, author: Author, videos: List[VideoInfo]) -> None:
        """处理视频列表：纠正标题并逐个处理"""
        for video in videos:
            corrected_video = await self._correct_video_title(video)
            await self._ingest_single_video(corrected_video, author)

    async def _store_author_avatar(self, avatar_url: str, author_external_id: str) -> Optional[str]:
        if not avatar_url:
            return None

        tmp_path = None
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(avatar_url)
                resp.raise_for_status()
                content_type = resp.headers.get("content-type", "")
                if "png" in content_type:
                    ext = ".png"
                elif "webp" in content_type:
                    ext = ".webp"
                elif "jpeg" in content_type or "jpg" in content_type:
                    ext = ".jpg"
                else:
                    ext = os.path.splitext(avatar_url.split("?")[0])[1] or ".jpg"

                with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp_file:
                    tmp_file.write(resp.content)
                    tmp_path = tmp_file.name

            object_name = f"avatars/{author_external_id}_{uuid.uuid4().hex}{ext}"
            await self.storage.upload_file(tmp_path, object_name)
            return self.storage.get_file_url(object_name)
        except Exception as e:
            logger.warning(f"Failed to store avatar {avatar_url}: {e}")
            return None
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception as rm_e:
                    logger.warning(f"Failed to remove temp avatar file {tmp_path}: {rm_e}")

    async def ingest_from_browser(self, url: str, limit: int = 0) -> None:
        """
        使用 BrowserCrawler 从页面获取视频并采集
        limit: 最大处理视频数
        """
        # 1. 爬取数据
        scrape_result = await self._scrape_from_browser(url, limit)
        if scrape_result is None:
            return

        videos: List[VideoInfo] = scrape_result.videos
        if not videos:
            logger.warning(f"No videos found on {url}")
            return

        author_data: Optional[AuthorInfo] = scrape_result.author

        # 2. 处理作者（获取 & 创建）
        complete_author_data = await self._fetch_author_with_fallback(author_data, videos[0])
        author = await self._get_or_create_author_in_db(complete_author_data)

        # 3. 处理视频列表
        await self._ingest_videos(author, videos)

        # 作者报告生成已改为手动执行。

    async def ingest_author(self, mid_or_url: str, limit: int = 10) -> None:
        """采集作者及其最近的视频"""
        # 1. 获取作者信息
        info = await self.crawler.get_author_info(mid_or_url)
        mid = str(info.mid)

        # 构建 AuthorInfo
        author_data = AuthorInfo(
            mid=mid,
            name=info.name,
            face=info.face,
            url=f"https://space.bilibili.com/{mid}",
        )

        # 2. 处理作者（获取/创建）
        author = await self._get_or_create_author_in_db(author_data)

        # 3. 获取视频列表
        videos_raw = await self.crawler.get_videos(mid_or_url, limit=limit)

        # 转换为 VideoInfo 格式
        videos: List[VideoInfo] = [
            VideoInfo(
                bvid=v.bvid,
                title=v.title,
                url=f"https://www.bilibili.com/video/{v.bvid}",
            )
            for v in videos_raw
        ]

        # 4. 处理视频列表
        await self._ingest_videos(author, videos)

        # 作者报告生成已改为手动执行。

    async def process_content(self, content: ContentItem, reuse_audio_only: bool = False):
        """Fetch subtitles, segment them, and persist segments."""
        logger.info(f"Processing content: {content.title}")
        
        try:
            video_meta = await self._get_video_meta(content, reuse_audio_only=reuse_audio_only)
            subtitles = await self._fetch_subtitles_with_fallback(
                content,
                video_meta,
                reuse_audio_only=reuse_audio_only,
            )

            if not subtitles:
                await self._mark_content_missing(content)
                return

            quality = self._determine_quality(subtitles)
            await self._update_content_quality(content, quality)

            chunks = self._create_chunks(subtitles)
            await self._persist_segments(content, chunks)

            logger.info(f"Saved {len(chunks)} segments for {content.title} (Quality: {quality})")
            
        except Exception as e:
            logger.error(f"Error processing {content.external_id}: {e}")

    async def _get_video_meta(self, content: ContentItem, reuse_audio_only: bool) -> VideoMeta:
        """Build VideoMeta from bilix video info or from the existing DB fields."""
        if reuse_audio_only:
            return VideoMeta(duration=content.duration or 60, desc="", cid=None)

        v_info = await self.crawler.get_video_info(content.external_id)
        duration = v_info.duration if v_info.duration else (content.duration or 60)
        desc = v_info.desc
        cid: Optional[int] = v_info.cid if v_info.cid else None
        return VideoMeta(duration=duration, desc=desc, cid=cid)

    async def _fetch_subtitles_with_fallback(
        self,
        content: ContentItem,
        video_meta: VideoMeta,
        reuse_audio_only: bool,
    ) -> List[SubtitleItem]:
        """Fetch subtitles with fallbacks: official subtitles -> ASR -> description."""
        subtitles = await self._try_fetch_subtitles(content, video_meta)
        if subtitles:
            return subtitles

        subtitles = await self._try_fetch_asr_subtitles(content, video_meta, reuse_audio_only=reuse_audio_only)
        if subtitles:
            return subtitles

        subtitles = self._fallback_to_description(content, video_meta)
        return subtitles

    async def _try_fetch_subtitles(self, content: ContentItem, video_meta: VideoMeta) -> List[SubtitleItem]:
        """Try fetching official subtitles from bilix."""
        if video_meta.cid is None:
            return []

        try:
            raw_subs = await self.crawler.get_subtitle(content.external_id, video_meta.cid)
        except Exception:
            return []

        items: List[SubtitleItem] = []
        for sub in raw_subs:
            text_clean = sub.content.strip()
            if not text_clean:
                continue
            items.append(SubtitleItem(start_s=sub.start_s, end_s=sub.end_s, content=text_clean))

        return items

    async def _try_fetch_asr_subtitles(
        self,
        content: ContentItem,
        video_meta: VideoMeta,
        reuse_audio_only: bool,
    ) -> List[SubtitleItem]:
        """Run ASR and normalize its output into subtitle items."""
        logger.info(f"No subtitles for {content.external_id}, trying ASR...")

        audio_ctx = await self._get_audio_for_asr(content, reuse_audio_only=reuse_audio_only)
        if audio_ctx is None:
            return []

        try:
            object_name = f"{content.external_id}_{os.path.basename(audio_ctx.audio_path)}"
            if not audio_ctx.reuse_object:
                await self.storage.upload_file(audio_ctx.audio_path, object_name)

            transcription = await self.asr.transcribe(audio_ctx.audio_path)
            return self._payload_to_subtitles(transcription, duration=video_meta.duration, content_external_id=content.external_id)
        except Exception as asr_e:
            logger.error(f"ASR failed for {content.external_id}: {asr_e}")
            return []
        finally:
            self._cleanup_audio_file(audio_ctx.audio_path)

    async def _get_audio_for_asr(self, content: ContentItem, reuse_audio_only: bool) -> Optional[AudioContext]:
        """Resolve an audio file path for ASR, either by reusing stored audio or downloading a new one."""
        audio_path: Optional[str] = None
        reuse_object = self.storage.find_object_with_prefix(content.external_id)
        if reuse_object:
            local_name = os.path.basename(reuse_object)
            local_path = os.path.join(self.crawler.download_dir, local_name)
            if self.storage.download_file(reuse_object, local_path):
                audio_path = local_path
                logger.info(f"Reusing stored audio for {content.external_id}: {reuse_object}")

        if not audio_path and reuse_audio_only:
            logger.warning(f"No stored audio found for {content.external_id}; skipping ASR reuse-only run.")
            return None

        if not audio_path:
            audio_path = await self.crawler.download_audio(content.external_id)

        if not audio_path:
            return None

        return AudioContext(audio_path=audio_path, reuse_object=reuse_object)

    def _cleanup_audio_file(self, audio_path: str) -> None:
        """Remove the temporary audio file if it exists."""
        if os.path.exists(audio_path):
            try:
                os.remove(audio_path)
                logger.info(f"Deleted local audio file: {audio_path}")
            except Exception as rm_e:
                logger.warning(f"Failed to delete {audio_path}: {rm_e}")

    def _payload_to_subtitles(
        self,
        transcription: AsrTranscription,
        duration: int,
        content_external_id: str,
    ) -> List[SubtitleItem]:
        """Convert AsrTranscription into subtitle items."""
        subtitles: List[SubtitleItem] = []

        if transcription.segments:
            for seg in transcription.segments:
                text_clean = seg.text.strip()
                if not text_clean:
                    continue
                subtitles.append(SubtitleItem(start_s=float(seg.start), end_s=float(seg.end), content=text_clean))
            return subtitles

        text_clean = transcription.text.strip()
        if text_clean:
            logger.info("ASR returned plain text without segments.")
            return [SubtitleItem(start_s=0.0, end_s=float(duration), content=text_clean)]

        logger.warning("ASR returned no segments/text for %s.", content_external_id)
        return []

    def _fallback_to_description(self, content: ContentItem, video_meta: VideoMeta) -> List[SubtitleItem]:
        """Fallback to using the video description when subtitles and ASR are unavailable."""
        if not video_meta.desc:
            return []

        logger.warning(f"No subtitles/ASR for {content.external_id}, using description.")
        return [
            SubtitleItem(
                start_s=0.0,
                end_s=float(video_meta.duration),
                content=f"[Description] {video_meta.desc}",
            )
        ]

    async def _mark_content_missing(self, content: ContentItem) -> None:
        """Mark a content item as missing and persist."""
        logger.warning(f"No content found for {content.external_id}")
        content.content_quality = "missing"
        self.session.add(content)
        await self.session.commit()

    def _determine_quality(self, subtitles: List[SubtitleItem]) -> str:
        """Determine content quality based on subtitle source."""
        if len(subtitles) == 1 and subtitles[0].content.startswith("[Description]"):
            return "summary"
        return "full"

    async def _update_content_quality(self, content: ContentItem, quality: str) -> None:
        """Update the content quality field (commit is performed later)."""
        content.content_quality = quality
        self.session.add(content)

    async def _persist_segments(self, content: ContentItem, chunks: List[TextChunk]) -> None:
        """Persist transcript chunks as Segment rows."""
        for i, chunk in enumerate(chunks):
            segment = Segment(
                content_id=content.id,
                segment_index=i,
                start_time_ms=int(chunk.start_s * 1000),
                end_time_ms=int(chunk.end_s * 1000),
                text=chunk.text,
            )
            self.session.add(segment)

        await self.session.commit()

    def _create_chunks(self, subtitles: List[SubtitleItem], target_length: int = 300) -> List[TextChunk]:
        """Merge subtitle items into text chunks."""

        chunks: List[TextChunk] = []
        current_from = 0.0
        current_to = 0.0
        current_text = ""

        for sub in subtitles:
            # Initialize start time
            if not current_text:
                current_from = sub.start_s

            # Append text
            if current_text:
                current_text += " " + sub.content
            else:
                current_text = sub.content

            current_to = sub.end_s

            # Flush by length
            if len(current_text) >= target_length:
                chunks.append(TextChunk(start_s=current_from, end_s=current_to, text=current_text))
                current_from = 0.0
                current_to = 0.0
                current_text = ""

        # Flush last chunk
        if current_text:
            chunks.append(TextChunk(start_s=current_from, end_s=current_to, text=current_text))

        return chunks

