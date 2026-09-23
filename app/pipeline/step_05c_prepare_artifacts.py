"""Pipeline Step 05C: Prepare visual artifacts."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.config import settings
from app.services.artifact_service import (
    ArtifactService,
)
from app.utils.json_utils import (
    load_json,
    save_json,
)
from app.utils.logging import setup_logging
from app.utils.run_manager import RunManager


STEP_NAME = "prepare_artifacts"


def build_argument_parser():
    """Create the argument parser."""

    parser = argparse.ArgumentParser(
        description=(
            "Prepare the artifact plan, "
            "extracted image candidates, and manifest."
        )
    )

    parser.add_argument(
        "--run-dir",
        required=True,
        help="Existing pipeline run directory.",
    )

    return parser


def _ensure_existing_run_supports_step(
    run_directory,
):
    """Add Phase 3A to an older run when required."""

    run_path = Path(
        run_directory
    ).expanduser().resolve()

    state_path = (
        run_path / "run.json"
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

    (
        run_path
        / "05c_artifacts"
    ).mkdir(
        parents=True,
        exist_ok=True,
    )


def prepare_artifacts(
    run_directory,
):
    """Prepare Phase 3A artifacts."""

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

    output_directory = (
        run_path
        / "05c_artifacts"
    )

    run_manager.start_step(
        STEP_NAME
    )

    try:
        service = ArtifactService()

        result = service.prepare_artifacts(
            run_directory=run_path,
            output_directory=(
                output_directory
            ),
        )

        manifest = result["manifest"]
        validation = result["validation"]

        run_manager.complete_step(
            STEP_NAME,
            outputs={
                "artifact_plan": str(
                    output_directory
                    / "artifact_plan.json"
                ),
                "artifact_manifest": str(
                    output_directory
                    / "artifact_manifest.json"
                ),
                "artifact_validation": str(
                    output_directory
                    / "artifact_validation.json"
                ),
                "artifact_summary": str(
                    output_directory
                    / "artifact_summary.md"
                ),
                "artifact_count": len(
                    manifest.artifacts
                ),
                "approved_count": (
                    manifest
                    .approved_artifact_count
                ),
                "pending_review_count": (
                    manifest
                    .pending_review_count
                ),
                "failed_count": (
                    manifest
                    .failed_artifact_count
                ),
                "valid": validation.valid,
            },
        )

        return result

    except Exception as error:
        run_manager.fail_step(
            STEP_NAME,
            f"{type(error).__name__}: {error}",
        )

        raise


def main():
    """Run Phase 3A from the command line."""

    arguments = (
        build_argument_parser()
        .parse_args()
    )

    try:
        result = prepare_artifacts(
            arguments.run_dir
        )

        manifest = result["manifest"]
        validation = result["validation"]

        print()
        print("=" * 72)
        print("PHASE 3A ARTIFACT PREPARATION COMPLETED")
        print("=" * 72)
        print(
            "Artifacts:       "
            f"{len(manifest.artifacts)}"
        )
        print(
            "Ready:           "
            f"{manifest.approved_artifact_count}"
        )
        print(
            "Pending review:  "
            f"{manifest.pending_review_count}"
        )
        print(
            "Failed:          "
            f"{manifest.failed_artifact_count}"
        )
        print(
            "Manifest valid:  "
            f"{validation.valid}"
        )
        print("=" * 72)
        print()

        return 0

    except Exception as error:
        print()
        print("=" * 72)
        print("PHASE 3A ARTIFACT PREPARATION FAILED")
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
