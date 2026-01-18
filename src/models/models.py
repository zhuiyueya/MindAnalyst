from typing import Optional, List, Dict, Any
from datetime import datetime
from sqlmodel import SQLModel, Field, Relationship, Column, JSON
from pgvector.sqlalchemy import Vector
from sqlalchemy import Column
from pydantic import field_serializer
import uuid

def generate_uuid():
    return str(uuid.uuid4())

class Author(SQLModel, table=True):
    id: str = Field(default_factory=generate_uuid, primary_key=True)
    platform: str = Field(index=True)
    external_id: str = Field(index=True)
    name: str
    homepage_url: Optional[str] = None
    avatar_url: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    contents: List["ContentItem"] = Relationship(back_populates="author")
    reports: List["AuthorReport"] = Relationship(back_populates="author")

class ContentItem(SQLModel, table=True):
    id: str = Field(default_factory=generate_uuid, primary_key=True)
    author_id: str = Field(foreign_key="author.id")
    platform: str = Field(index=True)
    external_id: str = Field(index=True)
    type: str = Field(default="video") # video, article
    title: str
    url: str
    content_quality: str = Field(default="summary") # 'full' or 'summary'
    published_at: Optional[datetime] = None
    duration: Optional[int] = None # seconds
    extra_data: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    author: Author = Relationship(back_populates="contents")
    segments: List["Segment"] = Relationship(back_populates="content")
    summaries: List["Summary"] = Relationship(back_populates="content_item")

class Segment(SQLModel, table=True):
    id: str = Field(default_factory=generate_uuid, primary_key=True)
    content_id: str = Field(foreign_key="contentitem.id")
    segment_index: int
    start_time_ms: int
    end_time_ms: int
    text: str
    # 'paraphrase-multilingual-MiniLM-L12-v2' outputs 384 dimensions
    embedding: List[float] = Field(sa_column=Column(Vector(384))) 
    
    @field_serializer("embedding")
    def _serialize_embedding(self, v):
        if v is None:
            return None
        if hasattr(v, "tolist"):
            v = v.tolist()
        return [float(x) for x in v]
    
    content: ContentItem = Relationship(back_populates="segments")

class Summary(SQLModel, table=True):
    id: str = Field(default_factory=generate_uuid, primary_key=True)
    content_id: str = Field(foreign_key="contentitem.id")
    summary_type: str # content, short
    content: str # The summary text
    json_data: Dict[str, Any] = Field(default={}, sa_column=Column(JSON)) # Structured summary
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    content_item: ContentItem = Relationship(back_populates="summaries")

class AuthorReport(SQLModel, table=True):
    id: str = Field(default_factory=generate_uuid, primary_key=True)
    author_id: str = Field(foreign_key="author.id")
    report_version: str = Field(default="v1")
    content: str # The full markdown report
    json_data: Dict[str, Any] = Field(default={}, sa_column=Column(JSON)) # Structured data (key points, clusters)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    author: Author = Relationship(back_populates="reports")

# Update Author to include reports relationship
# We need to do this carefully since Author is defined above.
# SQLModel resolves string forward references, but we need to ensure Author has the field.

