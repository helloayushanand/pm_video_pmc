"""Tests for Phase 7A component publishing helpers."""
from app.services.dynamic_component_publish_service import (
    DynamicComponentPublishService,
)


def test_renderer_import_alias_is_normalised():
    source = 'import {SceneFrame} from "@/dynamic-sdk";'
    result = DynamicComponentPublishService._normalise_renderer_imports(source)
    assert 'from "../../dynamic-sdk"' in result
    assert "@/dynamic-sdk" not in result


def test_canonical_hash_normalises_line_endings():
    first = DynamicComponentPublishService._sha256_text("one\r\ntwo\r\n")
    second = DynamicComponentPublishService._sha256_text("one\ntwo\n")
    assert first == second


def test_publish_gate_blocks_unapproved_quality_and_visual_qa():
    service = DynamicComponentPublishService()
    compiled = {
        "compiled_components": [
            {
                "scene_id": "scene_1",
                "component_name": "StrongScene",
                "source_file": "C:/tmp/scene_1.tsx",
                "source_sha256": "abc123",
                "compile_status": "compiled",
            }
        ]
    }
    preview = {
        "results": [
            {"scene_id": "scene_1", "visual_approved": False}
        ]
    }
    review = [
        {
            "scene_id": "scene_1",
            "design_quality_action": "retry",
            "approval_status": "quality_retry",
        }
    ]

    blocked = service._evaluate_publish_gate(
        compiled["compiled_components"],
        preview.get("results", []),
        review,
    )

    assert blocked[0]["scene_id"] == "scene_1"
    assert "quality_not_approved" in blocked[0]["errors"]
    assert "visual_quality_not_approved" in blocked[0]["errors"]
