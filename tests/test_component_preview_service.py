"""Tests for Phase 6 deterministic preview checks."""
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