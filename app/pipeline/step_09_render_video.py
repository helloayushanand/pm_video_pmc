"""Pipeline Step 09: Render the candidate video."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.config import settings
from app.utils.json_utils import load_json, save_json
from app.utils.logging import setup_logging
from app.utils.run_manager import RunManager


STEP_NAME = "render_video"


def build_argument_parser():
    parser = argparse.ArgumentParser(
        description="Render the candidate video using Remotion."
    )

    parser.add_argument(
        "--run-dir",
        required=True,
    )

    return parser


def render_video(run_directory):
    run_manager = RunManager(
        Path(run_directory).resolve()
    )

    setup_logging(
        settings.log_level,
        run_manager.get_directory("logs")
        / "pipeline.log",
    )

    render_spec_path = (
        run_manager.get_directory("render_spec")
        / "render_spec.json"
    )

    video_directory = run_manager.get_directory(
        "video"
    )

    if not render_spec_path.exists():
        raise FileNotFoundError(
            "Render specification not found. "
            "Run Step 08 first."
        )

    run_manager.start_step(STEP_NAME)

    try:
        from app.services.render_service import RemotionRenderService

        service = RemotionRenderService()

        output_path = (
            video_directory
            / "candidate_snapshot.mp4"
        )

        result = service.render(
            render_spec_path=render_spec_path,
            output_path=output_path,
        )

        metadata = {
            "output_path": str(output_path),
            "result": result,
        }

        save_json(
            metadata,
            video_directory
            / "render_metadata.json",
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
        result = render_video(
            arguments.run_dir
        )

        print()
        print("STEP 09 COMPLETED")
        print(f"Video: {result['output_path']}")
        print()

        return 0

    except Exception as error:
        print()
        print("STEP 09 FAILED")
        print(f"{type(error).__name__}: {error}")
        print()

        return 1


if __name__ == "__main__":
    sys.exit(main())
