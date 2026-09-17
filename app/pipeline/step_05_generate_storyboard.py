"""Pipeline Step 05: Generate the storyboard and narration."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.config import settings
from app.schemas.storyboard import Storyboard
from app.schemas.video_content import VideoContent
from app.utils.json_utils import load_json, save_json
from app.utils.logging import setup_logging
from app.utils.run_manager import RunManager


STEP_NAME = "generate_storyboard"


def build_argument_parser():
    parser = argparse.ArgumentParser(
        description="Generate a candidate-video storyboard."
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


def create_markdown_preview(storyboard):
    lines = [
        f"# {storyboard.title}",
        "",
        f"Candidate: {storyboard.candidate_name}",
        "",
        (
            "Estimated duration: "
            f"{storyboard.estimated_total_duration_seconds} seconds"
        ),
        "",
    ]

    for index, scene in enumerate(
        storyboard.scenes,
        start=1,
    ):
        lines.extend(
            [
                f"## Scene {index}: {scene.scene_type.value}",
                "",
                f"Purpose: {scene.purpose}",
                "",
                (
                    "Estimated duration: "
                    f"{scene.estimated_duration_seconds} seconds"
                ),
                "",
                "### Voiceover",
                "",
                scene.complete_voiceover or "[No voiceover]",
                "",
                "### Visual elements",
                "",
            ]
        )

        for element in scene.visual_elements:
            content = (
                element.content
                or element.value
                or element.label
                or element.asset_id
                or ""
            )

            lines.append(
                f"- {element.element_type.value}: {content}"
            )

        lines.append("")

    return "\n".join(lines)


def generate_storyboard(
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

    content_path = (
        run_manager.get_directory("video_content")
        / "video_content.json"
    )

    output_directory = run_manager.get_directory(
        "storyboard"
    )

    if not content_path.exists():
        raise FileNotFoundError(
            "Video content not found. Run Step 04 first."
        )

    run_manager.start_step(STEP_NAME)

    try:
        video_content = VideoContent.model_validate(
            load_json(content_path)
        )

        from app.services.vlm_service import OpenAIVLMService

        service = OpenAIVLMService(
            model=model or settings.openai_model
        )

        if not hasattr(
            service,
            "generate_storyboard",
        ):
            raise NotImplementedError(
                "OpenAIVLMService.generate_storyboard has not "
                "yet been added. Populate the storyboard-generation "
                "service before running Step 05."
            )

        storyboard = service.generate_storyboard(
            video_content=video_content,
            output_directory=output_directory,
        )

        if not isinstance(storyboard, Storyboard):
            storyboard = Storyboard.model_validate(
                storyboard
            )

        storyboard_path = (
            output_directory
            / "storyboard.json"
        )

        voiceover_path = (
            output_directory
            / "voiceover.txt"
        )

        segments_path = (
            output_directory
            / "voiceover_segments.json"
        )

        preview_path = (
            output_directory
            / "storyboard_preview.md"
        )

        save_json(
            storyboard.model_dump(mode="json"),
            storyboard_path,
        )

        voiceover_path.write_text(
            storyboard.complete_voiceover,
            encoding="utf-8",
        )

        segments = []

        for scene in storyboard.scenes:
            for segment in scene.voiceover_segments:
                segments.append(
                    {
                        "scene_id": scene.scene_id,
                        **segment.model_dump(mode="json"),
                    }
                )

        save_json(
            segments,
            segments_path,
        )

        preview_path.write_text(
            create_markdown_preview(storyboard),
            encoding="utf-8",
        )

        run_manager.complete_step(
            STEP_NAME,
            outputs={
                "storyboard": str(storyboard_path),
                "voiceover": str(voiceover_path),
                "preview": str(preview_path),
                "scene_count": len(storyboard.scenes),
            },
        )

        return storyboard

    except Exception as error:
        run_manager.fail_step(
            STEP_NAME,
            f"{type(error).__name__}: {error}",
        )
        raise


def main():
    arguments = build_argument_parser().parse_args()

    try:
        storyboard = generate_storyboard(
            arguments.run_dir,
            arguments.model,
        )

        print()
        print("STEP 05 COMPLETED")
        print(f"Scenes: {len(storyboard.scenes)}")
        print(
            "Estimated duration: "
            f"{storyboard.estimated_total_duration_seconds} seconds"
        )
        print()

        return 0

    except Exception as error:
        print()
        print("STEP 05 FAILED")
        print(f"{type(error).__name__}: {error}")
        print()

        return 1


if __name__ == "__main__":
    sys.exit(main())
