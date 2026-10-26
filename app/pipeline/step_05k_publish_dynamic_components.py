"""Pipeline Step 05K: Publish approved generated components."""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

from app.config import settings
from app.services.dynamic_component_publish_service import (
    DynamicComponentPublishService,
)
from app.utils.json_utils import load_json, save_json
from app.utils.logging import setup_logging
from app.utils.run_manager import RunManager

STEP_NAME = "publish_dynamic_components"


def _migrate(run_path):
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


def publish_dynamic_components(run_directory):
    run_path = Path(run_directory).expanduser().resolve()
    _migrate(run_path)
    manager = RunManager(run_path)
    setup_logging(
        settings.log_level,
        manager.get_directory("logs") / "pipeline.log",
    )
    output_dir = run_path / "05g_dynamic_integration"
    output_dir.mkdir(parents=True, exist_ok=True)
    manager.start_step(STEP_NAME)
    try:
        report = DynamicComponentPublishService().publish(
            run_path,
            output_dir,
        )
        manager.complete_step(
            STEP_NAME,
            outputs={
                "publish_report": str(
                    output_dir / "dynamic_publish_report.json"
                ),
                "published_count": report["published_count"],
                "blocked_count": report["blocked_count"],
                "publish_root": report["publish_root"],
                "ready_for_runtime_integration": report[
                    "ready_for_runtime_integration"
                ],
            },
        )
        return report
    except Exception as error:
        manager.fail_step(
            STEP_NAME,
            f"{type(error).__name__}: {error}",
        )
        raise


def main():
    parser = argparse.ArgumentParser(
        description="Publish approved generated components."
    )
    parser.add_argument("--run-dir", required=True)
    args = parser.parse_args()
    try:
        report = publish_dynamic_components(args.run_dir)
        print("PHASE 7A PUBLISHING COMPLETED")
        print(f"Published: {report['published_count']}")
        print(f"Blocked: {report['blocked_count']}")
        print(
            "Ready for runtime integration: "
            f"{report['ready_for_runtime_integration']}"
        )
        return 0
    except Exception as error:
        print("PHASE 7A PUBLISHING FAILED")
        print(f"{type(error).__name__}: {error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
