
import logging
import json
from typing import Dict, Any, List, Optional
from openai import AsyncOpenAI
from src.core.config import settings
from src.prompts.manager import PromptManager
from src.prompts.registry import PromptRegistry

logger = logging.getLogger(__name__)

class LLMService:
    def __init__(self):
        self.client = None
        if settings.OPENAI_API_KEY:
            self.client = AsyncOpenAI(
                api_key=settings.OPENAI_API_KEY,
                base_url=settings.OPENAI_BASE_URL
            )
            self.model = "Qwen/Qwen2.5-7B-Instruct" # Default model
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

        prompts = self.prompt_manager.get_prompt(profile_key, text=text[:20000])
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
            content = response.choices[0].message.content
            data = json.loads(content)
            value = data.get("content_type") if isinstance(data, dict) else None
            return self._ensure_str(value) if value else None
        except Exception as e:
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

        prompts = self.prompt_manager.get_prompt(profile_key, text=text[:30000])
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": prompts["system"]},
                    {"role": "user", "content": prompts["user"]}
                ],
                response_format={"type": "json_object"}
            )
            content = response.choices[0].message.content
            raw = json.loads(content)
            normalized = self._normalize_summary(raw, profile_key, resolved_type)
            return {"raw": raw, "normalized": normalized, "profile": profile_key, "content_type": resolved_type}
        except Exception as e:
            logger.error(f"Summary generation failed: {e}")
            return {"error": str(e)}

    async def generate_author_report(self, summaries: List[Dict[str, Any]], content_type: Optional[str]) -> Dict[str, Any]:
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
            
        # Aggregate summaries
        context_text = ""
        for i, s in enumerate(summaries):
            normalized = s.get("normalized") or s
            one_liner = normalized.get("one_liner", "")
            key_points = normalized.get("key_points", [])
            context_text += f"视频{i+1}摘要: {one_liner}\n观点: {'; '.join(key_points)}\n\n"
            
        prompts = self.prompt_manager.get_prompt(profile_key, context=context_text[:30000])
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": prompts["system"]},
                    {"role": "user", "content": prompts["user"]}
                ],
                response_format={"type": "json_object"}
            )
            content = response.choices[0].message.content
            raw = json.loads(content)
            return {"raw": raw, "profile": profile_key, "content_type": resolved_type}
        except Exception as e:
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
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompts["user"]}],
                response_format={"type": "json_object"}
            )
            result = json.loads(response.choices[0].message.content)
            indices = result.get("indices", [])
            return [int(i) for i in indices if isinstance(i, (int, str)) and int(i) < len(documents)]
        except Exception as e:
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

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": prompts["system"]},
                    {"role": "user", "content": prompts["user"]}
                ]
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"RAG answer failed: {e}")
            return f"Error calling LLM: {e}"
