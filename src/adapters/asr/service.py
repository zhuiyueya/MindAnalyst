import os
import logging
import subprocess
from dataclasses import dataclass
from typing import Any, Optional, cast
from openai import AsyncOpenAI
from src.core.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AsrSegment:
    start: float
    end: float
    text: str


@dataclass(frozen=True, slots=True)
class AsrTranscription:
    text: str
    segments: Optional[list[AsrSegment]] = None

    def model_dump(self) -> dict[str, Any]:
        segments_dump: Optional[list[dict[str, Any]]] = None
        if self.segments is not None:
            segments_dump = [
                {"start": s.start, "end": s.end, "text": s.text}
                for s in self.segments
            ]
        return {"text": self.text, "segments": segments_dump}

class ASRService:
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        api_key_resolved = api_key or os.getenv("SILICONFLOW_API_KEY") or settings.OPENAI_API_KEY
        base_url_resolved = (
            base_url
            or os.getenv("SILICONFLOW_BASE_URL")
            or settings.OPENAI_BASE_URL
            or "https://api.siliconflow.cn/v1"
        )

        # Keep types strict: downstream client expects str.
        # If key is missing, empty string preserves the previous runtime failure behavior.
        self.api_key: str = api_key_resolved or ""
        self.base_url: str = base_url_resolved
        
        if not self.api_key:
            # Fallback for local testing if env not loaded
            logger.warning("No API key found in env/settings. ASR will fail.")
            
        self.client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )
        # Model for SiliconFlow ASR (FunAudioLLM/SenseVoiceSmall)
        self.model = "FunAudioLLM/SenseVoiceSmall"

    async def transcribe(self, file_path: str) -> AsrTranscription:
        """
        Transcribe audio file to text using SiliconFlow ASR.
        Auto-converts unsupported formats (like aac) to mp3.
        Returns transcription with 'text' and optional 'segments'.
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

            transcription_data: Any = transcription
            if hasattr(transcription, "model_dump"):
                transcription_data = transcription.model_dump()

            if isinstance(transcription_data, dict):
                transcription_dict: dict[str, Any] = cast(dict[str, Any], transcription_data)
                text_raw: object = transcription_dict.get("text")
                text = str(text_raw) if text_raw is not None else ""

                segments_raw: object = transcription_dict.get("segments")
                segments: Optional[list[AsrSegment]] = None
                if isinstance(segments_raw, list):
                    parsed: list[AsrSegment] = []
                    segments_list = cast(list[object], segments_raw)
                    for seg in segments_list:
                        if not isinstance(seg, dict):
                            continue
                        seg_dict: dict[str, Any] = cast(dict[str, Any], seg)
                        start: object = seg_dict.get("start", seg_dict.get("from", 0))
                        end: object = seg_dict.get("end", seg_dict.get("to", 0))
                        seg_text: object = seg_dict.get("text") or seg_dict.get("content") or ""
                        if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
                            continue
                        seg_text_clean = str(seg_text).strip()
                        if not seg_text_clean:
                            continue
                        parsed.append(AsrSegment(start=float(start), end=float(end), text=seg_text_clean))
                    segments = parsed

                return AsrTranscription(text=text, segments=segments)

            return AsrTranscription(text=str(transcription_data), segments=None)
            
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
