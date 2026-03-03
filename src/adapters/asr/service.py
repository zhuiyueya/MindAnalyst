import os
import logging
import subprocess
from typing import Any, Dict, List, Optional, cast

from httpx import Timeout
from openai import AsyncOpenAI
from src.core.config import settings
from src.adapters.asr.types import ASRAdapterError, ASRProvider, AsrSegment, AsrTranscriptionResult

logger = logging.getLogger(__name__)


class OpenAICompatibleASRProvider:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout_s: int,
    ):
        self.name = "openai_compatible"
        self._model = model
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=Timeout(timeout=timeout_s),
        )

    async def transcribe_file(self, file_path: str, *, language: Optional[str] = None) -> AsrTranscriptionResult:
        try:
            with open(file_path, "rb") as audio_file:
                transcription = await self._client.audio.transcriptions.create(
                    model=self._model,
                    file=audio_file,
                    response_format="verbose_json",
                    language=language,
                )
        except Exception as exc:
            raise ASRAdapterError(
                "ASR provider transcription failed",
                operation="transcribe",
                ref=file_path,
                cause=exc,
            ) from exc

        transcription_data: Any = transcription
        if hasattr(transcription, "model_dump"):
            transcription_data = transcription.model_dump()

        parse_warnings: List[str] = []

        if not isinstance(transcription_data, dict):
            parse_warnings.append("asr_response_not_dict")
            return AsrTranscriptionResult(
                text=str(transcription_data),
                segments=[],
                language=None,
                duration_s=None,
                provider=self.name,
                model=self._model,
                parse_warnings=parse_warnings,
            )

        transcription_dict: Dict[str, Any] = cast(Dict[str, Any], transcription_data)
        text_raw: object = transcription_dict.get("text")
        text = str(text_raw) if text_raw is not None else ""

        language_raw: object = transcription_dict.get("language")
        language_out = str(language_raw) if isinstance(language_raw, str) and language_raw.strip() else None

        duration_raw: object = transcription_dict.get("duration")
        duration_s: Optional[float] = None
        if isinstance(duration_raw, (int, float)):
            duration_s = float(duration_raw)

        segments: List[AsrSegment] = []
        segments_raw: object = transcription_dict.get("segments")
        if segments_raw is None:
            parse_warnings.append("asr_segments_missing")
        elif not isinstance(segments_raw, list):
            parse_warnings.append("asr_segments_not_list")
        else:
            segments_list = cast(List[object], segments_raw)
            for idx, seg in enumerate(segments_list):
                if not isinstance(seg, dict):
                    parse_warnings.append(f"asr_segment_not_dict:{idx}")
                    continue

                seg_dict: Dict[str, Any] = cast(Dict[str, Any], seg)
                start: object = seg_dict.get("start", seg_dict.get("from"))
                end: object = seg_dict.get("end", seg_dict.get("to"))
                seg_text: object = seg_dict.get("text") or seg_dict.get("content") or ""

                if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
                    parse_warnings.append(f"asr_segment_time_missing:{idx}")
                    continue

                seg_text_clean = str(seg_text).strip()
                if not seg_text_clean:
                    parse_warnings.append(f"asr_segment_text_empty:{idx}")
                    continue

                segments.append(AsrSegment(start_s=float(start), end_s=float(end), text=seg_text_clean))

        if not text.strip() and segments:
            text = "\n".join(s.text for s in segments)
            parse_warnings.append("asr_text_missing_reconstructed_from_segments")

        return AsrTranscriptionResult(
            text=text,
            segments=segments,
            language=language_out,
            duration_s=duration_s,
            provider=self.name,
            model=self._model,
            parse_warnings=parse_warnings,
        )


class ASRService:
    def __init__(self, provider: Optional[ASRProvider] = None):
        self._provider = provider or self._build_provider_from_settings()

    def _build_provider_from_settings(self) -> ASRProvider:
        provider_name = (settings.ASR_PROVIDER or "").strip() or "openai_compatible"

        if provider_name != "openai_compatible":
            raise ASRAdapterError(
                f"Unsupported ASR_PROVIDER: {provider_name}",
                operation="transcribe",
                ref=provider_name,
            )

        api_key_resolved = (
            settings.ASR_API_KEY
            or os.getenv("SILICONFLOW_API_KEY")
            or settings.OPENAI_API_KEY
            or ""
        )
        base_url_resolved = (
            settings.ASR_BASE_URL
            or os.getenv("SILICONFLOW_BASE_URL")
            or settings.OPENAI_BASE_URL
            or "https://api.siliconflow.cn/v1"
        )
        if not api_key_resolved:
            logger.warning("No ASR API key found in env/settings. ASR will fail.")

        return OpenAICompatibleASRProvider(
            api_key=api_key_resolved,
            base_url=base_url_resolved,
            model=settings.ASR_MODEL,
            timeout_s=settings.ASR_TIMEOUT_S,
        )

    async def transcribe_file(self, file_path: str, *, language: Optional[str] = None) -> AsrTranscriptionResult:
        """
        Transcribe audio file to text using ASR provider.
        Auto-converts unsupported formats (like aac) to mp3.
        Returns strong-typed transcription with parse_warnings.
        """
        if not os.path.exists(file_path):
            raise ASRAdapterError(
                f"Audio file not found: {file_path}",
                operation="transcribe",
                ref=file_path,
            )

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
                    settings.ASR_FFMPEG_BIN, "-y", "-i", file_path, 
                    "-acodec", "libmp3lame", "-q:a", "4", 
                    temp_file
                ], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                target_path = temp_file
                logger.info(f"Converted to {target_path}")
            except subprocess.CalledProcessError as e:
                logger.error(f"FFmpeg conversion failed: {e}")
                raise ASRAdapterError(
                    "Failed to convert audio format",
                    operation="convert_audio",
                    ref=file_path,
                    cause=e,
                ) from e

        try:
            logger.info(f"Transcribing audio: {target_path}")
            return await self._provider.transcribe_file(target_path, language=language)

        except ASRAdapterError:
            raise

        except Exception as exc:
            raise ASRAdapterError(
                "ASR failed",
                operation="transcribe",
                ref=target_path,
                cause=exc,
            ) from exc
        finally:
            # Clean up temp converted file if created
            if temp_file and os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                    logger.info(f"Removed temp file: {temp_file}")
                except Exception:
                    pass
