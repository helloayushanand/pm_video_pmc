"""Pipeline Step 05I: Repair generated-component compiler errors."""
from __future__ import annotations
import argparse
import sys
from pathlib import Path
from app.config import settings
from app.services.compiler_repair_service import CompilerRepairService
from app.utils.json_utils import load_json, save_json
from app.utils.logging import setup_logging
from app.utils.run_manager import RunManager
STEP_NAME = "repair_compiler_errors"

def _migrate(run_path):
    state_path = run_path / "run.json"
    state = load_json(state_path)
    steps = state.setdefault("steps", {})
    if STEP_NAME not in steps:
        steps[STEP_NAME] = {"status": "pending", "started_at": None, "completed_at": None, "error": None, "outputs": {}}
        save_json(state, state_path)

def repair_compiler_errors(run_directory, model=None, max_attempts=2, timeout_seconds=120):
    run_path = Path(run_directory).expanduser().resolve()
    _migrate(run_path)
    manager = RunManager(run_path)
    setup_logging(settings.log_level, manager.get_directory("logs") / "pipeline.log")
    output_dir = run_path / "05e_component_compilation"
    manager.start_step(STEP_NAME)
    try:
        summary = CompilerRepairService(model=model).repair(run_path, output_dir, max_attempts, timeout_seconds)
        manager.complete_step(STEP_NAME, outputs={"repair_report": str(output_dir / "compiler_repair_report.json"), **{key: value for key, value in summary.items() if key != "results"}})
        return summary
    except Exception as error:
        manager.fail_step(STEP_NAME, f"{type(error).__name__}: {error}")
        raise

def main():
    parser = argparse.ArgumentParser(description="Repair generated TypeScript compiler errors.")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--model", default=settings.openai_model)
    parser.add_argument("--max-attempts", type=int, default=2)
    parser.add_argument("--timeout-seconds", type=int, default=120)
    args = parser.parse_args()
    try:
        summary = repair_compiler_errors(args.run_dir, args.model, args.max_attempts, args.timeout_seconds)
        print("PHASE 5B COMPILER REPAIR COMPLETED")
        print(f"Compiled repairs pending approval: {summary['compiled_repair_count']}")
        print(f"Fallbacks: {summary['fallback_count']}")
        print(f"Ready for repaired-source review: {summary['ready_for_repaired_source_review']}")
        return 0
    except Exception as error:
        print("PHASE 5B COMPILER REPAIR FAILED")
        print(f"{type(error).__name__}: {error}")
        return 1
if __name__ == "__main__":
    sys.exit(main())
