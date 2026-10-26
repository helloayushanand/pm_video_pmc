"""Tests for Phase 6 deterministic preview checks."""
from pathlib import Path
import sys

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


def test_preview_uses_platform_browser_from_shared_renderer(tmp_path):
    browser_root = (
        tmp_path
        / "node_modules"
        / ".remotion"
        / "chrome-headless-shell"
    )
    platform_directory = (
        "win64"
        if sys.platform == "win32"
        else "mac-arm64"
        if sys.platform == "darwin"
        else "linux64"
    )
    executable_directory = (
        f"chrome-headless-shell-{platform_directory}"
    )
    executable_name = (
        "chrome-headless-shell.exe"
        if sys.platform == "win32"
        else "chrome-headless-shell"
    )
    executable = (
        browser_root
        / platform_directory
        / executable_directory
        / executable_name
    )
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"browser")

    resolved = ComponentPreviewService._browser_executable(tmp_path)

    assert resolved == executable


def test_preview_fails_explicitly_when_shared_browser_is_missing(tmp_path):
    import pytest

    from app.services.component_preview_service import ComponentPreviewError

    with pytest.raises(
        ComponentPreviewError,
        match="Chrome headless-shell executable was not found",
    ):
        ComponentPreviewService._browser_executable(tmp_path)


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


def test_visual_policy_rejects_declared_layout_defects_even_if_low_severity():
    from app.schemas.visual_qa import VisualIssue, VisualQAResult

    result = VisualQAResult(
        approved=True,
        overall_score=0.9,
        hierarchy_score=0.9,
        readability_score=0.9,
        balance_score=0.9,
        brand_consistency_score=0.9,
        artifact_relevance_score=0.9,
        summary="Text overlaps in the timeline.",
        issues=[
            VisualIssue(
                issue_id="overlapping_timeline_labels",
                category="text_overlap",
                severity="low",
                blocking=False,
                description="Timeline labels collide.",
                recommended_change="Reflow the timeline labels.",
            )
        ],
    )

    assessed, approved = ComponentPreviewService._apply_visual_policy(result)

    assert not approved
    assert assessed.blocking_issue_count == 1
    assert not assessed.approved


def test_visual_policy_blocks_contrast_and_composition_defects():
    from app.schemas.visual_qa import VisualIssue, VisualQAResult

    categories = [
        "contrast_failure",
        "underfilled_composition",
        "internal_commentary",
        "repeated_confidentiality",
    ]
    result = VisualQAResult(
        approved=True,
        overall_score=0.95,
        hierarchy_score=0.95,
        readability_score=0.95,
        balance_score=0.95,
        brand_consistency_score=0.95,
        artifact_relevance_score=0.95,
        summary="The scene has several blocking visual defects.",
        issues=[
            VisualIssue(
                issue_id=category,
                category=category,
                severity="low",
                description=f"Defect: {category}",
                recommended_change="Repair the scene and render it again.",
            )
            for category in categories
        ],
    )

    assessed, approved = ComponentPreviewService._apply_visual_policy(result)

    assert not approved
    assert assessed.blocking_issue_count == len(categories)


def test_visual_policy_overrides_rejection_without_blockers_or_low_scores():
    from app.schemas.visual_qa import VisualQAResult

    result = VisualQAResult(
        approved=False,
        overall_score=0.9,
        hierarchy_score=0.9,
        readability_score=0.9,
        balance_score=0.9,
        brand_consistency_score=0.9,
        artifact_relevance_score=0.9,
        summary="The scene is usable with minor polish remaining.",
    )

    assessed, approved = ComponentPreviewService._apply_visual_policy(result)

    assert approved
    assert assessed.approved
    assert assessed.decision_policy_override
    assert assessed.blocking_issue_count == 0


def test_visual_policy_treats_low_severity_layout_breakdown_as_warning():
    from app.schemas.visual_qa import VisualIssue, VisualQAResult

    result = VisualQAResult(
        approved=True,
        overall_score=0.88,
        hierarchy_score=0.9,
        readability_score=0.9,
        balance_score=0.85,
        brand_consistency_score=0.9,
        artifact_relevance_score=0.8,
        summary="Usable layout with a minor style deviation.",
        issues=[
            VisualIssue(
                issue_id="font_preference",
                category="layout_breakdown",
                severity="low",
                blocking=False,
                description="The display font differs from the preference.",
                recommended_change="Use the preferred serif display font.",
            )
        ],
    )

    assessed, approved = ComponentPreviewService._apply_visual_policy(result)

    assert approved
    assert assessed.warning_count == 1
    assert assessed.blocking_issue_count == 0
    assert assessed.approved_with_warnings