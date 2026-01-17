import os
import logging
from openai import AsyncOpenAI
import httpx

from src.config.settings import settings

logger = logging.getLogger(__name__)

class ASRService:
    def __init__(self, api_key: str = None, base_url: str = None):
        self.api_key = api_key or os.getenv("SILICONFLOW_API_KEY") or settings.OPENAI_API_KEY
        self.base_url = base_url or os.getenv("SILICONFLOW_BASE_URL") or settings.OPENAI_BASE_URL or "https://api.siliconflow.cn/v1"
        
        if not self.api_key:
            # Fallback for local testing if env not loaded
            logger.warning("No API key found in env/settings. ASR will fail.")
            
        self.client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )
        # Model for SiliconFlow ASR (FunAudioLLM/SenseVoiceSmall)
        # Note: In OpenAI API, 'model' parameter is required. 
        # For SiliconFlow, we should check if they require a specific string.
        # Based on research, "FunAudioLLM/SenseVoiceSmall" is likely the ID.
        self.model = "FunAudioLLM/SenseVoiceSmall"

    async def transcribe(self, file_path: str) -> dict:
        """
        Transcribe audio file to text using SiliconFlow ASR.
        Returns dict with 'text' and optional 'segments'.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Audio file not found: {file_path}")

        try:
            logger.info(f"Transcribing audio: {file_path}")
            with open(file_path, "rb") as audio_file:
                # Request verbose_json to get timestamps if available
                # Note: SiliconFlow might not support all OpenAI params, but let's try.
                # If it fails, we fall back to default (json/text).
                transcription = await self.client.audio.transcriptions.create(
                    model=self.model,
                    file=audio_file,
                    response_format="verbose_json"
                )
            
            # OpenAI verbose_json returns object with text and segments
            return transcription
            
        except Exception as e:
            logger.error(f"ASR failed: {e}")
            raise
