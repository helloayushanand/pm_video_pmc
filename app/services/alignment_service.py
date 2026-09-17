"""ElevenLabs forced-alignment service."""

from __future__ import annotations

import re
from pathlib import Path

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings
from app.utils.logging import get_logger


logger = get_logger(__name__)


class AlignmentServiceError(Exception):
    """Base exception for audio-alignment errors."""


class AlignmentConfigurationError(AlignmentServiceError):
    """Raised when ElevenLabs configuration is incomplete."""


class ElevenLabsAlignmentService:
    """Align narration audio against its exact transcript."""

    ALIGNMENT_URL = (
        "https://api.elevenlabs.io/v1/forced-alignment"
    )

    def __init__(
        self,
        api_key=None,
        timeout_seconds=300,
    ):
        self.api_key = api_key or settings.elevenlabs_api_key
        self.timeout_seconds = timeout_seconds

        if not self.api_key:
            raise AlignmentConfigurationError(
                "ELEVENLABS_API_KEY is not configured in .env."
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
    def align(
        self,
        audio_path,
        transcript,
    ):
        """Return word and phrase timestamps."""

        source_path = Path(audio_path).resolve()
        clean_transcript = str(transcript).strip()

        if not source_path.exists():
            raise FileNotFoundError(
                f"Audio file not found: {source_path}"
            )

        if not clean_transcript:
            raise AlignmentServiceError(
                "Alignment transcript is empty."
            )

        headers = {
            "xi-api-key": self.api_key,
        }

        logger.info(
            "Submitting voiceover for forced alignment."
        )

        with source_path.open("rb") as audio_handle:
            files = {
                "file": (
                    source_path.name,
                    audio_handle,
                    "audio/mpeg",
                )
            }

            data = {
                "text": clean_transcript,
            }

            with httpx.Client(
                timeout=self.timeout_seconds
            ) as client:
                response = client.post(
                    self.ALIGNMENT_URL,
                    headers=headers,
                    files=files,
                    data=data,
                )

        if response.status_code >= 400:
            raise AlignmentServiceError(
                "ElevenLabs alignment failed with status "
                f"{response.status_code}: {response.text}"
            )

        provider_result = response.json()

        words = self._normalise_words(
            provider_result.get("words", [])
        )

        phrases = self._create_phrases(words)

        logger.info(
            "Alignment completed with %s words and %s phrases.",
            len(words),
            len(phrases),
        )

        return {
            "provider": "elevenlabs",
            "words": words,
            "phrases": phrases,
            "characters": provider_result.get(
                "characters",
                [],
            ),
            "loss": provider_result.get("loss"),
        }

    @staticmethod
    def _normalise_words(provider_words):
        """Normalise provider timestamps."""

        words = []

        for index, word in enumerate(provider_words):
            text = str(word.get("text", "")).strip()

            if not text:
                continue

            start = word.get("start")
            end = word.get("end")

            if start is None or end is None:
                continue

            words.append(
                {
                    "index": index,
                    "text": text,
                    "start": float(start),
                    "end": float(end),
                    "duration": round(
                        float(end) - float(start),
                        3,
                    ),
                    "loss": word.get("loss"),
                }
            )

        return words

    @staticmethod
    def _create_phrases(
        words,
        maximum_words=8,
        maximum_duration=4.0,
    ):
        """Group aligned words into animation-friendly phrases."""

        if not words:
            return []

        phrases = []
        current_words = []

        for word in words:
            current_words.append(word)

            phrase_start = current_words[0]["start"]
            phrase_end = current_words[-1]["end"]
            phrase_duration = phrase_end - phrase_start

            ends_sentence = bool(
                re.search(
                    r"[.!?;:]$",
                    current_words[-1]["text"],
                )
            )

            reached_word_limit = (
                len(current_words) >= maximum_words
            )

            reached_duration_limit = (
                phrase_duration >= maximum_duration
            )

            if (
                ends_sentence
                or reached_word_limit
                or reached_duration_limit
            ):
                phrases.append(
                    ElevenLabsAlignmentService._make_phrase(
                        current_words,
                        len(phrases),
                    )
                )

                current_words = []

        if current_words:
            phrases.append(
                ElevenLabsAlignmentService._make_phrase(
                    current_words,
                    len(phrases),
                )
            )

        return phrases

    @staticmethod
    def _make_phrase(words, phrase_index):
        """Create one phrase record."""

        start = words[0]["start"]
        end = words[-1]["end"]

        return {
            "phrase_id": f"phrase_{phrase_index + 1:03d}",
            "text": " ".join(
                word["text"]
                for word in words
            ),
            "start": start,
            "end": end,
            "duration": round(end - start, 3),
            "start_word_index": words[0]["index"],
            "end_word_index": words[-1]["index"],
        }
