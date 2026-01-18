
import logging
import json
from typing import Dict, Any, List, Optional
from openai import AsyncOpenAI
from src.core.config import settings
from src.prompts.manager import PromptManager

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

    def _normalize_summary(self, raw: Dict[str, Any], profile_key: str) -> Dict[str, Any]:
        if profile_key == "video_summary/v2":
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
        }

    async def generate_summary(self, text: str, context: str = "") -> Dict[str, Any]:
        """
        Generate structured summary for a video content.
        """
        if not self.client:
            raw = {"summary": "LLM not configured", "key_points": []}
            normalized = self._normalize_summary(raw, "video_summary/v1")
            return {"raw": raw, "normalized": normalized, "profile": "video_summary/v1"}

        # Use PromptManager
        profile_key = settings.SUMMARY_PROMPT_PROFILE or "video_summary/v1"
        if profile_key not in {"video_summary/v1", "video_summary/v2"}:
            logger.warning(f"Unknown summary prompt profile '{profile_key}', falling back to video_summary/v1")
            profile_key = "video_summary/v1"
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
            normalized = self._normalize_summary(raw, profile_key)
            return {"raw": raw, "normalized": normalized, "profile": profile_key}
        except Exception as e:
            logger.error(f"Summary generation failed: {e}")
            return {"error": str(e)}

    async def generate_author_report(self, summaries: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Generate author-level report from multiple video summaries.
        """
        if not self.client:
            return {"report": "LLM not configured"}
            
        # Aggregate summaries
        context_text = ""
        for i, s in enumerate(summaries):
            normalized = s.get("normalized") or s
            one_liner = normalized.get("one_liner", "")
            key_points = normalized.get("key_points", [])
            context_text += f"视频{i+1}摘要: {one_liner}\n观点: {'; '.join(key_points)}\n\n"
            
        prompts = self.prompt_manager.get_prompt("author_report/v1", context=context_text[:30000])
        
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
            return json.loads(content)
        except Exception as e:
            logger.error(f"Report generation failed: {e}")
            return {"error": str(e)}

    async def rerank(self, query: str, documents: List[str], top_n: int = 5) -> List[int]:
        """
        Rerank documents based on query. Returns indices of top_n documents.
        """
        if not self.client:
            return list(range(min(len(documents), top_n)))

        prompts = self.prompt_manager.get_prompt(
            "rag_chat/rerank_v1", 
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
