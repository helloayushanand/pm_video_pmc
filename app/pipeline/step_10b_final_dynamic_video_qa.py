"""Pipeline Step 10B: Run final technical and cohesion QA."""
from __future__ import annotations
import argparse
import sys
from pathlib import Path
from app.config import settings
from app.services.final_video_qa_service import FinalVideoQAService
from app.utils.json_utils import load_json, save_json
from app.utils.logging import setup_logging
from app.utils.run_manager import RunManager

STEP_NAME = "final_dynamic_video_qa"


def _migrate(run_path):
    state_path = run_path / "run.json"
    state = load_json(state_path)
    steps = state.setdefault("steps", {})
    if STEP_NAME not in steps:
        steps[STEP_NAME] = {"status": "pending", "started_at": None, "completed_at": None, "error": None, "outputs": {}}
        save_json(state, state_path)


def final_dynamic_video_qa(run_directory, model=None, run_cohesion_qa=True, timeout_seconds=300):
    run_path = Path(run_directory).expanduser().resolve()
    _migrate(run_path)
    manager = RunManager(run_path)
    setup_logging(settings.log_level, manager.get_directory("logs") / "pipeline.log")
    output_dir = run_path / "10_dynamic_render" / "final_qa"
    output_dir.mkdir(parents=True, exist_ok=True)
    manager.start_step(STEP_NAME)
    try:
        report = FinalVideoQAService(model=model).review(run_path, output_dir, run_cohesion_qa, timeout_seconds)
        manager.complete_step(STEP_NAME, outputs={
            "qa_report": str(output_dir / "final_video_qa_report.json"),
            "video_sha256": report["video_sha256"],
            "technical_qa_passed": report["technical_qa"]["passed"],
            "ready_for_final_approval": report["ready_for_final_approval"],
        })
        return report
    except Exception as error:
        manager.fail_step(STEP_NAME, f"{type(error).__name__}: {error}")
        raise


def main():
    parser = argparse.ArgumentParser(description="Run final dynamic-video QA.")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--model", default=settings.openai_model)
    parser.add_argument("--skip-cohesion-qa", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=300)
    args = parser.parse_args()
    try:
        report = final_dynamic_video_qa(args.run_dir, args.model, not args.skip_cohesion_qa, args.timeout_seconds)
        print("PHASE 7C FINAL VIDEO QA COMPLETED")
        print(f"Status: {report['status']}")
        print(f"Technical QA passed: {report['technical_qa']['passed']}")
        print(f"Ready for final approval: {report['ready_for_final_approval']}")
        return 0 if report["ready_for_final_approval"] else 2
    except Exception as error:
        print("PHASE 7C FINAL VIDEO QA FAILED")
        print(f"{type(error).__name__}: {error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
