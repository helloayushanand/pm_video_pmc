"""Repair generated components using structured visual-QA feedback."""

from __future__ import annotations

import base64
from pathlib import Path

from app.agents.component_generation.agent import ComponentGenerationAgent
from app.agents.component_generation.source_validator import validate_generated_source
from app.config import settings
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

    CATEGORY_REPAIR_ACTIONS = {
        "contrast_failure": (
            "Inspect the actual rendered backgrounds in every supplied frame. "
            "If essential or supporting text is faint during an entrance, do "
            "not wrap it in FadeReveal or any opacity animation; keep it fully "
            "opaque from its first visible frame and use a foreground color "
            "with strong contrast against the actual background."
        ),
        "text_clipping": (
            "Reflow or resize the affected text container so the complete "
            "essential text is visible in every supplied frame; do not rely "
            "on clipping or a later animation frame to reveal missing text."
        ),
        "text_overlap": (
            "Reposition or reflow the colliding elements so their visible "
            "bounds do not intersect in any supplied frame."
        ),
        "underfilled_composition": (
            "Expand and rebalance the requested focal composition across the "
            "safe area instead of leaving the visual compressed in a small "
            "cluster."
        ),
        "safe_area_violation": (
            "Move essential content inside the safe area with clear margin "
            "from the frame edges."
        ),
    }

    def __init__(self, model=None):
        self.model = model or settings.openai_visual_repair_model
        self.agent = ComponentGenerationAgent(model=self.model)

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

            result = result_by_scene.get(scene_id)
            if not result or not result.get("source_file"):
                skipped.append({"scene_id": scene_id, "reason": "scene_source_missing"})
                continue

            previous_attempts = int(
                result.get("visual_repair_attempts", 0)
            )
            if previous_attempts >= self.MAX_REPAIR_ATTEMPTS:
                skipped.append(
                    {
                        "scene_id": scene_id,
                        "reason": "visual_repair_attempt_limit_reached",
                        "attempts": previous_attempts,
                    }
                )
                continue

            scene_payload = scenes.get(scene_id)
            if not scene_payload:
                skipped.append({"scene_id": scene_id, "reason": "scene_source_missing"})
                continue

            scene_input = SceneGenerationInput.model_validate(scene_payload)
            visual_qa = qa.get("visual_qa") or {}
            issues = visual_qa.get("issues") or []
            required_changes = visual_qa.get("required_changes") or []
            issue_actions = []
            for issue in issues:
                category = str(issue.get("category", "")).strip().lower()
                action = self.CATEGORY_REPAIR_ACTIONS.get(category)
                if action and action not in issue_actions:
                    issue_actions.append(action)
            approved_artifact_ids = sorted(
                artifact.artifact_id
                for artifact in scene_input.available_artifacts
                if artifact.approved
            )
            fallback_strategy = (
                scene_input.scene_architecture.get("fallback_strategy")
                or scene_input.fallback_component
            )
            frames = qa.get("frames") or []
            if not frames:
                failed.append(
                    {
                        "scene_id": scene_id,
                        "reason": "visual_qa_frames_missing",
                    }
                )
                continue
            try:
                visual_frames = []
                for frame in frames:
                    frame_path = Path(frame["path"]).expanduser().resolve()
                    if not frame_path.is_file():
                        raise FileNotFoundError(
                            f"Visual QA frame is missing: {frame_path}"
                        )
                    encoded = base64.b64encode(
                        frame_path.read_bytes()
                    ).decode("ascii")
                    visual_frames.append(
                        {
                            "label": str(frame["label"]),
                            "frame": int(frame["frame"]),
                            "image_url": (
                                "data:image/png;base64,"
                                + encoded
                            ),
                        }
                    )
            except (KeyError, TypeError, ValueError, OSError) as error:
                failed.append(
                    {
                        "scene_id": scene_id,
                        "reason": f"visual_qa_frames_unavailable: {error}",
                    }
                )
                continue

            guidance = {
                "visual_repair_guidance": {
                    "summary": visual_qa.get("summary", "Visual QA did not approve this scene."),
                    "issues": issues,
                    "required_changes": required_changes,
                    "issue_specific_repair_actions": issue_actions,
                    "approved_artifact_ids": approved_artifact_ids,
                    "fallback_strategy": fallback_strategy,
                    "instruction": (
                        "Inspect every attached rendered frame and compare it against the current "
                        "source and QA findings. Repair the visible root cause, not just the "
                        "description: the QA recommendation can be mistaken. Apply every "
                        "issue_specific_repair_action in this scene package, then verify that "
                        "the fix addresses the specific frame and defect cited by QA. Preserve approved "
                        "facts, scene intent, and the SDK contract. If a supplied asset is visibly "
                        "wrong or unusable, do not keep rendering it as if it were correct; use "
                        "the scene's declared fallback strategy. You may use only the exact "
                        "approved artifact IDs listed here; never invent, infer, or copy an "
                        "artifact ID from the brief or QA text. If no approved artifact can serve "
                        "the visual, use native geometry or the declared fallback. Reflow a broken composition "
                        "rather than shrinking text. Fix overlap, clipping, safe-area, hierarchy, "
                        "and contrast issues. Do not introduce facts or use scene IDs/debug labels "
                        "as visible copy."
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
            result["visual_repair_attempts"] = previous_attempts + 1
            try:
                component, metadata = self.agent.repair(
                    repaired_input,
                    current_component,
                    visual_validation,
                    visual_frames=visual_frames,
                )
                if component.source_code == current_component.source_code:
                    failed.append(
                        {
                            "scene_id": scene_id,
                            "reason": "visual_repair_unchanged_source",
                        }
                    )
                    continue
                validation = validate_generated_source(
                    component.source_code,
                    repaired_input,
                )
                used_artifact_ids = set(component.used_artifacts)
                unapproved_used_artifacts = sorted(
                    used_artifact_ids - set(approved_artifact_ids)
                )
                if unapproved_used_artifacts or not validation.valid:
                    validation_issues = [
                        issue.message for issue in validation.issues
                    ]
                    if unapproved_used_artifacts:
                        validation_issues.append(
                            "Unapproved artifacts declared by repaired component: "
                            + ", ".join(unapproved_used_artifacts)
                        )
                    failed.append(
                        {
                            "scene_id": scene_id,
                            "reason": "repaired_source_validation_failed",
                            "issues": validation_issues,
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
            "model": getattr(self, "model", None),
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