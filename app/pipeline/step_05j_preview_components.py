"""Pipeline Step 05J: Render previews and run visual QA."""
from __future__ import annotations
import argparse
import sys
from pathlib import Path
from app.config import settings
from app.services.component_preview_service import ComponentPreviewService
from app.utils.json_utils import load_json, save_json
from app.utils.logging import setup_logging
from app.utils.run_manager import RunManager
STEP_NAME = "preview_components"

def _migrate(run_path):
    state_path = run_path / "run.json"
    state = load_json(state_path)
    steps = state.setdefault("steps", {})
    if STEP_NAME not in steps:
        steps[STEP_NAME] = {"status": "pending", "started_at": None, "completed_at": None, "error": None, "outputs": {}}
        save_json(state, state_path)

def preview_components(run_directory, model=None, run_visual_qa=True, timeout_seconds=180):
    run_path = Path(run_directory).expanduser().resolve()
    _migrate(run_path)
    manager = RunManager(run_path)
    setup_logging(settings.log_level, manager.get_directory("logs") / "pipeline.log")
    output_dir = run_path / "05f_component_previews"
    output_dir.mkdir(parents=True, exist_ok=True)
    manager.start_step(STEP_NAME)
    try:
        summary = ComponentPreviewService(model=model).run(run_path, output_dir, run_visual_qa, timeout_seconds)
        manager.complete_step(STEP_NAME, outputs={"preview_report": str(output_dir / "preview_qa_report.json"), **{key: value for key, value in summary.items() if key != "results"}})
        return summary
    except Exception as error:
        manager.fail_step(STEP_NAME, f"{type(error).__name__}: {error}")
        raise

def main():
    parser = argparse.ArgumentParser(description="Render generated-component previews and run visual QA.")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--model", default=settings.openai_model)
    parser.add_argument("--skip-visual-qa", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=180)
    args = parser.parse_args()
    try:
        summary = preview_components(args.run_dir, args.model, not args.skip_visual_qa, args.timeout_seconds)
        print("PHASE 6 PREVIEW QA COMPLETED")
        print(f"Preview rendered: {summary['preview_rendered_count']}")
        print(f"Visual approved: {summary['visual_approved_count']}")
        print(f"Visual repair required: {summary['visual_repair_required_count']}")
        print(f"Failed: {summary['failed_count']}")
        print(f"Ready for Phase 7: {summary['ready_for_phase_7']}")
        return 0 if summary["failed_count"] == 0 else 2
    except Exception as error:
        print("PHASE 6 PREVIEW QA FAILED")
        print(f"{type(error).__name__}: {error}")
        return 1
if __name__ == "__main__":
    sys.exit(main())
