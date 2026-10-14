"""Repair generated components using structured visual-QA feedback."""

from __future__ import annotations

from pathlib import Path

from app.agents.component_generation.agent import ComponentGenerationAgent
from app.agents.component_generation.source_validator import validate_generated_source
from app.schemas.generated_component import (
    GeneratedComponentOutput,
    SceneGenerationInput,
    SourceValidationIssue,
    SourceValidationResult,
)
from app.utils.json_utils import load_json, save_json
from app.utils.logging import get_logger

logger = get_logger(__name__)


class VisualComponentRepairService:
    """Regenerate only scenes rejected by visual QA."""

    MAX_REPAIR_ATTEMPTS = 1

    def __init__(self, model=None):
        self.agent = ComponentGenerationAgent(model=model)

    def repair(self, run_directory):
        run_path = Path(run_directory).expanduser().resolve()
        preview_path = run_path / "05f_component_previews" / "preview_qa_report.json"
        plan_path = run_path / "05d_generated_components" / "generation_plan.json"
        results_path = run_path / "05d_generated_components" / "generation_results.json"

        for path in (preview_path, plan_path, results_path):
            if not path.exists():
                raise FileNotFoundError(f"Required visual-repair input is missing: {path}")

        preview = load_json(preview_path)
        plan = load_json(plan_path)
        results = load_json(results_path)
        scenes = {item["scene_id"]: item for item in plan.get("scenes", [])}
        result_by_scene = {item["scene_id"]: item for item in results}
        repaired = []
        skipped = []
        failed = []

        for qa in preview.get("results", []):
            if qa.get("visual_approved"):
                skipped.append({"scene_id": qa.get("scene_id"), "reason": "already_approved"})
                continue

            scene_id = qa.get("scene_id")
            if (
                qa.get("status") != "visual_repair_required"
                or not qa.get("visual_qa")
            ):
                skipped.append(
                    {
                        "scene_id": scene_id,
                        "reason": "visual_assessment_unavailable",
                    }
                )
                continue

            scene_payload = scenes.get(scene_id)
            result = result_by_scene.get(scene_id)
            if not scene_payload or not result or not result.get("source_file"):
                skipped.append({"scene_id": scene_id, "reason": "scene_source_missing"})
                continue

            scene_input = SceneGenerationInput.model_validate(scene_payload)
            visual_qa = qa.get("visual_qa") or {}
            issues = visual_qa.get("issues") or []
            required_changes = visual_qa.get("required_changes") or []
            guidance = {
                "visual_repair_guidance": {
                    "summary": visual_qa.get("summary", "Visual QA did not approve this scene."),
                    "issues": issues,
                    "required_changes": required_changes,
                    "instruction": (
                        "Repair the visual defects while preserving approved facts, artifacts, "
                        "scene intent, and the canonical SDK contract. Prioritize readable text, "
                        "safe-area alignment, and sufficient contrast."
                    ),
                }
            }
            architecture = dict(scene_input.scene_architecture)
            architecture.update(guidance)
            repaired_input = scene_input.model_copy(update={"scene_architecture": architecture})
            current_component = GeneratedComponentOutput.model_validate(
                result["generated_component"]
            )
            current_validation = validate_generated_source(
                current_component.source_code,
                repaired_input,
            )
            visual_issues = [
                SourceValidationIssue(
                    code="visual_qa_issue",
                    message=(
                        issue.get("description")
                        or issue.get("recommended_change")
                        or str(issue)
                    ),
                    severity=str(issue.get("severity", "error")),
                )
                for issue in issues
            ]
            visual_validation = SourceValidationResult(
                valid=False,
                issues=[*current_validation.issues, *visual_issues],
                discovered_imports=current_validation.discovered_imports,
                discovered_artifacts=current_validation.discovered_artifacts,
            )
            try:
                component, metadata = self.agent.repair(
                    repaired_input,
                    current_component,
                    visual_validation,
                )
                validation = validate_generated_source(
                    component.source_code,
                    repaired_input,
                )
                if not validation.valid:
                    failed.append(
                        {
                            "scene_id": scene_id,
                            "reason": "repaired_source_validation_failed",
                            "issues": [
                                issue.message for issue in validation.issues
                            ],
                        }
                    )
                    continue
            except Exception as error:
                logger.exception(
                    "Visual repair failed for scene %s; it will use its fallback.",
                    scene_id,
                )
                failed.append(
                    {
                        "scene_id": scene_id,
                        "reason": f"{type(error).__name__}: {error}",
                    }
                )
                continue

            source_path = Path(result["source_file"]).expanduser().resolve()
            source_path.write_text(component.source_code, encoding="utf-8")
            result.update(
                {
                    "generated_source": component.source_code,
                    "generated_component": component.model_dump(mode="json"),
                    "source_validation": validation.model_dump(mode="json"),
                    "visual_repair_attempts": int(result.get("visual_repair_attempts", 0)) + 1,
                    "visual_repair_metadata": metadata,
                    "status": "ready_for_compilation",
                }
            )
            approval_path = (
                run_path / "05d_generated_components" / "approvals" / f"{scene_id}.approval.json"
            )
            if approval_path.exists():
                approval_path.unlink()
            repaired.append({"scene_id": scene_id, "source_file": str(source_path)})

        save_json(results, results_path)
        report = {
            "repaired_count": len(repaired),
            "skipped_count": len(skipped),
            "failed_count": len(failed),
            "repaired": repaired,
            "skipped": skipped,
            "failed": failed,
            "next_step": "recompile_and_verify",
        }
        save_json(report, run_path / "05d_generated_components" / "visual_repair_report.json")
        return report