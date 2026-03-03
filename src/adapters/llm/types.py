from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class LLMAdapterError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        operation: str,
        scene: Optional[str] = None,
        model: Optional[str] = None,
        provider: Optional[str] = None,
        cause: Optional[BaseException] = None,
    ):
        super().__init__(message)
        self.message = message
        self.operation = operation
        self.scene = scene
        self.model = model
        self.provider = provider
        self.cause = cause


class LLMUsage(BaseModel):
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None


class LLMCallRecord(BaseModel):
    task_type: str
    content_type: Optional[str] = None
    profile_key: Optional[str] = None
    model: Optional[str] = None

    system_prompt: str = ""
    user_prompt: str = ""

    request_meta: Dict[str, Any] = Field(default_factory=dict)
    response_text: Optional[str] = None
    response_meta: Dict[str, Any] = Field(default_factory=dict)

    usage: Optional[LLMUsage] = None
    status: Literal["success", "error"] = "success"
    error_message: Optional[str] = None

    parse_warnings: List[str] = Field(default_factory=list)


class ContentTypeResult(BaseModel):
    content_type: Optional[str] = None
    call: Optional[LLMCallRecord] = None


class SummaryBlock(BaseModel):
    type: str
    text: str


class SummaryResult(BaseModel):
    raw_text: str
    blocks: List[SummaryBlock] = Field(default_factory=list)
    profile: str
    content_type: str
    call: Optional[LLMCallRecord] = None


class ShortSummaryResult(BaseModel):
    raw: Dict[str, Any]
    profile: str
    content_type: str
    call: Optional[LLMCallRecord] = None


class AuthorReportResult(BaseModel):
    raw: Dict[str, Any]
    profile: str
    content_type: str
    call: Optional[LLMCallRecord] = None


class RerankResult(BaseModel):
    indices: List[int]
    call: Optional[LLMCallRecord] = None


class RagIntentResult(BaseModel):
    route: str
    tags: List[str] = Field(default_factory=list)
    query: str
    raw: Dict[str, Any] = Field(default_factory=dict)
    call: Optional[LLMCallRecord] = None


class RagAnswerResult(BaseModel):
    answer: str
    call: Optional[LLMCallRecord] = None


class BatchSelectCandidatesResult(BaseModel):
    selected_ids: List[str] = Field(default_factory=list)
    raw: Dict[str, Any] = Field(default_factory=dict)
    call: Optional[LLMCallRecord] = None


class FinalSelectCandidatesResult(BaseModel):
    selected_ids: List[str] = Field(default_factory=list)
    category_list: List[str] = Field(default_factory=list)
    raw: Dict[str, Any] = Field(default_factory=dict)
    call: Optional[LLMCallRecord] = None


class AuthorCategoriesResult(BaseModel):
    category_list: List[str] = Field(default_factory=list)
    raw: Dict[str, Any] = Field(default_factory=dict)
    call: Optional[LLMCallRecord] = None


class TagVideoCategoryResult(BaseModel):
    category: Optional[str] = None
    raw: Dict[str, Any] = Field(default_factory=dict)
    call: Optional[LLMCallRecord] = None
