import os
import logging
import datetime
from typing import Optional

from minio import Minio
from minio.error import S3Error
from pydantic import BaseModel

from src.core.config import settings

logger = logging.getLogger(__name__)


class StorageError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        operation: str,
        bucket: str,
        object_name: Optional[str] = None,
        prefix: Optional[str] = None,
        cause: Optional[BaseException] = None,
    ):
        super().__init__(message)
        self.operation = operation
        self.bucket = bucket
        self.object_name = object_name
        self.prefix = prefix
        self.cause = cause


class StoredObjectRef(BaseModel):
    bucket: str
    object_name: str


class PresignedUrl(BaseModel):
    url: str


class StorageService:
    def __init__(self):
        self._client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE,
        )
        self._bucket = settings.MINIO_BUCKET_NAME
        self._ensure_bucket()

    def _ensure_bucket(self) -> None:
        try:
            if not self._client.bucket_exists(self._bucket):
                self._client.make_bucket(self._bucket)
                logger.info("Created bucket: %s", self._bucket)
        except S3Error as exc:
            raise StorageError(
                "MinIO bucket ensure failed",
                operation="ensure_bucket",
                bucket=self._bucket,
                cause=exc,
            ) from exc

    async def put_file(self, local_path: str, object_name: str) -> StoredObjectRef:
        if not object_name:
            raise StorageError(
                "object_name is required",
                operation="put_file",
                bucket=self._bucket,
                object_name=object_name,
            )
        try:
            self._client.fput_object(self._bucket, object_name, local_path)
            logger.info("Uploaded %s to %s/%s", local_path, self._bucket, object_name)
            return StoredObjectRef(bucket=self._bucket, object_name=object_name)
        except S3Error as exc:
            raise StorageError(
                f"Failed to upload file: {os.path.basename(local_path)}",
                operation="put_file",
                bucket=self._bucket,
                object_name=object_name,
                cause=exc,
            ) from exc

    def find_first_by_prefix(self, prefix: str) -> Optional[StoredObjectRef]:
        if not prefix:
            return None
        try:
            objects = self._client.list_objects(self._bucket, prefix=prefix, recursive=True)
            for obj in objects:
                object_name = getattr(obj, "object_name", None)
                if isinstance(object_name, str) and object_name.startswith(prefix):
                    return StoredObjectRef(bucket=self._bucket, object_name=object_name)
            return None
        except Exception as exc:
            raise StorageError(
                "Failed to list objects",
                operation="find_first_by_prefix",
                bucket=self._bucket,
                prefix=prefix,
                cause=exc,
            ) from exc

    def get_to_file(self, ref: StoredObjectRef, target_path: str) -> None:
        try:
            self._client.fget_object(ref.bucket, ref.object_name, target_path)
            logger.info("Downloaded %s/%s to %s", ref.bucket, ref.object_name, target_path)
        except Exception as exc:
            raise StorageError(
                "Failed to download object",
                operation="get_to_file",
                bucket=ref.bucket,
                object_name=ref.object_name,
                cause=exc,
            ) from exc

    def presign_get(self, ref: StoredObjectRef, expires_in_s: Optional[int] = None) -> PresignedUrl:
        expires_s = expires_in_s if expires_in_s is not None else settings.MINIO_PRESIGN_EXPIRES_S
        if not isinstance(expires_s, int):
            raise StorageError(
                "Invalid expires value",
                operation="presign_get",
                bucket=ref.bucket,
                object_name=ref.object_name,
            )
        if expires_s < 1 or expires_s > 604800:
            raise StorageError(
                "expires_in_s must be between 1 and 604800 seconds",
                operation="presign_get",
                bucket=ref.bucket,
                object_name=ref.object_name,
            )
        expires = datetime.timedelta(seconds=expires_s)
        try:
            url = self._client.presigned_get_object(ref.bucket, ref.object_name, expires=expires)
            return PresignedUrl(url=url)
        except Exception as exc:
            raise StorageError(
                "Failed to presign object URL",
                operation="presign_get",
                bucket=ref.bucket,
                object_name=ref.object_name,
                cause=exc,
            ) from exc
