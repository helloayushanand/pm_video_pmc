"""OpenAI text-to-speech service."""

from pathlib import Path

from mutagen.mp3 import MP3
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings
from app.utils.logging import get_logger


logger = get_logger(__name__)


class AudioServiceError(Exception):
    """Base exception for audio-generation errors."""


class AudioConfigurationError(AudioServiceError):
    """Raised when OpenAI audio configuration is incomplete."""


class OpenAIAudioService:
    """Generate professional narration using OpenAI TTS."""

    def __init__(
        self,
        api_key=None,
        model=None,
        voice=None,
        response_format=None,
    ):
        self.api_key = api_key or settings.openai_api_key
        self.model = model or settings.openai_tts_model
        self.voice = voice or settings.openai_tts_voice
        self.response_format = (
            response_format or settings.openai_tts_format
        )

        if not self.api_key:
            raise AudioConfigurationError(
                "OPENAI_API_KEY is not configured in .env."
            )

        self.client = OpenAI(api_key=self.api_key)

    @retry(
        wait=wait_exponential(
            multiplier=2,
            min=2,
            max=20,
        ),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def generate_speech(
        self,
        text,
        output_path,
        instructions=None,
    ):
        """Generate narration and save it as an audio file."""

        transcript = str(text).strip()

        if not transcript:
            raise AudioServiceError(
                "Cannot generate audio from an empty transcript."
            )

        destination = Path(output_path).resolve()

        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        speech_instructions = instructions or (
            "Speak in a polished, measured, professional "
            "business-news style. Maintain a confident but "
            "neutral tone. Use clear pronunciation for company "
            "names, job titles, percentages, currencies and large "
            "numbers. Use brief natural pauses between ideas. "
            "Do not sound promotional or overly enthusiastic."
        )

        logger.info(
            "Generating OpenAI narration using model %s and voice %s.",
            self.model,
            self.voice,
        )

        try:
            with self.client.audio.speech.with_streaming_response.create(
                model=self.model,
                voice=self.voice,
                input=transcript,
                instructions=speech_instructions,
                response_format=self.response_format,
            ) as response:
                response.stream_to_file(destination)

        except Exception as error:
            raise AudioServiceError(
                f"OpenAI TTS generation failed: {error}"
            ) from error

        if not destination.exists():
            raise AudioServiceError(
                "Audio output was not created."
            )

        if destination.stat().st_size == 0:
            raise AudioServiceError(
                "Audio output is empty."
            )

        try:
            audio = MP3(destination)
            duration_seconds = float(audio.info.length)
            bitrate = getattr(
                audio.info,
                "bitrate",
                None,
            )
            sample_rate = getattr(
                audio.info,
                "sample_rate",
                None,
            )

        except Exception as error:
            raise AudioServiceError(
                f"Generated MP3 could not be inspected: {error}"
            ) from error

        logger.info(
            "OpenAI narration created successfully. "
            "Duration: %.2f seconds.",
            duration_seconds,
        )

        return {
            "provider": "openai",
            "model": self.model,
            "voice": self.voice,
            "response_format": self.response_format,
            "output_path": str(destination),
            "file_size_bytes": destination.stat().st_size,
            "duration_seconds": round(
                duration_seconds,
                3,
            ),
            "bitrate": bitrate,
            "sample_rate": sample_rate,
            "character_count": len(transcript),
            "ai_generated_voice": True,
        }