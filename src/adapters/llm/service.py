
import logging
import json
import re
import ast
from typing import Dict, Any, List, Optional
from openai import AsyncOpenAI
from src.core.config import settings
from src.prompts.manager import PromptManager
from src.prompts.registry import PromptRegistry
from src.database.db import get_session
from src.models.models import LLMCallLog

logger = logging.getLogger(__name__)

class LLMService:
    def __init__(self):
        self.client = None
        if settings.OPENAI_API_KEY:
            self.client = AsyncOpenAI(
                api_key=settings.OPENAI_API_KEY,
                base_url=settings.OPENAI_BASE_URL
            )
            self.model = settings.OPENAI_MODEL or "deepseek-ai/DeepSeek-V3.2"
        else:
            logger.warning("OPENAI_API_KEY not set, LLM service will be disabled.")
        
        self.prompt_manager = PromptManager()
        self.prompt_registry = PromptRegistry()

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

    def _parse_json_response(self, content: Optional[str]) -> Dict[str, Any]:
        if not content:
            return {"raw_text": "", "parse_error": "empty response"}

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
                return parsed if isinstance(parsed, dict) else {"raw": parsed}
            except Exception as exc:
                last_error = exc
                try:
                    parsed = ast.literal_eval(cleaned)
                    if isinstance(parsed, dict):
                        return parsed
                    if isinstance(parsed, list):
                        return {"raw": parsed}
                except Exception as inner_exc:
                    last_error = inner_exc
                continue

        return {"raw_text": content, "parse_error": str(last_error) if last_error else "invalid json"}

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
        usage_dict = self._usage_to_dict(usage)
        response_meta = response_meta or {}
        if usage_dict:
            response_meta = {**response_meta, "usage": usage_dict}

        log_entry = LLMCallLog(
            task_type=task_type,
            content_type=content_type,
            profile_key=profile_key,
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            request_meta=request_meta or {},
            response_text=response_text,
            response_meta=response_meta,
            prompt_tokens=usage_dict.get("prompt_tokens"),
            completion_tokens=usage_dict.get("completion_tokens"),
            total_tokens=usage_dict.get("total_tokens"),
            status=status,
            error_message=error_message
        )

        try:
            async for session in get_session():
                session.add(log_entry)
                await session.commit()
                break
        except Exception as exc:
            logger.warning(f"Failed to log LLM call: {exc}")

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

    async def classify_content_type(self, text: str) -> Optional[str]:
        profile_key = self.prompt_registry.get_prompt_key("content.classify", None, require_override=False)
        if not profile_key:
            logger.warning("No content.classify profile configured")
            return None
        content = None
        truncated_text = text[:20000]
        prompts = self.prompt_manager.get_prompt(profile_key, text=truncated_text)
        request_meta = {
            "input_chars": len(text),
            "input_char_limit": 20000,
            "input_truncated": len(text) > 20000
        }
        if not self.client:
            return None

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": prompts["system"]},
                    {"role": "user", "content": prompts["user"]}
                ],
                response_format={"type": "json_object"}
            )
            logger.info("LLM raw response (content.classify): %s", self._response_to_debug(response))
            content = response.choices[0].message.content
            data = json.loads(content)
            value = data.get("content_type") if isinstance(data, dict) else None
            await self._log_call(
                task_type="content.classify",
                content_type=None,
                profile_key=profile_key,
                system_prompt=prompts["system"],
                user_prompt=prompts["user"],
                model=getattr(response, "model", self.model),
                request_meta=request_meta,
                response_text=content,
                response_meta={"finish_reason": response.choices[0].finish_reason},
                usage=getattr(response, "usage", None)
            )
            return self._ensure_str(value) if value else None
        except Exception as e:
            await self._log_call(
                task_type="content.classify",
                content_type=None,
                profile_key=profile_key,
                system_prompt=prompts["system"],
                user_prompt=prompts["user"],
                model=self.model,
                request_meta=request_meta,
                response_text=content,
                status="error",
                error_message=str(e)
            )
            logger.error(f"Content classify failed: {e}")
            return None

    async def generate_summary(self, text: str, content_type: Optional[str], task_type: str = "summary.single") -> Dict[str, Any]:
        """
        Generate structured summary for a video content.
        """
        resolved_type = content_type or "generic"
        profile_key = self.prompt_registry.get_prompt_key(task_type, resolved_type, require_override=True)
        if not profile_key:
            logger.warning(f"No profile for task={task_type} type={resolved_type}, falling back to generic")
            profile_key = "types/generic/summary_single/v1"

        if not self.client:
            raw = {"summary": "LLM not configured", "key_points": []}
            normalized = self._normalize_summary(raw, profile_key, resolved_type)
            return {"raw": raw, "normalized": normalized, "profile": profile_key, "content_type": resolved_type}
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
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": prompts["system"]},
                    {"role": "user", "content": prompts["user"]}
                ]
            )
            logger.info("LLM raw response (summary.single): %s", self._response_to_debug(response))
            content = response.choices[0].message.content
            raw = self._parse_json_response(content)
            if isinstance(raw, dict) and raw.get("parse_error"):
                normalized = {
                    "one_liner": "",
                    "key_points": [],
                    "summary": self._ensure_str(raw.get("raw_text")),
                    "facts": [],
                    "principles": [],
                    "case_studies": [],
                    "actionable_guidelines": [],
                    "cognitive_warnings": [],
                    "content_type": resolved_type,
                    "profile": profile_key,
                    "parse_error": raw.get("parse_error"),
                }
            else:
                normalized = self._normalize_summary(raw, profile_key, resolved_type)
            await self._log_call(
                task_type=task_type,
                content_type=resolved_type,
                profile_key=profile_key,
                system_prompt=prompts["system"],
                user_prompt=prompts["user"],
                model=getattr(response, "model", self.model),
                request_meta=request_meta,
                response_text=content,
                response_meta={
                    "finish_reason": response.choices[0].finish_reason,
                    **({"parse_error": raw.get("parse_error")} if isinstance(raw, dict) and raw.get("parse_error") else {})
                },
                usage=getattr(response, "usage", None)
            )
            return {"raw": raw, "normalized": normalized, "profile": profile_key, "content_type": resolved_type}
        except Exception as e:
            await self._log_call(
                task_type=task_type,
                content_type=resolved_type,
                profile_key=profile_key,
                system_prompt=prompts["system"],
                user_prompt=prompts["user"],
                model=self.model,
                request_meta=request_meta,
                response_text=content,
                status="error",
                error_message=str(e)
            )
            logger.error(f"Summary generation failed: {e}")
            return {"error": str(e)}

    async def generate_author_report(
        self,
        summaries: List[Dict[str, Any]],
        content_type: Optional[str],
        context_override: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate author-level report from multiple video summaries.
        """
        resolved_type = content_type or "generic"
        profile_key = self.prompt_registry.get_prompt_key("report.author", resolved_type, require_override=True)
        if not profile_key:
            logger.warning(f"No report profile for type={resolved_type}, using generic")
            profile_key = "types/generic/author_report/v1"

        if not self.client:
            return {"report": "LLM not configured", "profile": profile_key, "content_type": resolved_type}
            
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
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": prompts["system"]},
                    {"role": "user", "content": prompts["user"]}
                ],
                response_format={"type": "json_object"}
            )
            logger.info("LLM raw response (report.author): %s", self._response_to_debug(response))
            content = response.choices[0].message.content
            raw = self._parse_json_response(content)
            await self._log_call(
                task_type="report.author",
                content_type=resolved_type,
                profile_key=profile_key,
                system_prompt=prompts["system"],
                user_prompt=prompts["user"],
                model=getattr(response, "model", self.model),
                request_meta=request_meta,
                response_text=content,
                response_meta={"finish_reason": response.choices[0].finish_reason},
                usage=getattr(response, "usage", None)
            )
            return {"raw": raw, "profile": profile_key, "content_type": resolved_type}
        except Exception as e:
            await self._log_call(
                task_type="report.author",
                content_type=resolved_type,
                profile_key=profile_key,
                system_prompt=prompts["system"],
                user_prompt=prompts["user"],
                model=self.model,
                request_meta=request_meta,
                response_text=content,
                status="error",
                error_message=str(e)
            )
            logger.error(f"Report generation failed: {e}")
            return {"error": str(e)}

    async def rerank(self, query: str, documents: List[str], top_n: int = 5, content_type: Optional[str] = None) -> List[int]:
        """
        Rerank documents based on query. Returns indices of top_n documents.
        """
        resolved_type = content_type or "generic"
        profile_key = self.prompt_registry.get_prompt_key("rag.rerank", resolved_type, require_override=True)
        if not profile_key:
            logger.warning(f"No rerank profile for type={resolved_type}, using generic")
            profile_key = "types/generic/rag/rerank_v1"

        if not self.client:
            return list(range(min(len(documents), top_n)))

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
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompts["user"]}],
                response_format={"type": "json_object"}
            )
            logger.info("LLM raw response (rag.rerank): %s", self._response_to_debug(response))
            content = response.choices[0].message.content
            result = json.loads(content)
            await self._log_call(
                task_type="rag.rerank",
                content_type=resolved_type,
                profile_key=profile_key,
                system_prompt="",
                user_prompt=prompts["user"],
                model=getattr(response, "model", self.model),
                request_meta=request_meta,
                response_text=content,
                response_meta={"finish_reason": response.choices[0].finish_reason},
                usage=getattr(response, "usage", None)
            )
            indices = result.get("indices", [])
            return [int(i) for i in indices if isinstance(i, (int, str)) and int(i) < len(documents)]
        except Exception as e:
            await self._log_call(
                task_type="rag.rerank",
                content_type=resolved_type,
                profile_key=profile_key,
                system_prompt="",
                user_prompt=prompts["user"],
                model=self.model,
                request_meta=request_meta,
                status="error",
                error_message=str(e)
            )
            logger.error(f"Rerank failed: {e}")
            return list(range(min(len(documents), top_n)))

    async def generate_rag_answer(self, query: str, context_str: str, content_type: Optional[str]) -> str:
        resolved_type = content_type or "generic"
        profile_key = self.prompt_registry.get_prompt_key("rag.answer", resolved_type, require_override=True)
        if not profile_key:
            logger.warning(f"No rag.answer profile for type={resolved_type}, using generic")
            profile_key = "types/generic/rag/answer_v1"

        prompts = self.prompt_manager.get_prompt(profile_key, query=query, context_str=context_str)
        if not self.client:
            return "【模拟回答】基于片段 [1]，作者提到了相关概念。\n(请配置 OPENAI_API_KEY 以启用真实 LLM 回答)"
        request_meta = {
            "query_chars": len(query),
            "context_chars": len(context_str)
        }
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": prompts["system"]},
                    {"role": "user", "content": prompts["user"]}
                ]
            )
            logger.info("LLM raw response (rag.answer): %s", self._response_to_debug(response))
            content = response.choices[0].message.content
            await self._log_call(
                task_type="rag.answer",
                content_type=resolved_type,
                profile_key=profile_key,
                system_prompt=prompts["system"],
                user_prompt=prompts["user"],
                model=getattr(response, "model", self.model),
                request_meta=request_meta,
                response_text=content,
                response_meta={"finish_reason": response.choices[0].finish_reason},
                usage=getattr(response, "usage", None)
            )
            return content
        except Exception as e:
            await self._log_call(
                task_type="rag.answer",
                content_type=resolved_type,
                profile_key=profile_key,
                system_prompt=prompts["system"],
                user_prompt=prompts["user"],
                model=self.model,
                request_meta=request_meta,
                status="error",
                error_message=str(e)
            )
            logger.error(f"RAG answer failed: {e}")
            return f"Error calling LLM: {e}"
