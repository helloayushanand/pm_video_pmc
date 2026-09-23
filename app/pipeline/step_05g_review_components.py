"""Pipeline Step 05G: Prepare component review packages and approvals."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.config import settings
from app.services.component_review_service import ComponentReviewService
from app.utils.json_utils import load_json, save_json
from app.utils.logging import setup_logging
from app.utils.run_manager import RunManager

STEP_NAME = "review_components"


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


def review_components(run_directory):
    run_path = Path(run_directory).expanduser().resolve()
    _migrate_existing_run(run_path)
    manager = RunManager(run_path)
    setup_logging(
        settings.log_level,
        manager.get_directory("logs") / "pipeline.log",
    )
    output_dir = run_path / "05d_generated_components"
    manager.start_step(STEP_NAME)
    try:
        service = ComponentReviewService()
        result = service.prepare_review(run_path, output_dir)
        summary = result["summary"]
        manager.complete_step(
            STEP_NAME,
            outputs={
                "review_packages": str(output_dir / "review_packages.json"),
                "approved_components": str(
                    output_dir / "approved_components.json"
                ),
                "review_summary": str(
                    output_dir / "component_review_summary.json"
                ),
                **summary,
            },
        )
        return result
    except Exception as error:
        manager.fail_step(STEP_NAME, f"{type(error).__name__}: {error}")
        raise


def main():
    parser = argparse.ArgumentParser(description="Review generated components.")
    parser.add_argument("--run-dir", required=True)
    args = parser.parse_args()
    try:
        result = review_components(args.run_dir)
        summary = result["summary"]
        print("PHASE 4D REVIEW COMPLETED")
        print(f"Approved: {summary['approved_count']}")
        print(f"Pending: {summary['pending_count']}")
        print(f"Rejected: {summary['rejected_count']}")
        print(f"Stale approvals: {summary['stale_approval_count']}")
        print(f"Ready for Phase 5: {summary['ready_for_phase_5']}")
        return 0
    except Exception as error:
        print("PHASE 4D REVIEW FAILED")
        print(f"{type(error).__name__}: {error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
