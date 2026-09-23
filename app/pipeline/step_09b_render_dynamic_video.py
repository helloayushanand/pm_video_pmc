"""Pipeline Step 09B: Render the integrated dynamic demo video."""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

from app.config import settings
from app.services.dynamic_video_render_service import DynamicVideoRenderService
from app.utils.json_utils import load_json, save_json
from app.utils.logging import setup_logging
from app.utils.run_manager import RunManager

STEP_NAME = "render_dynamic_video"


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


def render_dynamic_video(run_directory, timeout_seconds=900):
    run_path = Path(run_directory).expanduser().resolve()
    _migrate(run_path)
    manager = RunManager(run_path)
    setup_logging(
        settings.log_level,
        manager.get_directory("logs") / "pipeline.log",
    )
    output_dir = run_path / "10_dynamic_render"
    output_dir.mkdir(parents=True, exist_ok=True)
    manager.start_step(STEP_NAME)
    try:
        summary = DynamicVideoRenderService().render(
            run_path,
            output_dir,
            timeout_seconds,
        )
        manager.complete_step(
            STEP_NAME,
            outputs={
                "dynamic_video": summary["output_video"],
                "render_summary": str(
                    output_dir / "render_summary.json"
                ),
                "scene_resolution_report": str(
                    output_dir / "scene_resolution_report.json"
                ),
                "dynamic_scene_count": summary["dynamic_scene_count"],
                "fallback_count": summary["fallback_count"],
                "technical_checks_passed": summary[
                    "technical_checks"
                ]["passed"],
                "ready_for_phase_7c": summary["ready_for_phase_7c"],
            },
        )
        return summary
    except Exception as error:
        manager.fail_step(
            STEP_NAME,
            f"{type(error).__name__}: {error}",
        )
        raise


def main():
    parser = argparse.ArgumentParser(
        description="Render the integrated dynamic demo video."
    )
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    args = parser.parse_args()
    try:
        summary = render_dynamic_video(
            args.run_dir,
            args.timeout_seconds,
        )
        print("PHASE 7B DYNAMIC RENDER COMPLETED")
        print(f"Status: {summary['status']}")
        print(f"Output: {summary['output_video']}")
        print(
            "Technical checks passed: "
            f"{summary['technical_checks']['passed']}"
        )
        print(f"Ready for Phase 7C: {summary['ready_for_phase_7c']}")
        return 0 if summary["ready_for_phase_7c"] else 2
    except Exception as error:
        print("PHASE 7B DYNAMIC RENDER FAILED")
        print(f"{type(error).__name__}: {error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
