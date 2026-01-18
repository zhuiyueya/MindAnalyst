import os
import httpx
import logging
import subprocess
from typing import Optional, Dict, Any
from openai import AsyncOpenAI
from src.core.config import settings

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
        self.model = "FunAudioLLM/SenseVoiceSmall"

    async def transcribe(self, file_path: str) -> dict:
        """
        Transcribe audio file to text using SiliconFlow ASR.
        Auto-converts unsupported formats (like aac) to mp3.
        Returns dict with 'text' and optional 'segments'.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Audio file not found: {file_path}")

        temp_file = None
        target_path = file_path

        # Check format and convert if needed
        # Supported by SiliconFlow: wav, mp3, pcm, opus, webm
        ext = os.path.splitext(file_path)[1].lower()
        if ext not in ['.wav', '.mp3', '.pcm', '.opus', '.webm']:
            logger.info(f"Unsupported format {ext}, converting to mp3...")
            temp_file = os.path.splitext(file_path)[0] + "_converted.mp3"
            try:
                # Convert to mp3 using ffmpeg
                subprocess.run([
                    "ffmpeg", "-y", "-i", file_path, 
                    "-acodec", "libmp3lame", "-q:a", "4", 
                    temp_file
                ], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                target_path = temp_file
                logger.info(f"Converted to {target_path}")
            except subprocess.CalledProcessError as e:
                logger.error(f"FFmpeg conversion failed: {e}")
                raise RuntimeError(f"Failed to convert audio format: {e}")

        try:
            logger.info(f"Transcribing audio: {target_path}")
            with open(target_path, "rb") as audio_file:
                # Request verbose_json to get timestamps if available
                transcription = await self.client.audio.transcriptions.create(
                    model=self.model,
                    file=audio_file,
                    response_format="verbose_json"
                )
            
            return transcription
            
        except Exception as e:
            logger.error(f"ASR failed: {e}")
            raise
        finally:
            # Clean up temp converted file if created
            if temp_file and os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                    logger.info(f"Removed temp file: {temp_file}")
                except Exception:
                    pass
