"""ElevenLabs text-to-speech service."""

from __future__ import annotations

from pathlib import Path

import httpx
from mutagen.mp3 import MP3
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings
from app.utils.logging import get_logger


logger = get_logger(__name__)


class AudioServiceError(Exception):
    """Base exception for audio-generation errors."""


class AudioConfigurationError(AudioServiceError):
    """Raised when ElevenLabs configuration is incomplete."""


class ElevenLabsAudioService:
    """Generate voiceover audio using ElevenLabs."""

    API_BASE_URL = "https://api.elevenlabs.io/v1"

    def __init__(
        self,
        api_key=None,
        voice_id=None,
        model_id=None,
        timeout_seconds=180,
    ):
        self.api_key = api_key or settings.elevenlabs_api_key
        self.voice_id = voice_id or settings.elevenlabs_voice_id
        self.model_id = (
            model_id or settings.elevenlabs_model_id
        )
        self.timeout_seconds = timeout_seconds

        if not self.api_key:
            raise AudioConfigurationError(
                "ELEVENLABS_API_KEY is not configured in .env."
            )

        if not self.voice_id:
            raise AudioConfigurationError(
                "ELEVENLABS_VOICE_ID is not configured in .env."
            )

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
        stability=0.55,
        similarity_boost=0.75,
        style=0.1,
        use_speaker_boost=True,
    ):
        """Generate an MP3 voiceover from the supplied transcript."""

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

        url = (
            f"{self.API_BASE_URL}/text-to-speech/"
            f"{self.voice_id}"
        )

        headers = {
            "xi-api-key": self.api_key,
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
        }

        payload = {
            "text": transcript,
            "model_id": self.model_id,
            "voice_settings": {
                "stability": stability,
                "similarity_boost": similarity_boost,
                "style": style,
                "use_speaker_boost": use_speaker_boost,
            },
        }

        logger.info(
            "Generating ElevenLabs voiceover using voice %s.",
            self.voice_id,
        )

        with httpx.Client(
            timeout=self.timeout_seconds
        ) as client:
            response = client.post(
                url,
                headers=headers,
                json=payload,
            )

        if response.status_code >= 400:
            raise AudioServiceError(
                "ElevenLabs TTS request failed with status "
                f"{response.status_code}: {response.text}"
            )

        destination.write_bytes(response.content)

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
            bitrate = getattr(audio.info, "bitrate", None)
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
            "Voiceover generated successfully. Duration: %.2f seconds.",
            duration_seconds,
        )

        return {
            "provider": "elevenlabs",
            "voice_id": self.voice_id,
            "model_id": self.model_id,
            "output_path": str(destination),
            "file_size_bytes": destination.stat().st_size,
            "duration_seconds": round(
                duration_seconds,
                3,
            ),
            "bitrate": bitrate,
            "sample_rate": sample_rate,
            "character_count": len(transcript),
        }
