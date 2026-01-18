
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

    async def generate_summary(self, text: str, context: str = "") -> Dict[str, Any]:
        """
        Generate structured summary for a video content.
        """
        if not self.client:
            return {"summary": "LLM not configured", "key_points": []}

        # Use PromptManager
        prompts = self.prompt_manager.get_prompt("video_summary/v1", text=text[:30000])
        
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
            context_text += f"视频{i+1}摘要: {s.get('one_liner', '')}\n观点: {'; '.join(s.get('key_points', []))}\n\n"
            
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
