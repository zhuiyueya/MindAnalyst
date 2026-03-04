import logging
import os
import tempfile
import uuid
from typing import Optional

import httpx

from src.adapters.storage.service import StorageService

logger = logging.getLogger(__name__)


class AvatarService:
    def __init__(self, storage: StorageService):
        self._storage = storage

    async def store_avatar_from_url(self, avatar_url: str, author_external_id: str) -> Optional[str]:
        if not avatar_url:
            return None

        tmp_path: Optional[str] = None
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
            ref = await self._storage.put_file(tmp_path, object_name)
            return ref.object_name
        except Exception as exc:
            logger.warning("Failed to store avatar %s: %s", avatar_url, exc)
            return None
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception as rm_exc:
                    logger.warning("Failed to remove temp avatar file %s: %s", tmp_path, rm_exc)
