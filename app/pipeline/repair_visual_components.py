"""Regenerate components rejected by visual QA."""

from __future__ import annotations

import argparse
from pathlib import Path

from app.config import settings
from app.services.visual_component_repair_service import VisualComponentRepairService
from app.utils.json_utils import load_json, save_json
from app.utils.logging import setup_logging
from app.utils.run_manager import RunManager

STEP_NAME = "repair_visual_components"


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


def repair_visual_components(run_directory, model=None):
    run_path = Path(run_directory).expanduser().resolve()
    _migrate(run_path)
    manager = RunManager(run_path)
    setup_logging(settings.log_level, manager.get_directory("logs") / "pipeline.log")
    manager.start_step(STEP_NAME)
    try:
        report = VisualComponentRepairService(model=model).repair(run_path)
        manager.complete_step(
            STEP_NAME,
            outputs={
                "visual_repair_report": str(
                    run_path / "05d_generated_components" / "visual_repair_report.json"
                ),
                **report,
            },
        )
        return report
    except Exception as error:
        manager.fail_step(STEP_NAME, f"{type(error).__name__}: {error}")
        raise


def main():
    parser = argparse.ArgumentParser(description="Repair components using visual-QA feedback.")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--model", default=None)
    args = parser.parse_args()
    report = repair_visual_components(args.run_dir, args.model)
    print(f"Visual repairs generated: {report['repaired_count']}")
    print("Next step: rerun review_components, approve repaired sources, then compile and preview.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())