import os
import logging
from minio import Minio
from minio.error import S3Error
from typing import Optional

logger = logging.getLogger(__name__)

class StorageService:
    def __init__(self, endpoint: str = "localhost:9000", access_key: str = "minioadmin", secret_key: str = "minioadmin", secure: bool = False):
        self.client = Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure
        )
        self.bucket_name = "mind-analyst-files"
        self._ensure_bucket()

    def _ensure_bucket(self):
        try:
            if not self.client.bucket_exists(self.bucket_name):
                self.client.make_bucket(self.bucket_name)
                logger.info(f"Created bucket: {self.bucket_name}")
        except S3Error as e:
            logger.error(f"MinIO bucket error: {e}")

    async def upload_file(self, file_path: str, object_name: Optional[str] = None) -> Optional[str]:
        """
        Upload a file to MinIO. Returns the object name.
        """
        if not object_name:
            object_name = os.path.basename(file_path)
            
        try:
            # Upload file
            self.client.fput_object(
                self.bucket_name, object_name, file_path,
            )
            logger.info(f"Uploaded {file_path} to {self.bucket_name}/{object_name}")
            return object_name
        except S3Error as e:
            logger.error(f"Failed to upload {file_path}: {e}")
            return None
            
    def get_file_url(self, object_name: str) -> str:
        """
        Get a presigned URL for the file (valid for 7 days)
        """
        try:
            return self.client.presigned_get_object(self.bucket_name, object_name)
        except Exception as e:
            logger.error(f"Failed to get URL for {object_name}: {e}")
            return ""
