"""Tests for Phase 6 deterministic preview checks."""
from pathlib import Path

from PIL import Image
from app.services.component_preview_service import ComponentPreviewService

def test_valid_preview_frames(tmp_path):
    rendered = []
    for index, label in enumerate(["early", "middle", "peak", "late"]):
        path = tmp_path / f"{label}.png"
        Image.new("RGB", (1920, 1080), "white").save(path)
        rendered.append({"label": label, "frame": index, "path": str(path)})
    result = ComponentPreviewService._check_frames(rendered, 4, 1920, 1080)
    assert result.valid

def test_missing_preview_frame(tmp_path):
    path = tmp_path / "early.png"
    Image.new("RGB", (1920, 1080), "white").save(path)
    result = ComponentPreviewService._check_frames([{"label": "early", "frame": 1, "path": str(path)}], 4, 1920, 1080)
    assert not result.valid
    assert "middle" in result.missing_frames
    assert "peak" in result.missing_frames
    assert "late" in result.missing_frames


def test_preview_requires_four_temporal_samples(tmp_path):
    rendered = []
    for index, label in enumerate(["early", "middle", "peak", "late"]):
        path = tmp_path / f"{label}.png"
        Image.new("RGB", (1920, 1080), "white").save(path)
        rendered.append({"label": label, "frame": index, "path": str(path)})

    result = ComponentPreviewService._check_frames(
        rendered,
        expected_count=4,
        width=1920,
        height=1080,
    )

    assert result.valid
    assert result.frame_count == 4


def test_preview_import_alias_is_normalised():
    source = (
        'import {SceneFrame} '
        'from "@/dynamic-sdk";'
    )

    result = (
        ComponentPreviewService
        ._normalise_preview_imports(
            source
        )
    )

    assert (
        'from "../dynamic-sdk"'
        in result
    )

    assert "@/dynamic-sdk" not in result

def test_single_quote_preview_alias_is_normalised():
    source = (
        "import {SceneFrame} "
        "from '@/dynamic-sdk';"
    )

    result = (
        ComponentPreviewService
        ._normalise_preview_imports(
            source
        )
    )

    assert (
        "from '../dynamic-sdk'"
        in result
    )

    assert "@/dynamic-sdk" not in result


def test_preview_project_imports_default_component_export(tmp_path):
    service = ComponentPreviewService.__new__(ComponentPreviewService)
    service._preview_props = lambda *args: {}
    workspace = tmp_path / "preview"
    (workspace / "src").mkdir(parents=True)
    source_copy = workspace / "src" / "generated" / "scene.tsx"

    service._write_preview_project(
        workspace,
        {
            "component_name": "Scene",
            "export_kind": "default",
        },
        source_copy,
        None,
        None,
        10,
        30,
    )

    root_source = (
        workspace / "src" / "Root.tsx"
    ).read_text(encoding="utf-8")
    assert 'import GeneratedPreviewComponent from "./generated/scene";' in root_source
    assert "component: GeneratedPreviewComponent" in root_source


def test_visual_policy_rejects_missing_central_visual():
    from app.schemas.visual_qa import VisualIssue, VisualQAResult

    result = VisualQAResult(
        approved=True,
        overall_score=0.9,
        hierarchy_score=0.9,
        readability_score=0.9,
        balance_score=0.9,
        brand_consistency_score=0.9,
        artifact_relevance_score=0.9,
        summary="The requested timeline is missing.",
        issues=[
            VisualIssue(
                issue_id="missing_timeline",
                category="missing_central_visual",
                severity="high",
                blocking=False,
                description="No timeline is visible.",
                recommended_change="Render the timeline milestones.",
            )
        ],
    )

    assessed, approved = ComponentPreviewService._apply_visual_policy(result)

    assert not approved
    assert assessed.blocking_issue_count == 1
    assert not assessed.approved