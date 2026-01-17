from pydantic import BaseModel
from typing import List, Optional

class IngestRequest(BaseModel):
    mid: str # Changed from urls list to single mid
    limit: int = 10 # Default limit for videos to fetch

class IngestResponse(BaseModel):
    message: str
    task_id: str

class ChatRequest(BaseModel):
    query: str
    author_id: Optional[str] = None # Filter by author database ID
    history: List[dict] = []

class ChatResponse(BaseModel):
    answer: str
    citations: List[dict]

class AuthorResponse(BaseModel):
    id: str
    name: str
    platform: str
    avatar_url: Optional[str]
