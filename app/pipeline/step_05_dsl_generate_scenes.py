"""Pipeline Step 05 (DSL): Generate scene specs from dossier via a single LLM call.

Replaces the old steps 5b–5k chain (creative plan → component generation →
compilation → visual QA → repair loop) with one structured-output call that
produces a validated VideoSpec JSON.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.config import settings
from app.services.scene_generation_service import SceneGenerationService
from app.utils.json_utils import load_json, save_json
from app.utils.logging import setup_logging
from app.utils.run_manager import RunManager

STEP_NAME = "dsl_generate_scenes"


def generate_scenes(run_directory: str | Path) -> dict:
    """Generate DSL scenes for a run that already has extracted video_content."""

    run_path = Path(run_directory).expanduser().resolve()
    manager = RunManager(run_path)
    setup_logging(
        settings.log_level,
        manager.get_directory("logs") / "pipeline.log",
    )

    state = load_json(run_path / "run.json")
    steps = state.setdefault("steps", {})
    if STEP_NAME not in steps:
        steps[STEP_NAME] = {
            "status": "pending",
            "started_at": None,
            "completed_at": None,
            "error": None,
            "outputs": {},
        }
        save_json(state, run_path / "run.json")

    manager.start_step(STEP_NAME)

    try:
        video_content_path = run_path / "04_video_content" / "video_content.json"
        if not video_content_path.exists():
            raise FileNotFoundError(f"video_content.json not found at {video_content_path}")
        video_content = load_json(video_content_path)

        dossier = None
        for candidate in (
            run_path / "03_validation" / "dossier_validated.json",
            run_path / "02_extraction" / "dossier_extracted.json",
        ):
            if candidate.exists():
                dossier = load_json(candidate)
                break

        output_dir = run_path / "05_dsl_scenes"
        output_dir.mkdir(parents=True, exist_ok=True)

        service = SceneGenerationService()
        video_spec = service.generate_scenes(
            video_content=video_content,
            dossier=dossier,
            output_directory=output_dir,
        )

        summary = {
            "candidate_name": video_spec.candidate_name,
            "scene_count": len(video_spec.scenes),
            "total_duration": sum(s.duration_seconds for s in video_spec.scenes),
            "scene_ids": [s.scene_id for s in video_spec.scenes],
        }

        manager.complete_step(
            STEP_NAME,
            outputs={
                "video_spec": str(output_dir / "video_spec.json"),
                **summary,
            },
        )

        return {"video_spec": video_spec, "summary": summary}

    except Exception as error:
        manager.fail_step(STEP_NAME, f"{type(error).__name__}: {error}")
        raise


def main():
    parser = argparse.ArgumentParser(description="Generate DSL scene specs.")
    parser.add_argument("--run-dir", required=True)
    args = parser.parse_args()

    try:
        result = generate_scenes(args.run_dir)
        s = result["summary"]
        print("DSL SCENE GENERATION COMPLETED")
        print(f"Candidate: {s['candidate_name']}")
        print(f"Scenes: {s['scene_count']} ({s['total_duration']:.0f}s)")
        return 0
    except Exception as error:
        print("DSL SCENE GENERATION FAILED")
        print(f"{type(error).__name__}: {error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
