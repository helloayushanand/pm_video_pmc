"""Central configuration for the local candidate video pipeline."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
APP_DIR = PROJECT_ROOT / "app"
INPUTS_DIR = PROJECT_ROOT / "inputs"
RUNS_DIR = PROJECT_ROOT / "runs"
RENDERER_DIR = PROJECT_ROOT / "renderer" / "remotion-project"
PROMPTS_DIR = APP_DIR / "prompts"

load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    """Runtime settings loaded from environment variables."""

    environment: str = os.getenv("ENVIRONMENT", "development")

    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4.1")
    openai_tts_model: str = os.getenv(
        "OPENAI_TTS_MODEL",
        "gpt-4o-mini-tts",
    )

    openai_tts_voice: str = os.getenv(
        "OPENAI_TTS_VOICE",
        "coral",
    )

    openai_tts_format: str = os.getenv(
        "OPENAI_TTS_FORMAT",
        "mp3",
    )

    openai_transcription_model: str = os.getenv(
        "OPENAI_TRANSCRIPTION_MODEL",
        "whisper-1",
    )
    pdf_render_dpi: int = int(os.getenv("PDF_RENDER_DPI", "150"))

    video_width: int = int(os.getenv("VIDEO_WIDTH", "1920"))
    video_height: int = int(os.getenv("VIDEO_HEIGHT", "1080"))
    video_fps: int = int(os.getenv("VIDEO_FPS", "30"))
    default_video_mode: str = os.getenv(
        "DEFAULT_VIDEO_MODE",
        "automatic",
    )

    include_compensation: bool = (
        os.getenv("INCLUDE_COMPENSATION", "false").lower() == "true"
    )
    include_availability: bool = (
        os.getenv("INCLUDE_AVAILABILITY", "true").lower() == "true"
    )

    log_level: str = os.getenv("LOG_LEVEL", "INFO")


settings = Settings()


def create_project_directories() -> None:
    """Create required project directories."""

    required_directories = [
        INPUTS_DIR,
        RUNS_DIR,
        RENDERER_DIR,
        PROMPTS_DIR,
    ]

    for directory in required_directories:
        directory.mkdir(parents=True, exist_ok=True)


def validate_environment(
    require_openai: bool = False,
):
    """Return missing or invalid environment configuration values."""

    errors = []

    if require_openai and not settings.openai_api_key:
        errors.append(
            "OPENAI_API_KEY is not configured."
        )

    if settings.pdf_render_dpi <= 0:
        errors.append(
            "PDF_RENDER_DPI must be greater than zero."
        )

    if settings.video_width <= 0:
        errors.append(
            "VIDEO_WIDTH must be greater than zero."
        )

    if settings.video_height <= 0:
        errors.append(
            "VIDEO_HEIGHT must be greater than zero."
        )

    if settings.video_fps <= 0:
        errors.append(
            "VIDEO_FPS must be greater than zero."
        )

    return errors
