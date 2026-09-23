"""Unit tests for Phase 4B package creation helpers."""

from app.services.component_generation_service import ComponentGenerationService


def test_safe_component_name():
    assert (
        ComponentGenerationService._safe_component_name(
            "Commercial Impact Scene"
        )
        == "CommercialImpactScene"
    )


def test_safe_component_name_with_number():
    assert (
        ComponentGenerationService._safe_component_name("3D Scene")
        == "Scene3DScene"
    )
