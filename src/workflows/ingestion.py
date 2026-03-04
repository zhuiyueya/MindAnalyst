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
from src.adapters.sources.bilibili.service import BilibiliSourceService
from src.adapters.sources.bilibili.types import AuthorProfile, VideoItem
from src.adapters.asr.service import ASRService
from src.adapters.asr.types import ASRAdapterError, AsrTranscriptionResult
from src.adapters.storage.service import StorageService
from src.core.config import settings
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
        self.bilibili: BilibiliSourceService = BilibiliSourceService()
        self.asr: ASRService = ASRService()
        self.storage: StorageService = StorageService()  # MinIO

    async def _get_or_create_author_in_db(self, author_data: AuthorProfile) -> Author:
        """
        在数据库中获取或创建作者
        处理 avatar 存储、创建、更新等所有数据库操作
        如果发生异常，返回 dummy author
        """
        try:
            mid = author_data.external_id

            # 查询现有作者
            stmt = select(Author).where(Author.external_id == mid)
            result_db = await self.session.execute(stmt)
            author = result_db.scalar_one_or_none()

            # 存储 avatar
            stored_avatar_object: Optional[str] = None
            if author_data.avatar_url:
                if not author or not author.avatar_url or author.avatar_url == author_data.avatar_url:
                    stored_avatar_object = await self._store_author_avatar(author_data.avatar_url, mid)

            if not author:
                # 创建新作者
                author = Author(
                    platform="bilibili",
                    external_id=mid,
                    name=author_data.name,
                    homepage_url=author_data.homepage_url,
                    avatar_url=stored_avatar_object or author_data.avatar_url
                )
                self.session.add(author)
                await self.session.commit()
                await self.session.refresh(author)
                logger.info(f"Created author: {author.name}")
            else:
                # 更新作者信息
                if author.name == "Unknown Author" and author_data.name != "Unknown Author":
                    author.name = author_data.name
                if stored_avatar_object:
                    author.avatar_url = stored_avatar_object
                elif not author.avatar_url and author_data.avatar_url:
                    author.avatar_url = author_data.avatar_url
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

    async def _correct_video_title(self, video: VideoItem) -> VideoItem:
        """
        检查视频标题是否为 unknown，如果是则尝试从 API 获取正确标题。
        返回修正后的视频信息。
        """
        try:
            meta = await self.bilibili.fetch_video_meta(video.bvid)
            if meta.title and meta.title != "Unknown Title":
                if video.title != meta.title:
                    logger.info(
                        f"Correcting title for {video.bvid}: '{video.title}' -> '{meta.title}'"
                    )
                    return VideoItem(bvid=video.bvid, title=meta.title, url=video.url)
        except Exception as e:
            logger.warning(f"Failed to fetch metadata for {video.bvid}: {e}")

        return video

    async def _ingest_single_video(self, video: VideoItem, author: Author) -> None:
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

    async def _ingest_videos(self, author: Author, videos: List[VideoItem]) -> None:
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
            ref = await self.storage.put_file(tmp_path, object_name)
            return ref.object_name
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
        从页面获取视频并采集
        limit: 最大处理视频数
        """
        result = await self.bilibili.fetch_author_and_videos(url, limit=limit)
        if not result.videos:
            logger.warning(f"No videos found on {url}")
            return

        author = await self._get_or_create_author_in_db(result.author)
        await self._ingest_videos(author, result.videos)

        # 作者报告生成已改为手动执行。

    async def ingest_author(self, mid_or_url: str, limit: int = 10) -> None:
        """采集作者及其最近的视频"""
        result = await self.bilibili.fetch_author_and_videos(mid_or_url, limit=limit)
        author = await self._get_or_create_author_in_db(result.author)
        await self._ingest_videos(author, result.videos)

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

        meta = await self.bilibili.fetch_video_meta(content.external_id)
        duration = meta.duration_s if meta.duration_s else (content.duration or 60)
        desc = meta.desc or ""
        cid: Optional[int] = meta.cid if meta.cid else None
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
            subs = await self.bilibili.fetch_subtitles(content.external_id, video_meta.cid)
        except Exception:
            return []

        items: List[SubtitleItem] = []
        for sub in subs:
            text_clean = sub.text.strip()
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
                await self.storage.put_file(audio_ctx.audio_path, object_name)

            transcription = await self.asr.transcribe_file(audio_ctx.audio_path)
            return self._payload_to_subtitles(
                transcription,
                duration=video_meta.duration,
                content_external_id=content.external_id,
            )
        except ASRAdapterError as asr_e:
            logger.error(f"ASR failed for {content.external_id}: {asr_e}")
            return []
        finally:
            self._cleanup_audio_file(audio_ctx.audio_path)

    async def _get_audio_for_asr(self, content: ContentItem, reuse_audio_only: bool) -> Optional[AudioContext]:
        """Resolve an audio file path for ASR, either by reusing stored audio or downloading a new one."""
        audio_path: Optional[str] = None
        reuse_object = self.storage.find_first_by_prefix(content.external_id)
        reuse_object_name: Optional[str] = None
        if reuse_object is not None:
            reuse_object_name = reuse_object.object_name
            local_name = os.path.basename(reuse_object_name)
            local_path = os.path.join(settings.BILIBILI_DOWNLOAD_DIR, local_name)
            try:
                self.storage.get_to_file(reuse_object, local_path)
                audio_path = local_path
                logger.info(f"Reusing stored audio for {content.external_id}: {reuse_object_name}")
            except Exception as exc:
                logger.warning(f"Failed to download stored audio for {content.external_id}: {exc}")

        if not audio_path and reuse_audio_only:
            logger.warning(f"No stored audio found for {content.external_id}; skipping ASR reuse-only run.")
            return None

        if not audio_path:
            audio = await self.bilibili.download_audio(content.external_id)
            audio_path = audio.local_path if audio else None

        if not audio_path:
            return None

        return AudioContext(audio_path=audio_path, reuse_object=reuse_object_name)

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
        transcription: AsrTranscriptionResult,
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
                subtitles.append(SubtitleItem(start_s=float(seg.start_s), end_s=float(seg.end_s), content=text_clean))

            if transcription.parse_warnings:
                logger.info(
                    "ASR parse warnings for %s: %s",
                    content_external_id,
                    ",".join(transcription.parse_warnings),
                )
            return subtitles

        text_clean = transcription.text.strip()
        if text_clean:
            logger.info("ASR returned plain text without segments.")
            end_s = float(duration) if duration else float(transcription.duration_s or 0.0)
            if end_s <= 0.0:
                end_s = 3600.0
            return [SubtitleItem(start_s=0.0, end_s=end_s, content=text_clean)]

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

