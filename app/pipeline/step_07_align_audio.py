"""Pipeline Step 07: Generate word and phrase timestamps."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.config import settings
from app.utils.json_utils import save_json
from app.utils.logging import setup_logging
from app.utils.run_manager import RunManager


STEP_NAME = "align_audio"


def build_argument_parser():
    parser = argparse.ArgumentParser(
        description="Align voiceover audio with its transcript."
    )

    parser.add_argument(
        "--run-dir",
        required=True,
    )

    return parser


def align_audio(run_directory):
    run_manager = RunManager(
        Path(run_directory).resolve()
    )

    setup_logging(
        settings.log_level,
        run_manager.get_directory("logs")
        / "pipeline.log",
    )

    audio_directory = run_manager.get_directory(
        "audio"
    )
    output_directory = run_manager.get_directory(
        "alignment"
    )

    audio_path = audio_directory / "voiceover.mp3"
    transcript_path = (
        audio_directory
        / "final_transcript.txt"
    )

    if not audio_path.exists():
        raise FileNotFoundError(
            "Voiceover audio not found. Run Step 06 first."
        )

    if not transcript_path.exists():
        raise FileNotFoundError(
            "Final transcript not found. Run Step 06 first."
        )

    run_manager.start_step(STEP_NAME)

    try:
        from app.services.alignment_service import (
            OpenAIAlignmentService,
        )

        service = OpenAIAlignmentService()

        result = service.align(
            audio_path=audio_path,
            transcript=transcript_path.read_text(
                encoding="utf-8-sig"
            ),
        )

        words = result.get("words", [])
        phrases = result.get("phrases", [])

        segments = result.get("segments", [])

        save_json(
            segments,
            output_directory / "segments.json",
        )

        save_json(
            words,
            output_directory / "words.json",
        )

        save_json(
            phrases,
            output_directory / "phrases.json",
        )

        save_json(
            result,
            output_directory
            / "alignment_raw_response.json",
        )

        metadata = {
            "provider": "openai",
            "word_count": len(words),
            "phrase_count": len(phrases),
            "segment_count": len(segments),
            "audio_path": str(audio_path),
        }

        save_json(
            metadata,
            output_directory
            / "alignment_metadata.json",
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
        metadata = align_audio(
            arguments.run_dir
        )

        print()
        print("STEP 07 COMPLETED")
        print(
            f"Aligned words: {metadata['word_count']}"
        )
        print()

        return 0

    except Exception as error:
        print()
        print("STEP 07 FAILED")
        print(f"{type(error).__name__}: {error}")
        print()

        return 1


if __name__ == "__main__":
    sys.exit(main())
