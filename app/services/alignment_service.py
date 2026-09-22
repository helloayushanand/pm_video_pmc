"""OpenAI transcription and timestamp service."""

import re
from pathlib import Path

from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings
from app.utils.logging import get_logger


logger = get_logger(__name__)


class AlignmentServiceError(Exception):
    """Base exception for timestamp extraction errors."""


class AlignmentConfigurationError(AlignmentServiceError):
    """Raised when OpenAI configuration is incomplete."""


class OpenAIAlignmentService:
    """Generate word and phrase timestamps using OpenAI Whisper."""

    def __init__(
        self,
        api_key=None,
        model=None,
    ):
        self.api_key = api_key or settings.openai_api_key
        self.model = (
            model or settings.openai_transcription_model
        )

        if not self.api_key:
            raise AlignmentConfigurationError(
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
    def align(
        self,
        audio_path,
        transcript=None,
    ):
        """Transcribe generated audio with word-level timestamps."""

        source_path = Path(audio_path).resolve()

        if not source_path.exists():
            raise FileNotFoundError(
                f"Audio file not found: {source_path}"
            )

        logger.info(
            "Requesting OpenAI word timestamps using %s.",
            self.model,
        )

        try:
            with source_path.open("rb") as audio_file:
                response = self.client.audio.transcriptions.create(
                    model=self.model,
                    file=audio_file,
                    response_format="verbose_json",
                    timestamp_granularities=[
                        "word",
                        "segment",
                    ],
                    prompt=(
                        transcript[:1000]
                        if transcript
                        else None
                    ),
                )

        except Exception as error:
            raise AlignmentServiceError(
                f"OpenAI transcription failed: {error}"
            ) from error

        response_data = (
            response.model_dump(mode="json")
            if hasattr(response, "model_dump")
            else dict(response)
        )

        words = self._normalise_words(
            response_data.get("words", [])
        )

        segments = self._normalise_segments(
            response_data.get("segments", [])
        )

        phrases = self._create_phrases(words)

        logger.info(
            "Timestamp extraction completed with "
            "%s words, %s segments and %s phrases.",
            len(words),
            len(segments),
            len(phrases),
        )

        return {
            "provider": "openai",
            "model": self.model,
            "transcribed_text": response_data.get(
                "text",
                "",
            ),
            "language": response_data.get("language"),
            "duration": response_data.get("duration"),
            "words": words,
            "segments": segments,
            "phrases": phrases,
            "raw_response": response_data,
        }

    @staticmethod
    def _normalise_words(provider_words):
        """Normalise OpenAI word timestamp records."""

        words = []

        for index, word in enumerate(provider_words):
            text = str(
                word.get("word")
                or word.get("text")
                or ""
            ).strip()

            start = word.get("start")
            end = word.get("end")

            if not text:
                continue

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
                }
            )

        return words

    @staticmethod
    def _normalise_segments(provider_segments):
        """Normalise OpenAI segment timestamp records."""

        segments = []

        for index, segment in enumerate(provider_segments):
            text = str(
                segment.get("text", "")
            ).strip()

            start = segment.get("start")
            end = segment.get("end")

            if start is None or end is None:
                continue

            segments.append(
                {
                    "segment_id": (
                        f"segment_{index + 1:03d}"
                    ),
                    "text": text,
                    "start": float(start),
                    "end": float(end),
                    "duration": round(
                        float(end) - float(start),
                        3,
                    ),
                }
            )

        return segments

    @staticmethod
    def _create_phrases(
        words,
        maximum_words=8,
        maximum_duration=4.0,
    ):
        """Group word timings into visual animation phrases."""

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

            if (
                ends_sentence
                or len(current_words) >= maximum_words
                or phrase_duration >= maximum_duration
            ):
                phrases.append(
                    OpenAIAlignmentService._make_phrase(
                        current_words,
                        len(phrases),
                    )
                )

                current_words = []

        if current_words:
            phrases.append(
                OpenAIAlignmentService._make_phrase(
                    current_words,
                    len(phrases),
                )
            )

        return phrases

    @staticmethod
    def _make_phrase(words, phrase_index):
        """Create one phrase-level timestamp object."""

        start = words[0]["start"]
        end = words[-1]["end"]

        return {
            "phrase_id": (
                f"phrase_{phrase_index + 1:03d}"
            ),
            "text": " ".join(
                word["text"]
                for word in words
            ),
            "start": start,
            "end": end,
            "duration": round(
                end - start,
                3,
            ),
            "start_word_index": words[0]["index"],
            "end_word_index": words[-1]["index"],
        }