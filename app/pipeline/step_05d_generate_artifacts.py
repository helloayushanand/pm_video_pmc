"""Pipeline Step 05D: Generate, approve, and publish artifacts."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.config import RENDERER_DIR, settings
from app.services.artifact_generation_service import ArtifactGenerationService
from app.utils.json_utils import load_json, save_json
from app.utils.logging import setup_logging
from app.utils.run_manager import RunManager

STEP_NAME = "generate_artifacts"


def _migrate_existing_run(run_path):
    state_path = run_path / "run.json"
    state = load_json(state_path)
    steps = state.setdefault("steps", {})
    if STEP_NAME not in steps:
        steps[STEP_NAME] = {
            "status": "pending",
            "started_at": None,
            "completed_at": None,
            "error": None,
            "outputs": {},
        }
        save_json(state, state_path)


def generate_artifacts(run_directory, generate_images=False):
    run_path = Path(run_directory).expanduser().resolve()
    _migrate_existing_run(run_path)
    manager = RunManager(run_path)
    setup_logging(
        settings.log_level,
        manager.get_directory("logs") / "pipeline.log",
    )
    manager.start_step(STEP_NAME)
    try:
        service = ArtifactGenerationService()
        result = service.generate_artifacts(
            run_directory=run_path,
            renderer_directory=RENDERER_DIR,
            generate_images=generate_images,
        )
        summary = result["summary"]
        manager.complete_step(
            STEP_NAME,
            outputs={
                "final_manifest": str(
                    run_path / "05c_artifacts" / "artifact_manifest_final.json"
                ),
                "summary": str(
                    run_path
                    / "05c_artifacts"
                    / "artifact_generation_summary.json"
                ),
                **summary,
            },
        )
        return result
    except Exception as error:
        manager.fail_step(STEP_NAME, f"{type(error).__name__}: {error}")
        raise


def build_argument_parser():
    parser = argparse.ArgumentParser(description="Run Phase 3B artifacts.")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--generate-images", action="store_true")
    return parser


def main():
    args = build_argument_parser().parse_args()
    try:
        result = generate_artifacts(args.run_dir, args.generate_images)
        summary = result["summary"]
        print("PHASE 3B COMPLETED")
        print(f"Approved or ready: {summary['approved_count']}")
        print(f"Pending review: {summary['pending_review_count']}")
        print(f"Failed: {summary['failed_count']}")
        return 0
    except Exception as error:
        print("PHASE 3B FAILED")
        print(f"{type(error).__name__}: {error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
