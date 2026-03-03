from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://user:password@localhost:5432/mind_analyst"
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_BASE_URL: Optional[str] = None
    OPENAI_MODEL: Optional[str] = None
    HF_ENDPOINT: Optional[str] = None
    EMBEDDING_MODEL_NAME: str = "paraphrase-multilingual-MiniLM-L12-v2" # or text-embedding-3-small
    SUMMARY_PROMPT_PROFILE: str = "video_summary/v1"
    MODEL_CONFIG_PATH: str = "src/models/provider_models.yaml"
    CATEGORY_BATCH_SIZE: int = 500

    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_SECURE: bool = False
    MINIO_BUCKET_NAME: str = "mind-analyst-files"
    MINIO_PRESIGN_EXPIRES_S: int = 7 * 24 * 3600

    BILIBILI_USER_AGENT: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    BILIBILI_HTTP_TIMEOUT_S: int = 20
    BILIBILI_DOWNLOAD_DIR: str = "downloads"
    BILIBILI_BROWSER_HEADLESS: bool = False
    BILIBILI_BROWSER_SCROLL_TIMES: int = 3
    BILIBILI_BROWSER_SCROLL_SLEEP_S: float = 1.0
    
    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
