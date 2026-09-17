"""Pipeline Step 06: Generate voiceover audio."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.config import settings
from app.utils.json_utils import save_json
from app.utils.logging import setup_logging
from app.utils.run_manager import RunManager


STEP_NAME = "generate_audio"


def build_argument_parser():
    parser = argparse.ArgumentParser(
        description="Generate narration audio with ElevenLabs."
    )

    parser.add_argument(
        "--run-dir",
        required=True,
    )

    parser.add_argument(
        "--voice-id",
        default=settings.elevenlabs_voice_id,
    )

    return parser


def generate_audio(
    run_directory,
    voice_id=None,
):
    run_manager = RunManager(
        Path(run_directory).resolve()
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
            "Voiceover transcript not found. Run Step 05 first."
        )

    transcript = transcript_path.read_text(
        encoding="utf-8-sig"
    ).strip()

    if not transcript:
        raise ValueError(
            "Voiceover transcript is empty."
        )

    run_manager.start_step(STEP_NAME)

    try:
        from app.services.audio_service import ElevenLabsAudioService

        service = ElevenLabsAudioService(
            voice_id=voice_id,
        )

        audio_path = (
            output_directory
            / "voiceover.mp3"
        )

        result = service.generate_speech(
            text=transcript,
            output_path=audio_path,
        )

        final_transcript_path = (
            output_directory
            / "final_transcript.txt"
        )

        final_transcript_path.write_text(
            transcript,
            encoding="utf-8",
        )

        metadata = {
            "voice_id": voice_id,
            "audio_path": str(audio_path),
            "transcript_path": str(
                final_transcript_path
            ),
            "result": result,
        }

        save_json(
            metadata,
            output_directory
            / "audio_metadata.json",
        )

        run_manager.complete_step(
            STEP_NAME,
            outputs=metadata,
        )

        return metadata

    except Exception as error:
        run_manager.fail_step(
            STEP_NAME,
            f"{type(error).__name__}: {error}",
        )
        raise


def main():
    arguments = build_argument_parser().parse_args()

    try:
        metadata = generate_audio(
            arguments.run_dir,
            arguments.voice_id,
        )

        print()
        print("STEP 06 COMPLETED")
        print(f"Audio: {metadata['audio_path']}")
        print()

        return 0

    except Exception as error:
        print()
        print("STEP 06 FAILED")
        print(f"{type(error).__name__}: {error}")
        print()

        return 1


if __name__ == "__main__":
    sys.exit(main())
