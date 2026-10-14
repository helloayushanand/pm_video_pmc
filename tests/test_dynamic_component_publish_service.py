"""Tests for Phase 7A component publishing helpers."""
from pathlib import Path

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


def test_publish_gate_allows_rendered_component_without_visual_approval():
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
            {
                "scene_id": "scene_1",
                "preview_rendered": True,
                "visual_approved": False,
            }
        ]
    }
    blocked = service._evaluate_publish_gate(
        compiled["compiled_components"],
        preview.get("results", []),
    )

    assert blocked == []


def test_publish_gate_blocks_component_that_fails_runtime_smoke():
    blocked = DynamicComponentPublishService._evaluate_publish_gate(
        [
            {
                "scene_id": "scene_1",
                "component_name": "GeneratedScene",
            }
        ],
        [{"scene_id": "scene_1", "preview_rendered": False}],
    )

    assert blocked == [
        {
            "scene_id": "scene_1",
            "component_name": "GeneratedScene",
            "errors": ["runtime_smoke_not_passed"],
        }
    ]


def test_runtime_registry_imports_default_export(tmp_path):
    publish_root = tmp_path / "generated-current"
    (publish_root / "components").mkdir(parents=True)

    registry = DynamicComponentPublishService._write_registry(
        publish_root,
        [
            {
                "scene_id": "scene_default",
                "component_name": "Scene",
                "export_kind": "default",
                "runtime_source": str(
                    publish_root / "components" / "scene.tsx"
                ),
                "fallback_component": "GenericScene",
            }
        ],
    )

    source = Path(registry).read_text(encoding="utf-8")
    assert 'import GeneratedComponent1 from "./components/scene";' in source
    assert "import {Scene as GeneratedComponent1}" not in source
