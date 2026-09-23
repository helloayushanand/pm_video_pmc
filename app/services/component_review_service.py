"""Review and approval service for generated Remotion components."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from pathlib import Path

from app.agents.component_generation.source_validator import (
    validate_generated_source,
)
from app.schemas.generated_component import SceneGenerationInput
from app.utils.json_utils import load_json, save_json
from app.utils.logging import get_logger

logger = get_logger(__name__)


class ComponentReviewError(Exception):
    """Raised when generated-component review preparation fails."""


class ComponentReviewService:
    """Create review packages and enforce source-bound approvals."""

    def prepare_review(self, run_directory, output_directory):
        run_path = Path(run_directory).expanduser().resolve()
        output_path = Path(output_directory).expanduser().resolve()
        generation_root = run_path / "05d_generated_components"
        plan_path = generation_root / "generation_plan.json"
        results_path = generation_root / "generation_results.json"

        if not plan_path.exists() or not results_path.exists():
            raise FileNotFoundError(
                "Phase 4B outputs are missing. Run generate_components first."
            )

        plan = load_json(plan_path)
        results = load_json(results_path)
        review_dir = output_path / "review"
        approvals_dir = output_path / "approvals"
        review_dir.mkdir(parents=True, exist_ok=True)
        approvals_dir.mkdir(parents=True, exist_ok=True)

        scene_inputs = {
            scene["scene_id"]: SceneGenerationInput.model_validate(scene)
            for scene in plan.get("scenes", [])
        }
        packages = []

        for result in results:
            scene_id = result.get("scene_id")
            if not scene_id or scene_id not in scene_inputs:
                continue

            package = self._build_review_package(
                result=result,
                scene_input=scene_inputs[scene_id],
                output_directory=review_dir,
                approvals_directory=approvals_dir,
            )
            packages.append(package)

        approved_components = self._build_approved_components(packages)
        summary = self._build_summary(packages, approved_components)

        save_json(packages, output_path / "review_packages.json")
        save_json(
            approved_components,
            output_path / "approved_components.json",
        )
        save_json(summary, output_path / "component_review_summary.json")
        (output_path / "component_review_summary.md").write_text(
            self._build_markdown(summary, packages),
            encoding="utf-8",
        )

        logger.info(
            "Component review prepared. Total: %s, approved: %s, "
            "pending: %s, rejected: %s, stale: %s.",
            summary["component_count"],
            summary["approved_count"],
            summary["pending_count"],
            summary["rejected_count"],
            summary["stale_approval_count"],
        )

        return {
            "packages": packages,
            "approved_components": approved_components,
            "summary": summary,
        }

    def _build_review_package(
        self,
        result,
        scene_input,
        output_directory,
        approvals_directory,
    ):
        source_file_value = result.get("source_file")
        source_file = Path(source_file_value).resolve() if source_file_value else None
        source_exists = bool(source_file and source_file.exists())
        source_text = (
            source_file.read_text(encoding="utf-8-sig")
            if source_exists
            else ""
        )
        source_hash = (
            hashlib.sha256(
                source_text
                .replace("\r\n", "\n")
                .replace("\r", "\n")
                .encode("utf-8")
            ).hexdigest()
            if source_exists
            else None
        )
        validation = validate_generated_source(source_text, scene_input)
        imports = validation.discovered_imports
        component = result.get("generated_component") or {}
        status = result.get("status", "unknown")
        safe_scene = self._safe_scene_id(scene_input.scene_id)
        approval_path = approvals_directory / f"{safe_scene}.approval.json"
        approval = load_json(approval_path) if approval_path.exists() else None
        approval_status = self._evaluate_approval(
            approval=approval,
            source_hash=source_hash,
            validation_passed=validation.valid,
            source_exists=source_exists,
        )

        review_package = {
            "scene_id": scene_input.scene_id,
            "scene_type": scene_input.scene_type,
            "component_name": component.get("component_name"),
            "generation_status": status,
            "source_file": str(source_file) if source_file else None,
            "source_exists": source_exists,
            "source_sha256": source_hash,
            "source_line_count": len(source_text.splitlines()),
            "source_character_count": len(source_text),
            "imports": imports,
            "used_primitives": component.get("used_primitives", []),
            "used_artifacts": component.get("used_artifacts", []),
            "approved_facts": scene_input.approved_facts,
            "fallback_component": scene_input.fallback_component,
            "generation_attempts": result.get("generation_attempts", 0),
            "repair_attempts": result.get("source_repair_attempts", 0),
            "source_validation": validation.model_dump(mode="json"),
            "approval_file": str(approval_path),
            "approval_status": approval_status,
            "approval": approval,
            "eligible_for_approval": (
                source_exists
                and validation.valid
                and status == "ready_for_compilation"
            ),
            "review_checklist": [
                "Imports are limited to react, remotion, and @/dynamic-sdk.",
                "No filesystem, network, environment, shell, or dynamic import access.",
                "Only approved facts appear in source or comments.",
                "Only approved artifacts are referenced.",
                "The visual relationship between facts is not misleading.",
                "SafeArea, OverflowBoundary, and confidentiality treatment are retained.",
                "The source complexity is proportionate to the scene purpose.",
                "The fallback component is suitable if compilation later fails.",
            ],
        }

        save_json(
            review_package,
            output_directory / f"{safe_scene}_review.json",
        )
        return review_package

    @staticmethod
    def _evaluate_approval(
        approval,
        source_hash,
        validation_passed,
        source_exists,
    ):
        if not source_exists:
            return "source_missing"
        if not validation_passed:
            return "validation_failed"
        if approval is None:
            return "pending_review"
        if approval.get("source_sha256") != source_hash:
            return "stale_approval"
        decision = approval.get("decision")
        if decision == "approved_for_compilation" and approval.get("approved"):
            return "approved"
        if decision == "rejected_use_fallback" or not approval.get("approved"):
            return "rejected"
        return "pending_review"

    @staticmethod
    def _build_approved_components(packages):
        approved = []
        for package in packages:
            if package["approval_status"] != "approved":
                continue
            approved.append(
                {
                    "scene_id": package["scene_id"],
                    "component_name": package["component_name"],
                    "source_file": package["source_file"],
                    "source_sha256": package["source_sha256"],
                    "fallback_component": package["fallback_component"],
                    "approval_file": package["approval_file"],
                    "approved_for_compilation": True,
                }
            )
        return {
            "schema_version": "1.0",
            "approved_components": approved,
            "approved_count": len(approved),
        }

    @staticmethod
    def _build_summary(packages, approved_components):
        approved_count = sum(
            1 for item in packages if item["approval_status"] == "approved"
        )
        pending_count = sum(
            1 for item in packages if item["approval_status"] == "pending_review"
        )
        rejected_count = sum(
            1 for item in packages if item["approval_status"] == "rejected"
        )
        stale_count = sum(
            1 for item in packages if item["approval_status"] == "stale_approval"
        )
        blocked_count = sum(
            1
            for item in packages
            if item["approval_status"] in {"source_missing", "validation_failed"}
        )
        return {
            "component_count": len(packages),
            "approved_count": approved_count,
            "pending_count": pending_count,
            "rejected_count": rejected_count,
            "stale_approval_count": stale_count,
            "blocked_count": blocked_count,
            "ready_for_phase_5": (
                approved_count == len(packages)
                and len(packages) > 0
                and blocked_count == 0
                and stale_count == 0
            ),
            "approved_components_file_count": approved_components[
                "approved_count"
            ],
        }

    @staticmethod
    def _build_markdown(summary, packages):
        lines = [
            "# Generated Component Review Summary",
            "",
            f"Components: {summary['component_count']}",
            f"Approved: {summary['approved_count']}",
            f"Pending: {summary['pending_count']}",
            f"Rejected: {summary['rejected_count']}",
            f"Stale approvals: {summary['stale_approval_count']}",
            f"Blocked: {summary['blocked_count']}",
            f"Ready for Phase 5: {summary['ready_for_phase_5']}",
            "",
            "## Components",
            "",
        ]
        for package in packages:
            lines.extend(
                [
                    f"### {package['scene_id']}",
                    f"- Component: {package['component_name']}",
                    f"- Status: {package['approval_status']}",
                    f"- Source: `{package['source_file']}`",
                    f"- SHA-256: `{package['source_sha256']}`",
                    f"- Source validation: {package['source_validation']['valid']}",
                    f"- Imports: {', '.join(package['imports'])}",
                    f"- Used primitives: {', '.join(package['used_primitives'])}",
                    f"- Used artifacts: {', '.join(package['used_artifacts'])}",
                    f"- Fallback: {package['fallback_component']}",
                    "",
                ]
            )
        return "\n".join(lines)

        @staticmethod
        def _sha256_text(value):
            """Calculate a platform-independent source hash."""

            canonical_text = value.replace(
                "\r\n",
                "\n",
            ).replace(
                "\r",
                "\n",
            )

            return hashlib.sha256(
                canonical_text.encode("utf-8")
            ).hexdigest()
    @staticmethod
    def _safe_scene_id(value):
        return re.sub(r"[^A-Za-z0-9_-]", "_", str(value))


def create_approval(
    run_directory,
    scene_id,
    decision,
    reviewer,
    notes,
):
    """Create a source-hash-bound approval or rejection record."""

    run_path = Path(run_directory).expanduser().resolve()
    review_root = run_path / "05d_generated_components"
    source_results_path = review_root / "generation_results.json"
    plan_path = review_root / "generation_plan.json"

    if not source_results_path.exists() or not plan_path.exists():
        raise FileNotFoundError("Phase 4B outputs are missing.")

    results = load_json(source_results_path)
    matching = [item for item in results if item.get("scene_id") == scene_id]
    if not matching:
        raise ComponentReviewError(f"Scene not found: {scene_id}")

    source_file_value = matching[0].get("source_file")
    if not source_file_value:
        raise ComponentReviewError(
            f"Scene has no generated source and cannot be approved: {scene_id}"
        )

    source_file = Path(source_file_value).resolve()
    if not source_file.exists():
        raise FileNotFoundError(f"Generated source does not exist: {source_file}")

    source_text = source_file.read_text(encoding="utf-8-sig")
    canonical_text = source_text.replace(
        "\r\n",
        "\n",
    ).replace(
        "\r",
        "\n",
    )

    source_hash = hashlib.sha256(
        canonical_text.encode("utf-8")
    ).hexdigest()
    safe_scene = re.sub(r"[^A-Za-z0-9_-]", "_", scene_id)
    approvals_dir = review_root / "approvals"
    approvals_dir.mkdir(parents=True, exist_ok=True)
    approval_path = approvals_dir / f"{safe_scene}.approval.json"

    approved = decision == "approved_for_compilation"
    payload = {
        "scene_id": scene_id,
        "approved": approved,
        "decision": decision,
        "reviewer": reviewer,
        "review_notes": notes,
        "source_file": str(source_file),
        "source_sha256": source_hash,
        "reviewed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    save_json(payload, approval_path)
    return approval_path

