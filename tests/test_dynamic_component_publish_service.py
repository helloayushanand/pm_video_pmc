"""Tests for Phase 7A component publishing helpers."""
from app.services.dynamic_component_publish_service import (
    DynamicComponentPublishService,
)


def test_renderer_import_alias_is_normalised():
    source = 'import {SceneFrame} from "@/dynamic-sdk";'
    result = DynamicComponentPublishService._normalise_renderer_imports(source)
    assert 'from "../../../dynamic-sdk"' in result
    assert "@/dynamic-sdk" not in result


def test_canonical_hash_normalises_line_endings():
    first = DynamicComponentPublishService._sha256_text("one\r\ntwo\r\n")
    second = DynamicComponentPublishService._sha256_text("one\ntwo\n")
    assert first == second
