"""Pipeline Step 08: Compile the frame-level render specification."""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path
from uuid import uuid4

from mutagen.mp3 import MP3

from app.config import settings
from app.schemas.render_spec import (
    AudioTrack,
    RenderScene,
    RenderSpecification,
    RenderVideoSettings,
    ThemeSettings,
)
from app.schemas.storyboard import Storyboard
from app.utils.json_utils import load_json, save_json
from app.utils.logging import setup_logging
from app.utils.run_manager import RunManager


STEP_NAME = "compile_render_spec"


SCENE_COMPONENTS = {
    "candidate_intro": "CandidateIntro",
    "executive_summary": "ExecutiveSummary",
    "career_timeline": "CareerTimeline",
    "career_milestone": "CareerMilestone",
    "quantified_highlights": "MetricHighlights",
    "single_highlight": "SingleHighlight",
    "leadership_scope": "LeadershipScope",
    "organisation_structure": "OrganisationStructure",
    "strength_summary": "StrengthSummary",
    "compensation_availability": "ConfidentialDetails",
    "closing": "ClosingScene",
}


def build_argument_parser():
    parser = argparse.ArgumentParser(
        description="Compile the final renderer JSON."
    )

    parser.add_argument(
        "--run-dir",
        required=True,
    )

    return parser


def compile_render_spec(run_directory):
    run_manager = RunManager(
        Path(run_directory).resolve()
    )

    setup_logging(
        settings.log_level,
        run_manager.get_directory("logs")
        / "pipeline.log",
    )

    storyboard_path = (
        run_manager.get_directory("storyboard")
        / "storyboard.json"
    )

    audio_path = (
        run_manager.get_directory("audio")
        / "voiceover.mp3"
    )

    output_directory = run_manager.get_directory(
        "render_spec"
    )

    if not storyboard_path.exists():
        raise FileNotFoundError(
            "Storyboard not found. Run Step 05 first."
        )

    if not audio_path.exists():
        raise FileNotFoundError(
            "Audio not found. Run Step 06 first."
        )

    run_manager.start_step(STEP_NAME)

    try:
        storyboard = Storyboard.model_validate(
            load_json(storyboard_path)
        )

        audio_info = MP3(audio_path)
        audio_duration = float(
            audio_info.info.length
        )

        fps = settings.video_fps
        total_frames = max(
            1,
            math.ceil(audio_duration * fps),
        )

        estimated_total = sum(
            scene.estimated_duration_seconds
            for scene in storyboard.scenes
        )

        scale = (
            audio_duration / estimated_total
            if estimated_total > 0
            else 1.0
        )

        scenes = []
        current_frame = 0

        for index, scene in enumerate(
            storyboard.scenes
        ):
            if index == len(storyboard.scenes) - 1:
                duration_frames = (
                    total_frames - current_frame
                )
            else:
                resolved_seconds = (
                    scene.estimated_duration_seconds
                    * scale
                )

                duration_frames = max(
                    1,
                    round(resolved_seconds * fps),
                )

            component = SCENE_COMPONENTS.get(
                scene.scene_type.value
            )

            if not component:
                raise ValueError(
                    "Unsupported scene type: "
                    f"{scene.scene_type.value}"
                )

            render_scene = RenderScene(
                scene_id=scene.scene_id,
                component=component,
                variant=scene.variant,
                start_frame=current_frame,
                duration_frames=duration_frames,
                props={
                    "purpose": scene.purpose,
                    "voiceover": scene.complete_voiceover,
                    "visual_elements": [
                        element.model_dump(mode="json")
                        for element in scene.visual_elements
                    ],
                    "transition_in": scene.transition_in,
                    "transition_out": scene.transition_out,
                    "background_variant": (
                        scene.background_variant
                    ),
                },
            )

            scenes.append(render_scene)
            current_frame += duration_frames

        render_specification = RenderSpecification(
            render_id=f"render_{uuid4().hex[:12]}",
            candidate_name=storyboard.candidate_name,
            video=RenderVideoSettings(
                width=settings.video_width,
                height=settings.video_height,
                fps=fps,
                duration_frames=total_frames,
            ),
            theme=ThemeSettings(
                theme_id=storyboard.branding_theme,
                confidential=storyboard.confidential,
            ),
            audio=AudioTrack(
                source_path=str(audio_path),
                duration_seconds=audio_duration,
            ),
            scenes=scenes,
            assets=[],
            output_path=str(
                run_manager.get_directory("video")
                / "candidate_snapshot.mp4"
            ),
            metadata={
                "storyboard_path": str(
                    storyboard_path
                ),
                "duration_seconds": audio_duration,
            },
        )

        output_path = (
            output_directory
            / "render_spec.json"
        )

        save_json(
            render_specification.model_dump(
                mode="json"
            ),
            output_path,
        )

        save_json(
            {
                "status": "passed",
                "scene_count": len(scenes),
                "duration_frames": total_frames,
                "duration_seconds": audio_duration,
            },
            output_directory
            / "render_validation.json",
        )

        save_json(
            [],
            output_directory
            / "resolved_assets.json",
        )

        run_manager.complete_step(
            STEP_NAME,
            outputs={
                "render_spec": str(output_path),
                "duration_frames": total_frames,
                "scene_count": len(scenes),
            },
        )

        return render_specification

    except Exception as error:
        run_manager.fail_step(
            STEP_NAME,
            f"{type(error).__name__}: {error}",
        )
        raise


def main():
    arguments = build_argument_parser().parse_args()

    try:
        specification = compile_render_spec(
            arguments.run_dir
        )

        print()
        print("STEP 08 COMPLETED")
        print(
            f"Frames: {specification.video.duration_frames}"
        )
        print(
            f"Scenes: {len(specification.scenes)}"
        )
        print()

        return 0

    except Exception as error:
        print()
        print("STEP 08 FAILED")
        print(f"{type(error).__name__}: {error}")
        print()

        return 1


if __name__ == "__main__":
    sys.exit(main())
