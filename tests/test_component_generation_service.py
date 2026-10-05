"""Unit tests for Phase 4B package creation helpers."""

from pathlib import Path

from app.schemas.generated_component import SceneGenerationInput
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


def test_generate_scene_retries_once_for_borderline_quality():
    class FakeGraph:
        def __init__(self):
            self.calls = 0

        def invoke(self, state):
            self.calls += 1
            if self.calls == 1:
                return {
                    "generated_source": "<div><div><MetricCard /></div><div><MetricCard /></div></div>",
                    "generated_component": {
                        "scene_id": state["scene_id"],
                        "component_name": "WeakScene",
                        "source_code": "<div><div><MetricCard /></div><div><MetricCard /></div></div>",
                        "used_primitives": ["MetricCard"],
                        "used_artifacts": [],
                        "generation_rationale": "weak default layout",
                        "expected_peak_frame_percentage": 0.5,
                        "fallback_component": "GenericScene",
                    },
                    "status": "generated",
                }
            return {
                "generated_source": "<SceneFrame><SafeArea><Stack><SectionLabel /></Stack></SafeArea></SceneFrame>",
                "generated_component": {
                    "scene_id": state["scene_id"],
                    "component_name": "StrongScene",
                    "source_code": "<SceneFrame><SafeArea><Stack><SectionLabel /></Stack></SafeArea></SceneFrame>",
                    "used_primitives": ["SceneFrame", "SafeArea", "Stack", "SectionLabel"],
                    "used_artifacts": [],
                    "generation_rationale": "strong hierarchical composition",
                    "expected_peak_frame_percentage": 0.6,
                    "fallback_component": "GenericScene",
                },
                "status": "ready_for_compilation",
            }

    service = ComponentGenerationService.__new__(ComponentGenerationService)
    service.graph = FakeGraph()
    service.agent = None
    scene = SceneGenerationInput(
        run_id="run-1",
        scene_id="scene_1",
        scene_type="metric",
        component_name="Scene1",
        fallback_component="GenericScene",
        duration_hint_seconds=10,
        creative_direction={"tone": "executive"},
        scene_architecture={"dynamic_value_score": 0.68},
        approved_facts=["Revenue grew 42%"],
        available_artifacts=[],
        allowed_primitives=["SceneFrame", "SafeArea", "Stack", "SectionLabel"],
    )

    result = service._generate_scene_with_retry(scene, Path("./tmp"), "run-1")

    assert result["generation_attempts"] == 2
    assert service.graph.calls == 2
    assert "retry_guidance" in result["scene_input"]["scene_architecture"]
