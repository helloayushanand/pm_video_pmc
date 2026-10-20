"""Generate text-to-speech audio for scene narrations via OpenAI TTS."""

from __future__ import annotations

from pathlib import Path

from openai import OpenAI

from app.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


class TTSService:
    def __init__(self):
        self.client = OpenAI(api_key=settings.openai_api_key)
        self.model = settings.openai_tts_model
        self.voice = settings.openai_tts_voice
        self.fmt = settings.openai_tts_format

    def generate_scene_audio(
        self,
        scenes: list,
        output_dir: Path,
    ) -> list[dict]:
        """Generate TTS audio for each scene's narration.

        Returns list of dicts: {scene_id, audio_path, duration_seconds}.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        results = []

        for scene in scenes:
            narration = getattr(scene, "narration", None) or (
                scene.get("narration") if isinstance(scene, dict) else None
            )
            scene_id = getattr(scene, "scene_id", None) or (
                scene.get("scene_id") if isinstance(scene, dict) else None
            )
            if not narration or not scene_id:
                continue

            audio_path = output_dir / f"{scene_id}.{self.fmt}"
            logger.info("Generating TTS for scene %s (%d chars)…", scene_id, len(narration))

            try:
                response = self.client.audio.speech.create(
                    model=self.model,
                    voice=self.voice,
                    input=narration,
                    response_format=self.fmt,
                )
                response.stream_to_file(str(audio_path))

                duration = self._get_duration(audio_path)
                logger.info("  → %s (%.1fs)", audio_path.name, duration)

                results.append({
                    "scene_id": scene_id,
                    "audio_path": str(audio_path),
                    "duration_seconds": duration,
                })
            except Exception as exc:
                logger.warning("TTS failed for scene %s: %s", scene_id, exc)

        return results

    @staticmethod
    def _get_duration(path: Path) -> float:
        ext = path.suffix.lower()
        if ext == ".mp3":
            from mutagen.mp3 import MP3
            return MP3(str(path)).info.length
        if ext == ".wav":
            import wave
            with wave.open(str(path), "rb") as w:
                return w.getnframes() / w.getframerate()
        # fallback: estimate from file size (mp3 ~16kB/s for tts-1)
        return path.stat().st_size / 16_000
