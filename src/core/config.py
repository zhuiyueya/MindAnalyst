from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://user:password@localhost:5432/mind_analyst"
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_BASE_URL: Optional[str] = None
    HF_ENDPOINT: Optional[str] = None
    EMBEDDING_MODEL_NAME: str = "paraphrase-multilingual-MiniLM-L12-v2" # or text-embedding-3-small
    SUMMARY_PROMPT_PROFILE: str = "video_summary/v1"
    
    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
