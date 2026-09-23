"""Pipeline Step 05E: Generate candidate-specific Remotion components."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.config import settings
from app.services.component_generation_service import ComponentGenerationService
from app.utils.json_utils import load_json, save_json
from app.utils.logging import setup_logging
from app.utils.run_manager import RunManager

STEP_NAME = "generate_components"


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


def generate_components(run_directory, model=None, max_scenes=2):
    run_path = Path(run_directory).expanduser().resolve()
    _migrate_existing_run(run_path)
    manager = RunManager(run_path)
    setup_logging(
        settings.log_level,
        manager.get_directory("logs") / "pipeline.log",
    )
    output_dir = run_path / "05d_generated_components"
    output_dir.mkdir(parents=True, exist_ok=True)
    manager.start_step(STEP_NAME)
    try:
        service = ComponentGenerationService(model=model)
        report = service.generate(run_path, output_dir, max_scenes=max_scenes)
        manager.complete_step(
            STEP_NAME,
            outputs={
                "generation_plan": str(output_dir / "generation_plan.json"),
                "generation_report": str(
                    output_dir / "component_generation_report.json"
                ),
                "generated_registry": str(output_dir / "generated_registry.ts"),
                "planned_scene_count": report["planned_scene_count"],
                "ready_for_compilation_count": report[
                    "ready_for_compilation_count"
                ],
                "fallback_count": report["fallback_count"],
            },
        )
        return report
    except Exception as error:
        manager.fail_step(STEP_NAME, f"{type(error).__name__}: {error}")
        raise


def main():
    parser = argparse.ArgumentParser(description="Generate dynamic TSX scenes.")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--model", default=settings.openai_model)
    parser.add_argument("--max-scenes", type=int, default=2)
    args = parser.parse_args()
    try:
        report = generate_components(args.run_dir, args.model, args.max_scenes)
        print("PHASE 4B COMPLETED")
        print(f"Planned scenes: {report['planned_scene_count']}")
        print(
            "Ready for compilation: "
            f"{report['ready_for_compilation_count']}"
        )
        print(f"Fallbacks: {report['fallback_count']}")
        return 0
    except Exception as error:
        print("PHASE 4B FAILED")
        print(f"{type(error).__name__}: {error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
