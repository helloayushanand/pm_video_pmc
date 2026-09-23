"""Local run creation and pipeline state management."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.config import RUNS_DIR
from app.utils.files import ensure_directory
from app.utils.json_utils import load_json, save_json


PIPELINE_STEPS = [
    "prepare_document",
    "extract_dossier",
    "validate_extraction",
    "select_video_content",
    "generate_storyboard",
    "generate_creative_plan",
    "generate_audio",
    "align_audio",
    "compile_render_spec",
    "render_video",
    "run_quality_checks",
    "calculate_costs",
]

RUN_SUBDIRECTORIES = {
    "input": "00_input",
    "document": "01_document",
    "extraction": "02_extraction",
    "validation": "03_validation",
    "video_content": "04_video_content",
    "storyboard": "05_storyboard",
    "creative_plan": "05b_creative_plan",
    "audio": "06_audio",
    "alignment": "07_alignment",
    "render_spec": "08_render_spec",
    "video": "09_video",
    "quality": "10_quality",
    "costs": "11_costs",
    "logs": "logs",
}


def utc_now_iso() -> str:
    """Return the current UTC timestamp in ISO 8601 format."""

    return datetime.now().astimezone().isoformat(timespec="seconds")


def generate_run_id() -> str:
    """Generate a readable and collision-resistant run identifier."""

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = uuid4().hex[:8]

    return f"run_{timestamp}_{suffix}"


def create_run(
    input_filename: str,
    configuration: dict[str, Any] | None = None,
    runs_directory: str | Path = RUNS_DIR,
) -> Path:
    """Create a complete local run directory and initial state file."""

    run_id = generate_run_id()
    run_directory = ensure_directory(Path(runs_directory) / run_id)

    for subdirectory in RUN_SUBDIRECTORIES.values():
        ensure_directory(run_directory / subdirectory)

    now = utc_now_iso()

    run_state = {
        "run_id": run_id,
        "input_file": input_filename,
        "status": "CREATED",
        "current_step": None,
        "created_at": now,
        "updated_at": now,
        "configuration": configuration or {},
        "steps": {
            step: {
                "status": "pending",
                "started_at": None,
                "completed_at": None,
                "error": None,
            }
            for step in PIPELINE_STEPS
        },
    }

    save_json(run_state, run_directory / "run.json")

    return run_directory.resolve()


class RunManager:
    """Read and update the state of one local pipeline run."""

    def __init__(self, run_directory: str | Path) -> None:
        self.run_directory = Path(run_directory).resolve()
        self.state_path = self.run_directory / "run.json"

        if not self.state_path.exists():
            raise FileNotFoundError(
                f"Run state file not found: {self.state_path}"
            )

    @property
    def state(self) -> dict[str, Any]:
        """Return the latest run state."""

        return load_json(self.state_path)

    def get_directory(self, directory_name: str) -> Path:
        """Return one standard output directory for the run."""

        if directory_name not in RUN_SUBDIRECTORIES:
            valid_names = ", ".join(RUN_SUBDIRECTORIES)
            raise KeyError(
                f"Unknown run directory '{directory_name}'. "
                f"Valid names: {valid_names}"
            )

        return self.run_directory / RUN_SUBDIRECTORIES[directory_name]

    def start_step(self, step_name: str) -> None:
        """Mark a pipeline step as running."""

        state = self.state
        self._validate_step_name(step_name, state)

        state["status"] = "RUNNING"
        state["current_step"] = step_name
        state["updated_at"] = utc_now_iso()

        step = state["steps"][step_name]
        step["status"] = "running"
        step["started_at"] = utc_now_iso()
        step["completed_at"] = None
        step["error"] = None

        save_json(state, self.state_path)

    def complete_step(
        self,
        step_name: str,
        outputs: dict[str, Any] | None = None,
    ) -> None:
        """Mark a pipeline step as completed."""

        state = self.state
        self._validate_step_name(step_name, state)

        step = state["steps"][step_name]
        step["status"] = "completed"
        step["completed_at"] = utc_now_iso()
        step["error"] = None

        if outputs is not None:
            step["outputs"] = outputs

        state["status"] = f"{step_name.upper()}_COMPLETED"
        state["current_step"] = step_name
        state["updated_at"] = utc_now_iso()

        save_json(state, self.state_path)

    def fail_step(
        self,
        step_name: str,
        error_message: str,
    ) -> None:
        """Mark a pipeline step as failed."""

        state = self.state
        self._validate_step_name(step_name, state)

        step = state["steps"][step_name]
        step["status"] = "failed"
        step["completed_at"] = utc_now_iso()
        step["error"] = error_message

        state["status"] = f"{step_name.upper()}_FAILED"
        state["current_step"] = step_name
        state["updated_at"] = utc_now_iso()

        save_json(state, self.state_path)

    def update_configuration(
        self,
        updates: dict[str, Any],
    ) -> None:
        """Update run-level configuration values."""

        state = self.state
        state["configuration"].update(updates)
        state["updated_at"] = utc_now_iso()

        save_json(state, self.state_path)

    @staticmethod
    def _validate_step_name(
        step_name: str,
        state: dict[str, Any],
    ) -> None:
        if step_name not in state["steps"]:
            raise KeyError(f"Unknown pipeline step: {step_name}")
