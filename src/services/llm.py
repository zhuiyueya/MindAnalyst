
import logging
import json
from typing import Dict, Any, List, Optional
from openai import AsyncOpenAI
from src.config.settings import settings

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

    async def generate_summary(self, text: str, context: str = "") -> Dict[str, Any]:
        """
        Generate structured summary for a video content.
        """
        if not self.client:
            return {"summary": "LLM not configured", "key_points": []}

        system_prompt = """你是一个专业的视频内容分析师。请对提供的视频转写文本进行结构化总结。
输出必须是合法的 JSON 格式，包含以下字段：
1. one_liner (str): 一句话概括视频主旨。
2. key_points (List[str]): 3-5个核心观点。
3. summary (str): 200字左右的内容摘要。
4. facts (List[str]): 视频中提到的关键事实或案例（可选）。
"""
        
        user_prompt = f"视频内容如下：\n{text[:30000]}..." # Truncate to avoid context limit roughly
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
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
            
        system_prompt = """你是一个深度思考的分析师。请根据这位作者的一系列视频摘要，生成一份核心思想报告。
输出必须是合法的 JSON 格式，包含以下字段：
1. core_philosophy (str): 作者的核心思考逻辑或价值观（300字以内）。
2. main_topics (List[str]): 作者常谈论的3-5个主题簇。
3. evolution (str): 观点演化或一贯性分析（可选）。
4. report_markdown (str): 一份完整的 Markdown 格式报告，包含标题、核心命题、支撑论点等。
"""
        
        user_prompt = f"作者过往视频摘要集合：\n{context_text[:30000]}"
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
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
        Uses a rerank model if available, or LLM as fallback.
        For MVP, we use LLM scoring.
        """
        if not self.client:
            return list(range(min(len(documents), top_n)))

        # Simple listwise rerank prompt
        prompt = f"""请针对查询语句，对以下段落进行相关性排序。
查询: {query}

段落列表:
"""
        for i, doc in enumerate(documents):
            prompt += f"[{i}] {doc[:200]}...\n"
            
        prompt += f"\n请返回相关性最高的 {top_n} 个段落的编号列表，格式如 JSON: {{'indices': [0, 2, 1]}}"
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )
            result = json.loads(response.choices[0].message.content)
            indices = result.get("indices", [])
            return [int(i) for i in indices if isinstance(i, (int, str)) and int(i) < len(documents)]
        except Exception as e:
            logger.error(f"Rerank failed: {e}")
            return list(range(min(len(documents), top_n)))
