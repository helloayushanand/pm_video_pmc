"""Pipeline Step 05H: Compile approved generated components."""
from __future__ import annotations
import argparse
import sys
from pathlib import Path
from app.config import settings
from app.services.component_compilation_service import ComponentCompilationService
from app.utils.json_utils import load_json, save_json
from app.utils.logging import setup_logging
from app.utils.run_manager import RunManager
STEP_NAME = "compile_components"

def _migrate_existing_run(run_path):
    state_path = run_path / "run.json"
    state = load_json(state_path)
    steps = state.setdefault("steps", {})
    if STEP_NAME not in steps:
        steps[STEP_NAME] = {"status": "pending", "started_at": None, "completed_at": None, "error": None, "outputs": {}}
        save_json(state, state_path)

def compile_components(run_directory, timeout_seconds=120):
    run_path = Path(run_directory).expanduser().resolve()
    _migrate_existing_run(run_path)
    manager = RunManager(run_path)
    setup_logging(settings.log_level, manager.get_directory("logs") / "pipeline.log")
    output_dir = run_path / "05e_component_compilation"
    output_dir.mkdir(parents=True, exist_ok=True)
    manager.start_step(STEP_NAME)
    try:
        report = ComponentCompilationService().compile_approved_components(run_path, output_dir, timeout_seconds)
        manager.complete_step(STEP_NAME, outputs={
            "compilation_report": str(output_dir / "compilation_report.json"),
            "compiled_registry": str(output_dir / "compiled_registry.ts") if report["compiled"] else None,
            "compiled": report["compiled"], "status": report["status"],
            "component_count": len(report["components"]), "compiler_error_count": len(report["compiler_errors"]),
        })
        return report
    except Exception as error:
        manager.fail_step(STEP_NAME, f"{type(error).__name__}: {error}")
        raise

def main():
    parser = argparse.ArgumentParser(description="Compile approved generated components.")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=120)
    args = parser.parse_args()
    try:
        report = compile_components(args.run_dir, args.timeout_seconds)
        print("PHASE 5A COMPILATION COMPLETED")
        print(f"Status: {report['status']}")
        print(f"Compiled: {report['compiled']}")
        print(f"Compiler errors: {len(report['compiler_errors'])}")
        return 0 if report["compiled"] else 2
    except Exception as error:
        print("PHASE 5A COMPILATION FAILED")
        print(f"{type(error).__name__}: {error}")
        return 1
if __name__ == "__main__":
    sys.exit(main())
