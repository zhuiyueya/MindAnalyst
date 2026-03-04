import logging
import os
from dataclasses import dataclass
from typing import Optional

from src.adapters.sources.bilibili.service import BilibiliSourceService
from src.adapters.storage.service import StorageService
from src.core.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PreparedAudio:
    audio_path: str
    cached_object_name: Optional[str]


class AudioMaterialService:
    def __init__(self, *, bilibili: BilibiliSourceService, storage: StorageService):
        self._bilibili = bilibili
        self._storage = storage

    async def prepare_audio_for_asr(self, content_external_id: str, *, reuse_audio_only: bool) -> Optional[PreparedAudio]:
        audio_path: Optional[str] = None
        cached_object_name: Optional[str] = None

        reuse_object = self._storage.find_first_by_prefix(f"audios/{content_external_id}/")
        if reuse_object is not None:
            cached_object_name = reuse_object.object_name
            local_name = os.path.basename(cached_object_name)
            local_path = os.path.join(settings.BILIBILI_DOWNLOAD_DIR, local_name)
            try:
                self._storage.get_to_file(reuse_object, local_path)
                audio_path = local_path
                logger.info("Reusing stored audio for %s: %s", content_external_id, cached_object_name)
            except Exception as exc:
                logger.warning("Failed to download stored audio for %s: %s", content_external_id, exc)

        if not audio_path and reuse_audio_only:
            logger.warning("No stored audio found for %s; skipping ASR reuse-only run.", content_external_id)
            return None

        if not audio_path:
            audio = await self._bilibili.download_audio(content_external_id)
            audio_path = audio.local_path if audio else None

        if not audio_path:
            return None

        if not cached_object_name:
            try:
                cached_object_name = await self._cache_audio_in_storage(content_external_id, audio_path)
            except Exception as exc:
                logger.warning("Failed to cache audio for %s: %s", content_external_id, exc)

        return PreparedAudio(audio_path=audio_path, cached_object_name=cached_object_name)

    async def _cache_audio_in_storage(self, content_external_id: str, audio_path: str) -> str:
        local_name = os.path.basename(audio_path)
        object_name = f"audios/{content_external_id}/{local_name}"
        await self._storage.put_file(audio_path, object_name)
        logger.info("Cached audio %s to %s", audio_path, object_name)
        return object_name

    def cleanup_audio_file(self, audio_path: str) -> None:
        if os.path.exists(audio_path):
            try:
                os.remove(audio_path)
                logger.info("Deleted local audio file: %s", audio_path)
            except Exception as exc:
                logger.warning("Failed to delete %s: %s", audio_path, exc)
