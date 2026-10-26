"""Tests for generated-component review decisions."""

from app.services.component_review_service import (
    ComponentReviewService,
    create_approval,
)
from app.utils.json_utils import load_json, save_json


def test_pending_without_approval():
    assert (
        ComponentReviewService._evaluate_approval(
            approval=None,
            source_hash="abc",
            validation_passed=True,
            source_exists=True,
        )
        == "pending_review"
    )


def test_stale_approval():
    assert (
        ComponentReviewService._evaluate_approval(
            approval={
                "approved": True,
                "decision": "approved_for_compilation",
                "source_sha256": "old",
            },
            source_hash="new",
            validation_passed=True,
            source_exists=True,
        )
        == "stale_approval"
    )


def test_valid_approval():
    assert (
        ComponentReviewService._evaluate_approval(
            approval={
                "approved": True,
                "decision": "approved_for_compilation",
                "source_sha256": "same",
            },
            source_hash="same",
            validation_passed=True,
            source_exists=True,
        )
        == "approved"
    )


def test_source_bound_approval_uses_technical_validation():
    assert (
        ComponentReviewService._evaluate_approval(
            approval={
                "approved": True,
                "decision": "approved_for_compilation",
                "source_sha256": "same",
            },
            source_hash="same",
            validation_passed=True,
            source_exists=True,
        )
        == "approved"
    )


def test_technically_invalid_source_cannot_be_approved():
    assert (
        ComponentReviewService._evaluate_approval(
            approval={
                "approved": True,
                "decision": "approved_for_compilation",
                "source_sha256": "same",
            },
            source_hash="same",
            validation_passed=False,
            source_exists=True,
        )
        == "validation_failed"
    )


def test_review_auto_approves_only_valid_unrejected_components(tmp_path):
    generation_root = tmp_path / "05d_generated_components"
    source_root = generation_root / "sources"
    source_root.mkdir(parents=True)
    valid_source = (
        'import { GeneratedSceneProps } from "@/dynamic-sdk";\n'
        "export const ValidScene = (props: GeneratedSceneProps) => <div />;\n"
    )
    invalid_source = (
        'import fs from "node:fs";\n'
        'import { GeneratedSceneProps } from "@/dynamic-sdk";\n'
        "export const InvalidScene = (props: GeneratedSceneProps) => <div />;\n"
    )
    rejected_source = (
        'import { GeneratedSceneProps } from "@/dynamic-sdk";\n'
        "export const RejectedScene = (props: GeneratedSceneProps) => <div />;\n"
    )
    sources = {
        "valid": valid_source,
        "invalid": invalid_source,
        "rejected": rejected_source,
    }
    scenes = []
    results = []
    for scene_id, component_name in (
        ("valid", "ValidScene"),
        ("invalid", "InvalidScene"),
        ("rejected", "RejectedScene"),
    ):
        source_file = source_root / f"{scene_id}.tsx"
        source_file.write_text(sources[scene_id], encoding="utf-8")
        scenes.append(
            {
                "run_id": "test-run",
                "scene_id": scene_id,
                "scene_type": "test",
                "component_name": component_name,
                "fallback_component": "TypographyOnly_TitleCard",
                "duration_hint_seconds": 5,
                "creative_direction": {},
                "scene_architecture": {},
                "approved_facts": [],
                "available_artifacts": [],
                "allowed_primitives": ["Text"],
            }
        )
        results.append(
            {
                "scene_id": scene_id,
                "source_file": str(source_file),
                "status": "ready_for_compilation",
                "generated_component": {
                    "component_name": component_name,
                    "used_primitives": ["Text"],
                    "used_artifacts": [],
                },
            }
        )

    save_json({"scenes": scenes}, generation_root / "generation_plan.json")
    save_json(results, generation_root / "generation_results.json")
    create_approval(
        run_directory=tmp_path,
        scene_id="rejected",
        decision="rejected_use_fallback",
        reviewer="Reviewer",
        notes="Keep the fallback for this scene.",
    )

    result = ComponentReviewService().prepare_review(
        tmp_path,
        generation_root,
    )

    packages = {item["scene_id"]: item for item in result["packages"]}
    assert packages["valid"]["approval_status"] == "approved"
    assert packages["invalid"]["approval_status"] == "validation_failed"
    assert packages["rejected"]["approval_status"] == "rejected"
    assert result["summary"]["approved_count"] == 1
    assert result["summary"]["blocked_count"] == 1
    assert result["summary"]["rejected_count"] == 1

    approval = load_json(
        generation_root / "approvals" / "valid.approval.json"
    )
    assert approval["reviewer"] == "Automated source validation"
    assert approval["source_sha256"] == packages["valid"]["source_sha256"]
