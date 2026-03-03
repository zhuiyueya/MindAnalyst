import logging
import json
import re
import ast
import os
from typing import Dict, Any, List, Optional, Tuple, cast
from openai import AsyncOpenAI
from src.core.config import settings
from src.prompts.manager import PromptManager
from src.prompts.registry import PromptRegistry
from src.models.provider_registry import ModelProviderRegistry
from src.adapters.llm.types import (
    AuthorReportResult,
    AuthorCategoriesResult,
    BatchSelectCandidatesResult,
    ContentTypeResult,
    FinalSelectCandidatesResult,
    LLMCallRecord,
    LLMUsage,
    RagAnswerResult,
    RagIntentResult,
    RerankResult,
    ShortSummaryResult,
    SummaryBlock,
    SummaryResult,
    TagVideoCategoryResult,
)

logger = logging.getLogger(__name__)

class LLMService:
    def __init__(self):
        self._clients: Dict[str, AsyncOpenAI] = {}
        self.prompt_manager = PromptManager()
        self.prompt_registry = PromptRegistry()
        self.model_registry = ModelProviderRegistry()

    async def _chat_completion(
        self,
        *,
        client: AsyncOpenAI,
        model_name: str,
        messages: List[Dict[str, str]],
        require_json: bool,
    ) -> Tuple[Any, Optional[str]]:
        kwargs: Dict[str, Any] = {"model": model_name, "messages": messages}
        if require_json:
            kwargs["response_format"] = {"type": "json_object"}
        response = await client.chat.completions.create(**kwargs)
        content = None
        try:
            content = response.choices[0].message.content
        except Exception:
            content = None
        return response, content

    def _ensure_list(self, value) -> List[Any]:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        return [value]

    def _ensure_str(self, value) -> str:
        if value is None:
            return ""
        return str(value)

    def _usage_to_dict(self, usage: Any) -> Dict[str, Any]:
        if not usage:
            return {}
        if isinstance(usage, dict):
            return usage
        if hasattr(usage, "model_dump"):
            return usage.model_dump()
        if hasattr(usage, "dict"):
            return usage.dict()
        return {
            "prompt_tokens": getattr(usage, "prompt_tokens", None),
            "completion_tokens": getattr(usage, "completion_tokens", None),
            "total_tokens": getattr(usage, "total_tokens", None)
        }

    def _response_to_debug(self, response: Any) -> str:
        try:
            if hasattr(response, "model_dump"):
                return json.dumps(response.model_dump(), ensure_ascii=False)
            if hasattr(response, "dict"):
                return json.dumps(response.dict(), ensure_ascii=False)
        except Exception as exc:
            return f"<response dump failed: {exc}>"
        return str(response)

    def _parse_summary_blocks(self, text: str) -> List[Dict[str, str]]:
        if not text:
            return []
        pattern = re.compile(r"\[(观点|案例|实操|金句)\]")
        matches = list(pattern.finditer(text))
        if not matches:
            cleaned = text.strip()
            return [{"type": "其他", "text": cleaned}] if cleaned else []

        blocks: List[Dict[str, str]] = []
        last_type: Optional[str] = None
        last_index = 0
        for match in matches:
            if last_type is not None:
                chunk = text[last_index:match.start()].strip()
                if chunk:
                    blocks.append({"type": last_type, "text": chunk})
            else:
                leading = text[:match.start()].strip()
                if leading:
                    blocks.append({"type": "其他", "text": leading})
            last_type = match.group(1)
            last_index = match.end()

        if last_type is not None:
            tail = text[last_index:].strip()
            if tail:
                blocks.append({"type": last_type, "text": tail})

        return blocks

    def _parse_json_response(self, content: Optional[str]) -> Dict[str, Any]:
        if not content:
            return {"raw_text": "", "parse_error": "empty response"}

        def _normalize(candidate: str) -> str:
            normalized = candidate
            normalized = normalized.replace("\u201c", '"').replace("\u201d", '"')
            normalized = normalized.replace("\u2018", "'").replace("\u2019", "'")
            normalized = normalized.replace("“", '"').replace("”", '"')
            normalized = normalized.replace("‘", "'").replace("’", "'")
            return normalized

        candidates: List[str] = []
        stripped = content.strip()
        candidates.append(stripped)

        if stripped.startswith("```"):
            unfenced = re.sub(r"^```[a-zA-Z0-9]*", "", stripped).strip()
            unfenced = re.sub(r"```$", "", unfenced).strip()
            candidates.append(unfenced)

        obj_start = stripped.find("{")
        obj_end = stripped.rfind("}")
        if obj_start != -1 and obj_end != -1 and obj_end > obj_start:
            candidates.append(stripped[obj_start:obj_end + 1])

        arr_start = stripped.find("[")
        arr_end = stripped.rfind("]")
        if arr_start != -1 and arr_end != -1 and arr_end > arr_start:
            candidates.append(stripped[arr_start:arr_end + 1])

        last_error: Optional[Exception] = None
        for candidate in candidates:
            cleaned = re.sub(r",\s*([}\]])", r"\1", candidate)
            try:
                parsed = json.loads(cleaned)
                return cast(Dict[str, Any], parsed) if isinstance(parsed, dict) else {"raw": parsed}
            except Exception as exc:
                last_error = exc

            normalized = _normalize(cleaned)
            if normalized != cleaned:
                try:
                    parsed = json.loads(normalized)
                    return cast(Dict[str, Any], parsed) if isinstance(parsed, dict) else {"raw": parsed}
                except Exception as exc:
                    last_error = exc

            try:
                parsed = ast.literal_eval(normalized)
                if isinstance(parsed, dict):
                    return cast(Dict[str, Any], parsed)
                if isinstance(parsed, list):
                    return {"raw": parsed}
            except Exception as inner_exc:
                last_error = inner_exc
                continue

        return {"raw_text": content, "parse_error": str(last_error) if last_error else "invalid json"}

    def _get_client_for_scene(
        self,
        scene: str
    ) -> tuple[Optional[AsyncOpenAI], str, Optional[str], Optional[str]]:
        model_id = self.model_registry.get_scene_model_id(scene)
        model_config = self.model_registry.get_model_config(model_id)
        if not model_id or not model_config:
            logger.warning("No model configured for scene=%s", scene)
            return None, "", model_id, None

        provider_name: Optional[str] = model_config.get("provider")
        model_name = str(model_config.get("model_name") or "").strip()
        if not provider_name or not model_name:
            logger.warning("Invalid model config for scene=%s model_id=%s", scene, model_id)
            return None, model_name, model_id, provider_name

        provider_config = self.model_registry.get_provider_config(provider_name) or {}
        base_url = provider_config.get("base_url")
        api_key_env = provider_config.get("api_key_env")
        api_key: Optional[str] = os.getenv(api_key_env) if isinstance(api_key_env, str) and api_key_env else None

        if not base_url or not api_key:
            logger.warning(
                "LLM provider config missing (base_url/api_key) for scene=%s provider=%s model_id=%s",
                scene,
                provider_name,
                model_id,
            )
            return None, model_name, model_id, provider_name

        cache_key = f"{provider_name or 'default'}::{base_url or ''}::{api_key_env or 'default'}"
        if cache_key not in self._clients:
            self._clients[cache_key] = AsyncOpenAI(api_key=api_key, base_url=base_url)
        return self._clients[cache_key], model_name, model_id, provider_name

    def _build_request_meta(self, base: Dict[str, Any], model_id: Optional[str], provider: Optional[str]) -> Dict[str, Any]:
        meta = dict(base)
        if model_id:
            meta["model_id"] = model_id
        if provider:
            meta["provider"] = provider
        return meta

    async def _log_call(
        self,
        task_type: str,
        content_type: Optional[str],
        profile_key: Optional[str],
        system_prompt: str,
        user_prompt: str,
        model: Optional[str],
        request_meta: Optional[Dict[str, Any]] = None,
        response_text: Optional[str] = None,
        response_meta: Optional[Dict[str, Any]] = None,
        usage: Any = None,
        status: str = "success",
        error_message: Optional[str] = None
    ) -> None:
        return

    def _build_call_record(
        self,
        *,
        task_type: str,
        content_type: Optional[str],
        profile_key: Optional[str],
        system_prompt: str,
        user_prompt: str,
        model: Optional[str],
        request_meta: Optional[Dict[str, Any]] = None,
        response_text: Optional[str] = None,
        response_meta: Optional[Dict[str, Any]] = None,
        usage: Any = None,
        status: str = "success",
        error_message: Optional[str] = None,
        parse_warnings: Optional[List[str]] = None,
    ) -> LLMCallRecord:
        usage_dict = self._usage_to_dict(usage)
        usage_model: Optional[LLMUsage] = None
        if usage_dict:
            usage_model = LLMUsage(
                prompt_tokens=usage_dict.get("prompt_tokens"),
                completion_tokens=usage_dict.get("completion_tokens"),
                total_tokens=usage_dict.get("total_tokens"),
            )

        return LLMCallRecord(
            task_type=task_type,
            content_type=content_type,
            profile_key=profile_key,
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            request_meta=request_meta or {},
            response_text=response_text,
            response_meta=response_meta or {},
            usage=usage_model,
            status="success" if status != "error" else "error",
            error_message=error_message,
            parse_warnings=parse_warnings or [],
        )

    def _is_v2_summary(self, profile_key: str) -> bool:
        return "summary_single/v2" in profile_key or profile_key == "video_summary/v2"

    def _normalize_summary(self, raw: Dict[str, Any], profile_key: str, content_type: Optional[str]) -> Dict[str, Any]:
        if self._is_v2_summary(profile_key):
            core_principles = [self._ensure_str(v) for v in self._ensure_list(raw.get("core_principles"))]
            actionable = [self._ensure_str(v) for v in self._ensure_list(raw.get("actionable_guidelines"))]
            warnings = [self._ensure_str(v) for v in self._ensure_list(raw.get("cognitive_warnings"))]

            case_studies: List[Dict[str, Any]] = []
            for item in self._ensure_list(raw.get("case_studies")):
                if isinstance(item, dict):
                    case_studies.append(item)
                else:
                    case_studies.append({"description": self._ensure_str(item)})

            one_liner = core_principles[0] if core_principles else (actionable[0] if actionable else (warnings[0] if warnings else ""))
            key_points = core_principles if core_principles else actionable
            summary_parts = []
            if core_principles:
                summary_parts.append("核心原则：" + "；".join(core_principles))
            if actionable:
                summary_parts.append("行动建议：" + "；".join(actionable))
            if warnings:
                summary_parts.append("认知警示：" + "；".join(warnings))
            summary_text = "。".join(summary_parts)

            return {
                "one_liner": one_liner,
                "key_points": key_points,
                "summary": summary_text,
                "facts": [],
                "principles": core_principles,
                "case_studies": case_studies,
                "actionable_guidelines": actionable,
                "cognitive_warnings": warnings,
                "content_type": content_type or "generic",
                "profile": profile_key,
            }

        key_points = [self._ensure_str(v) for v in self._ensure_list(raw.get("key_points"))]
        facts = [self._ensure_str(v) for v in self._ensure_list(raw.get("facts"))]
        return {
            "one_liner": self._ensure_str(raw.get("one_liner")),
            "key_points": key_points,
            "summary": self._ensure_str(raw.get("summary")),
            "facts": facts,
            "principles": [],
            "case_studies": [],
            "actionable_guidelines": [],
            "cognitive_warnings": [],
            "content_type": content_type or "generic",
            "profile": profile_key,
        }

    async def classify_content_type(self, text: str) -> ContentTypeResult:
        profile_key = self.prompt_registry.get_prompt_key("content.classify", None, require_override=False)
        if not profile_key:
            logger.warning("No content.classify profile configured")
            return ContentTypeResult(content_type=None, call=None)
        content = None
        truncated_text = text[:20000]
        prompts = self.prompt_manager.get_prompt(profile_key, text=truncated_text)
        request_meta = {
            "input_chars": len(text),
            "input_char_limit": 20000,
            "input_truncated": len(text) > 20000
        }
        client, model_name, model_id, provider = self._get_client_for_scene("content.classify")
        if not client:
            return ContentTypeResult(content_type=None, call=None)

        try:
            response, content = await self._chat_completion(
                client=client,
                model_name=model_name,
                messages=[
                    {"role": "system", "content": prompts["system"]},
                    {"role": "user", "content": prompts["user"]},
                ],
                require_json=True,
            )
            logger.info("LLM raw response (content.classify): %s", self._response_to_debug(response))
            data = json.loads(content or "{}")
            value = data.get("content_type") if isinstance(data, dict) else None
            call = self._build_call_record(
                task_type="content.classify",
                content_type=None,
                profile_key=profile_key,
                system_prompt=prompts["system"],
                user_prompt=prompts["user"],
                model=getattr(response, "model", model_name),
                request_meta=self._build_request_meta(request_meta, model_id, provider),
                response_text=content,
                response_meta={"finish_reason": response.choices[0].finish_reason},
                usage=getattr(response, "usage", None),
            )
            return ContentTypeResult(content_type=self._ensure_str(value) if value else None, call=call)
        except Exception as e:
            logger.error(f"Content classify failed: {e}")
            call = self._build_call_record(
                task_type="content.classify",
                content_type=None,
                profile_key=profile_key,
                system_prompt=prompts["system"],
                user_prompt=prompts["user"],
                model=model_name,
                request_meta=self._build_request_meta(request_meta, model_id, provider),
                response_text=content,
                status="error",
                error_message=str(e),
            )
            return ContentTypeResult(content_type=None, call=call)

    async def generate_short_summary(self, text: str, content_type: Optional[str]) -> ShortSummaryResult:
        resolved_type = content_type or "generic"
        profile_key = self.prompt_registry.get_prompt_key("summary.short", resolved_type, require_override=True)
        if not profile_key:
            logger.warning("No profile for task=summary.short type=%s, falling back to generic", resolved_type)
            profile_key = "types/generic/summary_short/v1"

        client, model_name, model_id, provider = self._get_client_for_scene("summary.short")
        if not client:
            return ShortSummaryResult(
                raw={"keywords": [], "summary": "LLM not configured", "is_trash": False},
                profile=profile_key,
                content_type=resolved_type,
                call=None,
            )

        content = None
        truncated_text = text[:30000]
        prompts = self.prompt_manager.get_prompt(profile_key, full_transcript=truncated_text)
        request_meta = {
            "input_chars": len(text),
            "input_char_limit": 30000,
            "input_truncated": len(text) > 30000,
            "task_type": "summary.short"
        }

        try:
            response, content = await self._chat_completion(
                client=client,
                model_name=model_name,
                messages=[
                    {"role": "system", "content": prompts["system"]},
                    {"role": "user", "content": prompts["user"]},
                ],
                require_json=True,
            )
            logger.info("LLM raw response (summary.short): %s", self._response_to_debug(response))
            raw = self._parse_json_response(content or "")
            call = self._build_call_record(
                task_type="summary.short",
                content_type=resolved_type,
                profile_key=profile_key,
                system_prompt=prompts["system"],
                user_prompt=prompts["user"],
                model=getattr(response, "model", model_name),
                request_meta=self._build_request_meta(request_meta, model_id, provider),
                response_text=content,
                response_meta={"finish_reason": response.choices[0].finish_reason},
                usage=getattr(response, "usage", None),
                parse_warnings=["json_parse_error"] if "parse_error" in raw else [],
            )
            return ShortSummaryResult(raw=raw, profile=profile_key, content_type=resolved_type, call=call)
        except Exception as e:
            logger.error("Short summary generation failed: %s", e)
            call = self._build_call_record(
                task_type="summary.short",
                content_type=resolved_type,
                profile_key=profile_key,
                system_prompt=prompts["system"],
                user_prompt=prompts["user"],
                model=model_name,
                request_meta=self._build_request_meta(request_meta, model_id, provider),
                response_text=content,
                status="error",
                error_message=str(e),
            )
            return ShortSummaryResult(raw={"error": str(e)}, profile=profile_key, content_type=resolved_type, call=call)

    async def generate_summary(self, text: str, content_type: Optional[str], task_type: str = "summary.single") -> SummaryResult:
        """
        Generate structured summary for a video content.
        """
        resolved_type = content_type or "generic"
        profile_key = self.prompt_registry.get_prompt_key(task_type, resolved_type, require_override=True)
        if not profile_key:
            logger.warning(f"No profile for task={task_type} type={resolved_type}, falling back to generic")
            profile_key = "types/generic/summary_single/v1"

        scene = task_type
        client, model_name, model_id, provider = self._get_client_for_scene(scene)
        if not client:
            raw_text = "LLM not configured"
            return SummaryResult(raw_text=raw_text, blocks=[], profile=profile_key, content_type=resolved_type, call=None)
        content = None
        truncated_text = text[:30000]
        prompts = self.prompt_manager.get_prompt(profile_key, text=truncated_text)
        request_meta = {
            "input_chars": len(text),
            "input_char_limit": 30000,
            "input_truncated": len(text) > 30000,
            "task_type": task_type
        }
        
        try:
            response, content = await self._chat_completion(
                client=client,
                model_name=model_name,
                messages=[
                    {"role": "system", "content": prompts["system"]},
                    {"role": "user", "content": prompts["user"]},
                ],
                require_json=False,
            )
            logger.info("LLM raw response (summary.single): %s", self._response_to_debug(response))
            raw_text = (content or "").strip()
            blocks_raw = self._parse_summary_blocks(raw_text)
            blocks = [SummaryBlock(type=b.get("type", ""), text=b.get("text", "")) for b in blocks_raw if isinstance(b, dict)]
            call = self._build_call_record(
                task_type=task_type,
                content_type=resolved_type,
                profile_key=profile_key,
                system_prompt=prompts["system"],
                user_prompt=prompts["user"],
                model=getattr(response, "model", model_name),
                request_meta=self._build_request_meta(request_meta, model_id, provider),
                response_text=content,
                response_meta={"finish_reason": response.choices[0].finish_reason, "block_count": len(blocks)},
                usage=getattr(response, "usage", None),
            )
            return SummaryResult(raw_text=raw_text, blocks=blocks, profile=profile_key, content_type=resolved_type, call=call)
        except Exception as e:
            logger.error(f"Summary generation failed: {e}")
            call = self._build_call_record(
                task_type=task_type,
                content_type=resolved_type,
                profile_key=profile_key,
                system_prompt=prompts["system"],
                user_prompt=prompts["user"],
                model=model_name,
                request_meta=self._build_request_meta(request_meta, model_id, provider),
                response_text=content,
                status="error",
                error_message=str(e),
            )
            return SummaryResult(raw_text="", blocks=[], profile=profile_key, content_type=resolved_type, call=call)

    async def generate_author_report(
        self,
        summaries: List[Dict[str, Any]],
        content_type: Optional[str],
        context_override: Optional[str] = None
    ) -> AuthorReportResult:
        """
        Generate author-level report from multiple video summaries.
        """
        resolved_type = content_type or "generic"
        profile_key = self.prompt_registry.get_prompt_key("report.author", resolved_type, require_override=True)
        if not profile_key:
            logger.warning(f"No report profile for type={resolved_type}, using generic")
            profile_key = "types/generic/author_report/v1"

        client, model_name, model_id, provider = self._get_client_for_scene("report.author")
        if not client:
            return AuthorReportResult(raw={"report": "LLM not configured"}, profile=profile_key, content_type=resolved_type, call=None)
            
        # Aggregate summaries or use full-text override
        context_source = "summaries"
        context_text = ""
        if context_override and str(context_override).strip():
            context_source = "full_text"
            context_text = str(context_override)
        else:
            for i, s in enumerate(summaries):
                normalized = s.get("normalized") or s
                one_liner = normalized.get("one_liner", "")
                key_points = normalized.get("key_points", [])
                context_text += f"视频{i+1}摘要: {one_liner}\n观点: {'; '.join(key_points)}\n\n"
        content = None
        truncated_context = context_text[:30000]
        prompts = self.prompt_manager.get_prompt(profile_key, context=truncated_context)
        request_meta = {
            "summary_count": len(summaries),
            "context_chars": len(context_text),
            "context_char_limit": 30000,
            "context_truncated": len(context_text) > 30000,
            "context_source": context_source
        }
        
        try:
            response, content = await self._chat_completion(
                client=client,
                model_name=model_name,
                messages=[
                    {"role": "system", "content": prompts["system"]},
                    {"role": "user", "content": prompts["user"]},
                ],
                require_json=True,
            )
            logger.info("LLM raw response (report.author): %s", self._response_to_debug(response))
            raw = self._parse_json_response(content)
            call = self._build_call_record(
                task_type="report.author",
                content_type=resolved_type,
                profile_key=profile_key,
                system_prompt=prompts["system"],
                user_prompt=prompts["user"],
                model=getattr(response, "model", model_name),
                request_meta=self._build_request_meta(request_meta, model_id, provider),
                response_text=content,
                response_meta={"finish_reason": response.choices[0].finish_reason},
                usage=getattr(response, "usage", None),
                parse_warnings=["json_parse_error"] if isinstance(raw, dict) and "parse_error" in raw else [],
            )
            return AuthorReportResult(raw=raw if isinstance(raw, dict) else {"raw": raw}, profile=profile_key, content_type=resolved_type, call=call)
        except Exception as e:
            logger.error(f"Report generation failed: {e}")
            call = self._build_call_record(
                task_type="report.author",
                content_type=resolved_type,
                profile_key=profile_key,
                system_prompt=prompts["system"],
                user_prompt=prompts["user"],
                model=model_name,
                request_meta=self._build_request_meta(request_meta, model_id, provider),
                response_text=content,
                status="error",
                error_message=str(e),
            )
            return AuthorReportResult(raw={"error": str(e)}, profile=profile_key, content_type=resolved_type, call=call)

    async def rerank(self, query: str, documents: List[str], top_n: int = 5, content_type: Optional[str] = None) -> RerankResult:
        """
        Rerank documents based on query. Returns indices of top_n documents.
        """
        resolved_type = content_type or "generic"
        profile_key = self.prompt_registry.get_prompt_key("rag.rerank", resolved_type, require_override=True)
        if not profile_key:
            logger.warning(f"No rerank profile for type={resolved_type}, using generic")
            profile_key = "types/generic/rag/rerank_v1"

        client, model_name, model_id, provider = self._get_client_for_scene("rag.rerank")
        if not client:
            return RerankResult(indices=list(range(min(len(documents), top_n))), call=None)

        prompts = self.prompt_manager.get_prompt(
            profile_key,
            query=query, 
            documents=documents, 
            top_n=top_n
        )
        request_meta = {
            "query_chars": len(query),
            "document_count": len(documents),
            "documents_chars_total": sum(len(doc) for doc in documents),
            "top_n": top_n,
            "system_prompt_used": False,
            "template_system_prompt": prompts.get("system", "")
        }
        
        try:
            response, content = await self._chat_completion(
                client=client,
                model_name=model_name,
                messages=[{"role": "user", "content": prompts["user"]}],
                require_json=True,
            )
            logger.info("LLM raw response (rag.rerank): %s", self._response_to_debug(response))
            result = self._parse_json_response(content or "")
            indices_raw: object = result.get("indices") if isinstance(result, dict) else None
            indices: List[int] = []
            if isinstance(indices_raw, list):
                for i in cast(List[Any], indices_raw):
                    try:
                        indices.append(int(i))
                    except Exception:
                        continue
            indices = [i for i in indices if 0 <= i < len(documents)][:top_n]
            call = self._build_call_record(
                task_type="rag.rerank",
                content_type=resolved_type,
                profile_key=profile_key,
                system_prompt="",
                user_prompt=prompts["user"],
                model=getattr(response, "model", model_name),
                request_meta=self._build_request_meta(request_meta, model_id, provider),
                response_text=content,
                response_meta={"finish_reason": response.choices[0].finish_reason},
                usage=getattr(response, "usage", None),
                parse_warnings=["json_parse_error"] if isinstance(result, dict) and "parse_error" in result else [],
            )
            if not indices:
                indices = list(range(min(len(documents), top_n)))
                call.parse_warnings.append("rerank_indices_empty_fallback")
            return RerankResult(indices=indices, call=call)
        except Exception as e:
            logger.error(f"Rerank failed: {e}")
            call = self._build_call_record(
                task_type="rag.rerank",
                content_type=resolved_type,
                profile_key=profile_key,
                system_prompt="",
                user_prompt=prompts["user"],
                model=model_name,
                request_meta=self._build_request_meta(request_meta, model_id, provider),
                status="error",
                error_message=str(e),
            )
            return RerankResult(indices=list(range(min(len(documents), top_n))), call=call)

    async def classify_rag_intent(self, query: str) -> RagIntentResult:
        """Classify query intent for RAG routing.

        Returns a dict like: {"route": "author_report"|"summary_chunk"|"summary_short", "tags": [...], "query": "..."}
        """
        profile_key = self.prompt_registry.get_prompt_key("rag.router", None, require_override=False)
        prompts = self.prompt_manager.get_prompt(profile_key or "", query=query)

        client, model_name, model_id, provider = self._get_client_for_scene("rag.router")
        request_meta = {"query_chars": len(query)}
        if not client:
            call = self._build_call_record(
                task_type="rag.router",
                content_type=None,
                profile_key=profile_key,
                system_prompt=prompts.get("system", ""),
                user_prompt=prompts.get("user", ""),
                model=model_name or None,
                request_meta=self._build_request_meta({**request_meta, "missing_client": True}, model_id, provider),
                status="error",
                error_message="llm_client_not_configured",
            )
            return RagIntentResult(
                route="summary_chunk",
                tags=[],
                query=query,
                raw={"route": "summary_chunk", "tags": [], "query": query, "error": "llm_client_not_configured"},
                call=call,
            )

        content = None
        try:
            response, content = await self._chat_completion(
                client=client,
                model_name=model_name,
                messages=[
                    {"role": "system", "content": prompts["system"]},
                    {"role": "user", "content": prompts["user"]},
                ],
                require_json=True,
            )
            logger.info("LLM raw response (rag.router): %s", self._response_to_debug(response))
            data = self._parse_json_response(content)
            raw_dict = data if isinstance(data, dict) else {"raw": data}
            route_raw: object = raw_dict.get("route")
            tags_raw: object = raw_dict.get("tags")
            q_raw: object = raw_dict.get("query")
            tags: List[str] = []
            if isinstance(tags_raw, list):
                for x in cast(List[Any], tags_raw):
                    sx = str(x).strip()
                    if sx:
                        tags.append(sx)
            q = q_raw.strip() if isinstance(q_raw, str) and q_raw.strip() else query
            route = str(route_raw).strip() if isinstance(route_raw, str) and route_raw.strip() else "summary_chunk"
            call = self._build_call_record(
                task_type="rag.router",
                content_type=None,
                profile_key=profile_key,
                system_prompt=prompts["system"],
                user_prompt=prompts["user"],
                model=getattr(response, "model", model_name),
                request_meta=self._build_request_meta(request_meta, model_id, provider),
                response_text=content,
                response_meta={"finish_reason": response.choices[0].finish_reason},
                usage=getattr(response, "usage", None),
                parse_warnings=["json_parse_error"] if isinstance(raw_dict, dict) and "parse_error" in raw_dict else [],
            )
            return RagIntentResult(route=route, tags=tags, query=q, raw=raw_dict, call=call)
        except Exception as e:
            logger.error("RAG router classify failed: %s", e)
            call = self._build_call_record(
                task_type="rag.router",
                content_type=None,
                profile_key=profile_key,
                system_prompt=prompts.get("system", ""),
                user_prompt=prompts.get("user", ""),
                model=model_name,
                request_meta=self._build_request_meta(request_meta, model_id, provider),
                response_text=content,
                status="error",
                error_message=str(e),
            )
            return RagIntentResult(
                route="summary_chunk",
                tags=[],
                query=query,
                raw={"route": "summary_chunk", "tags": [], "query": query, "error": str(e)},
                call=call,
            )

    async def generate_rag_answer(self, query: str, context_str: str, content_type: Optional[str]) -> RagAnswerResult:
        resolved_type = content_type or "generic"
        profile_key = self.prompt_registry.get_prompt_key("rag.answer", resolved_type, require_override=True)
        if not profile_key:
            logger.warning(f"No rag.answer profile for type={resolved_type}, using generic")
            profile_key = "types/generic/rag/answer_v1"

        prompts = self.prompt_manager.get_prompt(profile_key, query=query, context_str=context_str)
        client, model_name, model_id, provider = self._get_client_for_scene("rag.answer")
        if not client:
            call = self._build_call_record(
                task_type="rag.answer",
                content_type=resolved_type,
                profile_key=profile_key,
                system_prompt=prompts["system"],
                user_prompt=prompts["user"],
                model=model_name or None,
                request_meta=self._build_request_meta({"missing_client": True}, model_id, provider),
                status="error",
                error_message="llm_client_not_configured",
            )
            return RagAnswerResult(answer="", call=call)
        request_meta = {
            "query_chars": len(query),
            "context_chars": len(context_str)
        }
        try:
            response, content = await self._chat_completion(
                client=client,
                model_name=model_name,
                messages=[
                    {"role": "system", "content": prompts["system"]},
                    {"role": "user", "content": prompts["user"]},
                ],
                require_json=False,
            )
            logger.info("LLM raw response (rag.answer): %s", self._response_to_debug(response))
            call = self._build_call_record(
                task_type="rag.answer",
                content_type=resolved_type,
                profile_key=profile_key,
                system_prompt=prompts["system"],
                user_prompt=prompts["user"],
                model=getattr(response, "model", model_name),
                request_meta=self._build_request_meta(request_meta, model_id, provider),
                response_text=content,
                response_meta={"finish_reason": response.choices[0].finish_reason},
                usage=getattr(response, "usage", None),
            )
            return RagAnswerResult(answer=content or "", call=call)
        except Exception as e:
            logger.error(f"RAG answer failed: {e}")
            call = self._build_call_record(
                task_type="rag.answer",
                content_type=resolved_type,
                profile_key=profile_key,
                system_prompt=prompts["system"],
                user_prompt=prompts["user"],
                model=model_name,
                request_meta=self._build_request_meta(request_meta, model_id, provider),
                response_text=content,
                status="error",
                error_message=str(e),
            )
            return RagAnswerResult(answer=f"Error calling LLM: {e}", call=call)

    async def select_batch_candidates(self, items: List[Dict[str, Any]], top_min: int = 5, top_max: int = 8) -> BatchSelectCandidatesResult:
        client, model_name, model_id, provider = self._get_client_for_scene("batch.select_candidates")
        profile_key = self.prompt_registry.get_prompt_key("batch.select_candidates", None, require_override=False)
        payload = json.dumps(items, ensure_ascii=False)
        prompts = self.prompt_manager.get_prompt(profile_key or "", payload=payload, top_min=top_min, top_max=top_max)
        request_meta = {
            "item_count": len(items),
            "top_min": top_min,
            "top_max": top_max
        }
        if not client:
            call = self._build_call_record(
                task_type="batch.select_candidates",
                content_type=None,
                profile_key=profile_key,
                system_prompt=prompts.get("system", ""),
                user_prompt=prompts.get("user", ""),
                model=model_name or None,
                request_meta=self._build_request_meta({**request_meta, "missing_client": True}, model_id, provider),
                status="error",
                error_message="llm_client_not_configured",
            )
            return BatchSelectCandidatesResult(selected_ids=[], raw={"error": "llm_client_not_configured"}, call=call)

        content = None
        try:
            response, content = await self._chat_completion(
                client=client,
                model_name=model_name,
                messages=[
                    {"role": "system", "content": prompts["system"]},
                    {"role": "user", "content": prompts["user"]},
                ],
                require_json=True,
            )
            data = self._parse_json_response(content)
            selected_ids_raw: object = data.get("selected_ids") if isinstance(data, dict) else None
            selected_ids: List[str] = []
            if isinstance(selected_ids_raw, list):
                for x in cast(List[Any], selected_ids_raw):
                    sx = str(x).strip()
                    if sx:
                        selected_ids.append(sx)

            call = self._build_call_record(
                task_type="batch.select_candidates",
                content_type=None,
                profile_key=profile_key,
                system_prompt=prompts["system"],
                user_prompt=prompts["user"],
                model=getattr(response, "model", model_name),
                request_meta=self._build_request_meta(request_meta, model_id, provider),
                response_text=content,
                response_meta={"finish_reason": response.choices[0].finish_reason},
                usage=getattr(response, "usage", None),
                parse_warnings=["json_parse_error"] if isinstance(data, dict) and "parse_error" in data else [],
            )
            return BatchSelectCandidatesResult(selected_ids=selected_ids, raw=data if isinstance(data, dict) else {"raw": data}, call=call)
        except Exception as e:
            logger.error("Batch candidate selection failed: %s", e)
            call = self._build_call_record(
                task_type="batch.select_candidates",
                content_type=None,
                profile_key=profile_key,
                system_prompt=prompts.get("system", ""),
                user_prompt=prompts.get("user", ""),
                model=model_name,
                request_meta=self._build_request_meta(request_meta, model_id, provider),
                response_text=content,
                status="error",
                error_message=str(e),
            )
            return BatchSelectCandidatesResult(selected_ids=[], raw={"error": str(e)}, call=call)

    async def select_final_candidates(self, items: List[Dict[str, Any]], top_n: int = 20) -> FinalSelectCandidatesResult:
        client, model_name, model_id, provider = self._get_client_for_scene("batch.final_select")
        profile_key = self.prompt_registry.get_prompt_key("batch.final_select", None, require_override=False)
        payload = json.dumps(items, ensure_ascii=False)
        prompts = self.prompt_manager.get_prompt(profile_key or "", payload=payload, top_n=top_n)
        request_meta = {"item_count": len(items), "top_n": top_n}
        if not client:
            call = self._build_call_record(
                task_type="batch.final_select",
                content_type=None,
                profile_key=profile_key,
                system_prompt=prompts.get("system", ""),
                user_prompt=prompts.get("user", ""),
                model=model_name or None,
                request_meta=self._build_request_meta({**request_meta, "missing_client": True}, model_id, provider),
                status="error",
                error_message="llm_client_not_configured",
            )
            return FinalSelectCandidatesResult(selected_ids=[], category_list=[], raw={"error": "llm_client_not_configured"}, call=call)

        content = None
        try:
            response, content = await self._chat_completion(
                client=client,
                model_name=model_name,
                messages=[
                    {"role": "system", "content": prompts["system"]},
                    {"role": "user", "content": prompts["user"]},
                ],
                require_json=True,
            )
            data = self._parse_json_response(content)
            selected_ids_raw: object = data.get("selected_ids") if isinstance(data, dict) else None
            category_list_raw: object = data.get("category_list") if isinstance(data, dict) else None
            selected_ids: List[str] = []
            if isinstance(selected_ids_raw, list):
                for x in cast(List[Any], selected_ids_raw):
                    sx = str(x).strip()
                    if sx:
                        selected_ids.append(sx)
            category_list: List[str] = []
            if isinstance(category_list_raw, list):
                for x in cast(List[Any], category_list_raw):
                    sx = str(x).strip()
                    if sx:
                        category_list.append(sx)

            call = self._build_call_record(
                task_type="batch.final_select",
                content_type=None,
                profile_key=profile_key,
                system_prompt=prompts["system"],
                user_prompt=prompts["user"] ,
                model=getattr(response, "model", model_name),
                request_meta=self._build_request_meta(request_meta, model_id, provider),
                response_text=content,
                response_meta={"finish_reason": response.choices[0].finish_reason},
                usage=getattr(response, "usage", None),
                parse_warnings=["json_parse_error"] if isinstance(data, dict) and "parse_error" in data else [],
            )
            return FinalSelectCandidatesResult(
                selected_ids=selected_ids,
                category_list=category_list,
                raw=data if isinstance(data, dict) else {"raw": data},
                call=call,
            )
        except Exception as e:
            logger.error("Final candidate selection failed: %s", e)
            call = self._build_call_record(
                task_type="batch.final_select",
                content_type=None,
                profile_key=profile_key,
                system_prompt=prompts.get("system", ""),
                user_prompt=prompts.get("user", ""),
                model=model_name,
                request_meta=self._build_request_meta(request_meta, model_id, provider),
                response_text=content,
                status="error",
                error_message=str(e),
            )
            return FinalSelectCandidatesResult(selected_ids=[], category_list=[], raw={"error": str(e)}, call=call)

    async def generate_author_categories(self, category_list: List[str], summaries: List[Dict[str, Any]]) -> AuthorCategoriesResult:
        client, model_name, model_id, provider = self._get_client_for_scene("author.final_categories")
        profile_key = self.prompt_registry.get_prompt_key("author.final_categories", None, require_override=False)
        payload = json.dumps({"category_list": category_list, "summaries": summaries}, ensure_ascii=False)
        prompts = self.prompt_manager.get_prompt(profile_key or "", payload=payload)
        request_meta = {"candidate_category_count": len(category_list), "summary_count": len(summaries)}
        if not client:
            call = self._build_call_record(
                task_type="author.final_categories",
                content_type=None,
                profile_key=profile_key,
                system_prompt=prompts.get("system", ""),
                user_prompt=prompts.get("user", ""),
                model=model_name or None,
                request_meta=self._build_request_meta({**request_meta, "missing_client": True}, model_id, provider),
                status="error",
                error_message="llm_client_not_configured",
            )
            return AuthorCategoriesResult(category_list=category_list, raw={"error": "llm_client_not_configured"}, call=call)

        content = None
        try:
            response, content = await self._chat_completion(
                client=client,
                model_name=model_name,
                messages=[
                    {"role": "system", "content": prompts["system"]},
                    {"role": "user", "content": prompts["user"]},
                ],
                require_json=True,
            )
            data = self._parse_json_response(content)
            final_categories_raw: object = data.get("category_list") if isinstance(data, dict) else None
            final_categories: List[str] = []
            if isinstance(final_categories_raw, list):
                for x in cast(List[Any], final_categories_raw):
                    sx = str(x).strip()
                    if sx:
                        final_categories.append(sx)

            call = self._build_call_record(
                task_type="author.final_categories",
                content_type=None,
                profile_key=profile_key,
                system_prompt=prompts["system"],
                user_prompt=prompts["user"],
                model=getattr(response, "model", model_name),
                request_meta=self._build_request_meta(request_meta, model_id, provider),
                response_text=content,
                response_meta={"finish_reason": response.choices[0].finish_reason},
                usage=getattr(response, "usage", None),
                parse_warnings=["json_parse_error"] if isinstance(data, dict) and "parse_error" in data else [],
            )
            return AuthorCategoriesResult(
                category_list=final_categories or category_list,
                raw=data if isinstance(data, dict) else {"raw": data},
                call=call,
            )
        except Exception as e:
            logger.error("Author category generation failed: %s", e)
            call = self._build_call_record(
                task_type="author.final_categories",
                content_type=None,
                profile_key=profile_key,
                system_prompt=prompts.get("system", ""),
                user_prompt=prompts.get("user", ""),
                model=model_name,
                request_meta=self._build_request_meta(request_meta, model_id, provider),
                response_text=content,
                status="error",
                error_message=str(e),
            )
            return AuthorCategoriesResult(category_list=category_list, raw={"error": str(e)}, call=call)

    async def tag_video_category(self, category_list: List[str], summary: Dict[str, Any]) -> TagVideoCategoryResult:
        client, model_name, model_id, provider = self._get_client_for_scene("video.category_tagging")
        profile_key = self.prompt_registry.get_prompt_key("video.category_tagging", None, require_override=False)
        payload = json.dumps({"category_list": category_list, "summary": summary}, ensure_ascii=False)
        prompts = self.prompt_manager.get_prompt(profile_key or "", payload=payload)
        request_meta = {"category_count": len(category_list)}
        if not client:
            call = self._build_call_record(
                task_type="video.category_tagging",
                content_type=None,
                profile_key=profile_key,
                system_prompt=prompts.get("system", ""),
                user_prompt=prompts.get("user", ""),
                model=model_name or None,
                request_meta=self._build_request_meta({**request_meta, "missing_client": True}, model_id, provider),
                status="error",
                error_message="llm_client_not_configured",
            )
            return TagVideoCategoryResult(category=None, raw={"error": "llm_client_not_configured"}, call=call)
        content = None
        try:
            response, content = await self._chat_completion(
                client=client,
                model_name=model_name,
                messages=[
                    {"role": "system", "content": prompts["system"]},
                    {"role": "user", "content": prompts["user"]},
                ],
                require_json=True,
            )
            data = self._parse_json_response(content)
            category_raw: object = data.get("category") if isinstance(data, dict) else None
            category = str(category_raw).strip() if isinstance(category_raw, str) and str(category_raw).strip() else None
            call = self._build_call_record(
                task_type="video.category_tagging",
                content_type=None,
                profile_key=profile_key,
                system_prompt=prompts["system"],
                user_prompt=prompts["user"],
                model=getattr(response, "model", model_name),
                request_meta=self._build_request_meta(request_meta, model_id, provider),
                response_text=content,
                response_meta={"finish_reason": response.choices[0].finish_reason},
                usage=getattr(response, "usage", None),
                parse_warnings=["json_parse_error"] if isinstance(data, dict) and "parse_error" in data else [],
            )
            return TagVideoCategoryResult(category=category, raw=data if isinstance(data, dict) else {"raw": data}, call=call)
        except Exception as e:
            logger.error("Video category tagging failed: %s", e)
            call = self._build_call_record(
                task_type="video.category_tagging",
                content_type=None,
                profile_key=profile_key,
                system_prompt=prompts.get("system", ""),
                user_prompt=prompts.get("user", ""),
                model=model_name,
                request_meta=self._build_request_meta(request_meta, model_id, provider),
                response_text=content,
                status="error",
                error_message=str(e),
            )
            return TagVideoCategoryResult(category=None, raw={"error": str(e)}, call=call)
