"""Pipeline Step 05B: Generate the video creative plan."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.config import settings
from app.services.creative_planning_service import (
    CreativePlanningService,
)
from app.utils.json_utils import (
    load_json,
    save_json,
)
from app.utils.logging import setup_logging
from app.utils.run_manager import RunManager


STEP_NAME = "generate_creative_plan"


def build_argument_parser():
    """Create the command-line argument parser."""

    parser = argparse.ArgumentParser(
        description=(
            "Generate creative direction and "
            "scene architecture for a candidate video."
        )
    )

    parser.add_argument(
        "--run-dir",
        required=True,
        help="Existing pipeline run directory.",
    )

    parser.add_argument(
        "--model",
        default=settings.openai_model,
        help=(
            "OpenAI model used for creative planning. "
            f"Default: {settings.openai_model}"
        ),
    )

    return parser


def _ensure_existing_run_supports_step(
    run_directory,
):
    """Add the Phase 2 step to an older run when required."""

    run_path = Path(
        run_directory
    ).expanduser().resolve()

    state_path = (
        run_path
        / "run.json"
    )

    if not state_path.exists():
        raise FileNotFoundError(
            f"Run state not found: {state_path}"
        )

    state = load_json(
        state_path
    )

    steps = state.setdefault(
        "steps",
        {},
    )

    if STEP_NAME not in steps:
        steps[STEP_NAME] = {
            "status": "pending",
            "started_at": None,
            "completed_at": None,
            "error": None,
            "outputs": {},
        }

        save_json(
            state,
            state_path,
        )

    output_directory = (
        run_path
        / "05b_creative_plan"
    )

    output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )


def generate_creative_plan(
    run_directory,
    model=None,
):
    """Generate the complete Phase 2 creative plan."""

    run_path = Path(
        run_directory
    ).expanduser().resolve()

    _ensure_existing_run_supports_step(
        run_path
    )

    run_manager = RunManager(
        run_path
    )

    setup_logging(
        settings.log_level,
        run_manager.get_directory("logs")
        / "pipeline.log",
    )

    video_content_path = (
        run_manager.get_directory(
            "video_content"
        )
        / "video_content.json"
    )

    storyboard_path = (
        run_manager.get_directory(
            "storyboard"
        )
        / "storyboard.json"
    )

    if not video_content_path.exists():
        raise FileNotFoundError(
            "Video content was not found. "
            "Run content selection first."
        )

    if not storyboard_path.exists():
        raise FileNotFoundError(
            "Storyboard was not found. "
            "Run storyboard generation first."
        )

    output_directory = (
        run_path
        / "05b_creative_plan"
    )

    run_manager.start_step(
        STEP_NAME
    )

    try:
        video_content = load_json(
            video_content_path
        )

        storyboard = load_json(
            storyboard_path
        )

        service = CreativePlanningService(
            model=(
                model
                or settings.openai_model
            )
        )

        final_plan = service.generate_plan(
            video_content=video_content,
            storyboard=storyboard,
            output_directory=(
                output_directory
            ),
        )

        final_path = (
            output_directory
            / "creative_plan.json"
        )

        run_manager.complete_step(
            STEP_NAME,
            outputs={
                "creative_plan": str(
                    final_path
                ),
                "creative_plan_preview": str(
                    output_directory
                    / "creative_plan_preview.md"
                ),
                "cohesion_review": str(
                    output_directory
                    / "cohesion_review.json"
                ),
                "scene_count": len(
                    final_plan
                    .draft
                    .scene_briefs
                ),
                "cohesion_approved": (
                    final_plan
                    .cohesion_review
                    .approved
                ),
                "cohesion_score": (
                    final_plan
                    .cohesion_review
                    .overall_cohesion_score
                ),
                "generated_component_count": sum(
                    1
                    for scene in (
                        final_plan
                        .draft
                        .scene_briefs
                    )
                    if (
                        scene.component_strategy.value
                        == "generated_component"
                    )
                ),
            },
        )

        return final_plan

    except Exception as error:
        run_manager.fail_step(
            STEP_NAME,
            f"{type(error).__name__}: {error}",
        )

        raise


def main():
    """Run Phase 2 from the command line."""

    arguments = (
        build_argument_parser()
        .parse_args()
    )

    try:
        plan = generate_creative_plan(
            run_directory=(
                arguments.run_dir
            ),
            model=arguments.model,
        )

        print()
        print("=" * 72)
        print("PHASE 2 CREATIVE PLAN COMPLETED")
        print("=" * 72)
        print(
            "Candidate:        "
            f"{plan.draft.candidate_name}"
        )
        print(
            "Scene briefs:     "
            f"{len(plan.draft.scene_briefs)}"
        )
        print(
            "Cohesion score:   "
            f"{plan.cohesion_review.overall_cohesion_score:.2f}"
        )
        print(
            "Approved:         "
            f"{plan.cohesion_review.approved}"
        )
        print("=" * 72)
        print()

        return 0

    except Exception as error:
        print()
        print("=" * 72)
        print("PHASE 2 CREATIVE PLAN FAILED")
        print("=" * 72)
        print(
            f"Error type: {type(error).__name__}"
        )
        print(f"Details:    {error}")
        print("=" * 72)
        print()

        return 1


if __name__ == "__main__":
    sys.exit(main())
