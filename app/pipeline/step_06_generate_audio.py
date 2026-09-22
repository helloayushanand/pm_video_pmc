"""Pipeline Step 06: Generate voiceover audio using OpenAI TTS."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.config import settings
from app.services.audio_service import OpenAIAudioService
from app.utils.json_utils import save_json
from app.utils.logging import setup_logging
from app.utils.run_manager import RunManager


STEP_NAME = "generate_audio"

DEFAULT_SPEAKING_INSTRUCTIONS = (
    "Speak in a polished, measured, professional business-news style. "
    "Maintain a confident but neutral tone. "
    "Use clear pronunciation for company names, job titles, percentages, "
    "currencies, and large numbers. "
    "Use brief natural pauses between ideas. "
    "Do not sound promotional or overly enthusiastic."
)


def build_argument_parser():
    """Create the command-line argument parser."""

    parser = argparse.ArgumentParser(
        description="Generate narration audio using OpenAI TTS."
    )

    parser.add_argument(
        "--run-dir",
        required=True,
        help=(
            "Path to an existing pipeline run directory "
            "containing the Step 05 storyboard output."
        ),
    )

    parser.add_argument(
        "--voice",
        default=settings.openai_tts_voice,
        help=(
            "OpenAI text-to-speech voice. "
            f"Default: {settings.openai_tts_voice}"
        ),
    )

    parser.add_argument(
        "--tts-model",
        default=settings.openai_tts_model,
        help=(
            "OpenAI text-to-speech model. "
            f"Default: {settings.openai_tts_model}"
        ),
    )

    parser.add_argument(
        "--instructions",
        default=DEFAULT_SPEAKING_INSTRUCTIONS,
        help=(
            "Speaking-style instructions supplied to the "
            "OpenAI text-to-speech model."
        ),
    )

    return parser


def generate_audio(
    run_directory,
    voice=None,
    model=None,
    instructions=None,
):
    """Generate the complete candidate-video voiceover."""

    run_manager = RunManager(
        Path(run_directory).expanduser().resolve()
    )

    setup_logging(
        settings.log_level,
        run_manager.get_directory("logs")
        / "pipeline.log",
    )

    storyboard_directory = run_manager.get_directory(
        "storyboard"
    )

    output_directory = run_manager.get_directory(
        "audio"
    )

    transcript_path = (
        storyboard_directory
        / "voiceover.txt"
    )

    if not transcript_path.exists():
        raise FileNotFoundError(
            "Voiceover transcript was not found. "
            "Run Step 05 before generating audio. "
            f"Expected file: {transcript_path}"
        )

    transcript = transcript_path.read_text(
        encoding="utf-8-sig"
    ).strip()

    if not transcript:
        raise ValueError(
            "The Step 05 voiceover transcript is empty."
        )

    selected_voice = (
        voice or settings.openai_tts_voice
    )

    selected_model = (
        model or settings.openai_tts_model
    )

    selected_instructions = (
        instructions or DEFAULT_SPEAKING_INSTRUCTIONS
    )

    run_manager.start_step(STEP_NAME)

    try:
        service = OpenAIAudioService(
            voice=selected_voice,
            model=selected_model,
            response_format=settings.openai_tts_format,
        )

        audio_path = (
            output_directory
            / "voiceover.mp3"
        )

        result = service.generate_speech(
            text=transcript,
            output_path=audio_path,
            instructions=selected_instructions,
        )

        final_transcript_path = (
            output_directory
            / "final_transcript.txt"
        )

        final_transcript_path.write_text(
            transcript,
            encoding="utf-8",
        )

        tts_request_metadata = {
            "provider": "openai",
            "model": selected_model,
            "voice": selected_voice,
            "response_format": (
                settings.openai_tts_format
            ),
            "instructions": selected_instructions,
            "character_count": len(transcript),
            "source_transcript": str(
                transcript_path
            ),
            "ai_generated_voice": True,
        }

        tts_request_path = (
            output_directory
            / "tts_request.json"
        )

        save_json(
            tts_request_metadata,
            tts_request_path,
        )

        metadata = {
            "provider": "openai",
            "model": selected_model,
            "voice": selected_voice,
            "audio_path": str(audio_path),
            "transcript_path": str(
                final_transcript_path
            ),
            "tts_request_path": str(
                tts_request_path
            ),
            "ai_generated_voice": True,
            "result": result,
        }

        audio_metadata_path = (
            output_directory
            / "audio_metadata.json"
        )

        save_json(
            metadata,
            audio_metadata_path,
        )

        run_manager.complete_step(
            STEP_NAME,
            outputs={
                "provider": "openai",
                "model": selected_model,
                "voice": selected_voice,
                "audio_path": str(audio_path),
                "transcript_path": str(
                    final_transcript_path
                ),
                "audio_metadata": str(
                    audio_metadata_path
                ),
                "tts_request": str(
                    tts_request_path
                ),
                "duration_seconds": result.get(
                    "duration_seconds"
                ),
                "ai_generated_voice": True,
            },
        )

        return metadata

    except Exception as error:
        run_manager.fail_step(
            STEP_NAME,
            f"{type(error).__name__}: {error}",
        )

        raise


def print_result_summary(metadata):
    """Print a safe summary of the generated audio."""

    result = metadata.get("result", {})

    print()
    print("=" * 72)
    print("STEP 06 COMPLETED")
    print("=" * 72)
    print(f"Provider:      {metadata['provider']}")
    print(f"Model:         {metadata['model']}")
    print(f"Voice:         {metadata['voice']}")
    print(f"Audio:         {metadata['audio_path']}")
    print(
        "Duration:      "
        f"{result.get('duration_seconds', 'unknown')} seconds"
    )
    print(f"Transcript:    {metadata['transcript_path']}")
    print("Voice type:    AI-generated")
    print("=" * 72)
    print()


def main():
    """Run Step 06 from the command line."""

    parser = build_argument_parser()
    arguments = parser.parse_args()

    try:
        metadata = generate_audio(
            run_directory=arguments.run_dir,
            voice=arguments.voice,
            model=arguments.tts_model,
            instructions=arguments.instructions,
        )

        print_result_summary(metadata)
        return 0

    except Exception as error:
        print()
        print("=" * 72)
        print("STEP 06 FAILED")
        print("=" * 72)
        print(
            f"Error type: {type(error).__name__}"
        )
        print(f"Details:    {error}")
        print()
        print(
            "Check the run's logs/pipeline.log file "
            "for additional details."
        )
        print("=" * 72)
        print()

        return 1


if __name__ == "__main__":
    sys.exit(main())