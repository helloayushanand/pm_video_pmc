"""Pipeline Step 04: Select dossier content for the video."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.config import settings
from app.schemas.dossier import Dossier
from app.schemas.video_content import VideoContent
from app.utils.json_utils import load_json, save_json
from app.utils.logging import setup_logging
from app.utils.run_manager import RunManager


STEP_NAME = "select_video_content"


def build_argument_parser():
    parser = argparse.ArgumentParser(
        description="Select candidate content for video generation."
    )

    parser.add_argument(
        "--run-dir",
        required=True,
    )

    parser.add_argument(
        "--model",
        default=settings.openai_model,
    )

    return parser


def select_video_content(
    run_directory,
    model=None,
):
    run_manager = RunManager(
        Path(run_directory).resolve()
    )

    setup_logging(
        settings.log_level,
        run_manager.get_directory("logs")
        / "pipeline.log",
    )

    validated_path = (
        run_manager.get_directory("validation")
        / "dossier_validated.json"
    )

    output_directory = run_manager.get_directory(
        "video_content"
    )

    if not validated_path.exists():
        raise FileNotFoundError(
            "Validated dossier not found. Run Step 03 first."
        )

    run_manager.start_step(STEP_NAME)

    try:
        dossier = Dossier.model_validate(
            load_json(validated_path)
        )

        from app.services.vlm_service import OpenAIVLMService

        service = OpenAIVLMService(
            model=model or settings.openai_model
        )

        if not hasattr(
            service,
            "select_video_content",
        ):
            raise NotImplementedError(
                "OpenAIVLMService.select_video_content has not "
                "yet been added. Populate the content-selection "
                "service before running Step 04."
            )

        configuration = run_manager.state.get(
            "configuration",
            {},
        )

        content = service.select_video_content(
            dossier=dossier,
            output_directory=output_directory,
            include_compensation=configuration.get(
                "include_compensation",
                False,
            ),
            include_availability=configuration.get(
                "include_availability",
                True,
            ),
            video_mode=configuration.get(
                "video_mode",
                "automatic",
            ),
        )

        if not isinstance(content, VideoContent):
            content = VideoContent.model_validate(content)

        output_path = (
            output_directory
            / "video_content.json"
        )

        save_json(
            content.model_dump(mode="json"),
            output_path,
        )

        run_manager.complete_step(
            STEP_NAME,
            outputs={
                "video_content": str(output_path),
                "selected_highlights": len(
                    content.selected_highlights
                ),
                "career_milestones": len(
                    content.career_milestones
                ),
            },
        )

        return content

    except Exception as error:
        run_manager.fail_step(
            STEP_NAME,
            f"{type(error).__name__}: {error}",
        )
        raise


def main():
    arguments = build_argument_parser().parse_args()

    try:
        content = select_video_content(
            run_directory=arguments.run_dir,
            model=arguments.model,
        )

        print()
        print("STEP 04 COMPLETED")
        print(
            f"Candidate: {content.candidate_intro.name}"
        )
        print(
            "Selected highlights: "
            f"{len(content.selected_highlights)}"
        )
        print()

        return 0

    except Exception as error:
        print()
        print("STEP 04 FAILED")
        print(f"{type(error).__name__}: {error}")
        print()

        return 1


if __name__ == "__main__":
    sys.exit(main())
