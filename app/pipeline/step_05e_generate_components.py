"""
Pipeline Step 05E:
Generate candidate-specific Remotion components.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.config import settings
from app.services.component_generation_service import (
    ComponentGenerationService,
)
from app.utils.json_utils import (
    load_json,
    save_json,
)
from app.utils.logging import setup_logging
from app.utils.run_manager import RunManager


STEP_NAME = "generate_components"

DEFAULT_MAX_GENERATED_SCENES = 5


def _migrate_existing_run(
    run_path,
):
    state_path = (
        run_path
        / "run.json"
    )

    state = load_json(
        state_path
    )

    steps = state.setdefault(
        "steps",
        {},
    )

    if STEP_NAME not in steps:
        steps[
            STEP_NAME
        ] = {
            "status":
                "pending",

            "started_at":
                None,

            "completed_at":
                None,

            "error":
                None,

            "outputs":
                {},
        }

        save_json(
            state,
            state_path,
        )


def generate_components(
    run_directory,
    model=None,
    max_scenes=None,
):
    """
    Generate candidate-specific scene components.

    The Creative Director determines which scenes are eligible
    for generated treatment.

    max_scenes acts only as a cost/capacity ceiling.

    ComponentGenerationService performs ranking when more
    eligible generated scenes exist than the configured cap.
    """

    run_path = (
        Path(run_directory)
        .expanduser()
        .resolve()
    )

    _migrate_existing_run(
        run_path
    )

    manager = RunManager(
        run_path
    )

    setup_logging(
        settings.log_level,

        manager.get_directory(
            "logs"
        )
        / "pipeline.log",
    )

    output_dir = (
        run_path
        / "05d_generated_components"
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    resolved_max_scenes = (
        DEFAULT_MAX_GENERATED_SCENES
        if max_scenes is None
        else max(
            1,
            int(max_scenes),
        )
    )

    manager.start_step(
        STEP_NAME
    )

    try:
        service = (
            ComponentGenerationService(
                model=model
            )
        )

        report = service.generate(
            run_directory=run_path,
            output_directory=output_dir,
            max_scenes=resolved_max_scenes,
        )

        manager.complete_step(
            STEP_NAME,
            outputs={
                "generation_plan":
                    str(
                        output_dir
                        / "generation_plan.json"
                    ),

                "generation_report":
                    str(
                        output_dir
                        / (
                            "component_generation_"
                            "report.json"
                        )
                    ),

                "generated_registry":
                    str(
                        output_dir
                        / "generated_registry.ts"
                    ),

                "requested_max_scenes":
                    resolved_max_scenes,

                "planned_scene_count":
                    report[
                        "planned_scene_count"
                    ],

                "ready_for_compilation_count":
                    report[
                        "ready_for_compilation_count"
                    ],

                "fallback_count":
                    report[
                        "fallback_count"
                    ],
            },
        )

        return report

    except Exception as error:
        manager.fail_step(
            STEP_NAME,
            (
                f"{type(error).__name__}: "
                f"{error}"
            ),
        )

        raise


def build_argument_parser():
    parser = argparse.ArgumentParser(
        description=(
            "Generate candidate-specific "
            "Remotion TSX scenes."
        )
    )

    parser.add_argument(
        "--run-dir",
        required=True,
    )

    parser.add_argument(
        "--model",
        default=settings.openai_model,
    )

    parser.add_argument(
        "--max-scenes",
        type=int,
        default=DEFAULT_MAX_GENERATED_SCENES,
        help=(
            "Maximum number of Creative Director-selected "
            "scenes to generate. The value is a capacity cap, "
            "not an eligibility threshold."
        ),
    )

    return parser


def main():
    parser = (
        build_argument_parser()
    )

    args = (
        parser.parse_args()
    )

    try:
        report = generate_components(
            run_directory=args.run_dir,
            model=args.model,
            max_scenes=args.max_scenes,
        )

        print()
        print(
            "PHASE 4B COMPLETED"
        )

        print(
            "Generated-scene cap: "
            f"{args.max_scenes}"
        )

        print(
            "Planned scenes: "
            f"{report['planned_scene_count']}"
        )

        print(
            "Ready for compilation: "
            f"{report['ready_for_compilation_count']}"
        )

        print(
            "Fallbacks: "
            f"{report['fallback_count']}"
        )

        print()

        return 0

    except Exception as error:
        print()
        print(
            "PHASE 4B FAILED"
        )

        print(
            f"{type(error).__name__}: "
            f"{error}"
        )

        print()

        return 1


if __name__ == "__main__":
    sys.exit(
        main()
    )