"""Unit tests for Phase 4B package creation helpers."""

from pathlib import Path

import pytest

from app.agents.component_generation.agent import ComponentGenerationAgent
from app.schemas.generated_component import (
    GeneratedComponentOutput,
    SceneGenerationInput,
    SourceValidationResult,
)
from app.services.component_generation_service import ComponentGenerationService


def test_agent_disables_provider_retries(monkeypatch):
    options = {}

    class FakeClient:
        def __init__(self, **kwargs):
            options.update(kwargs)

    monkeypatch.setattr(
        "app.agents.component_generation.agent.OpenAI",
        FakeClient,
    )

    ComponentGenerationAgent(api_key="test-key")

    assert options["max_retries"] == 0


def test_agent_generation_does_not_retry_provider_failure():
    class FakeResponses:
        calls = 0

        def parse(self, **kwargs):
            self.calls += 1
            raise RuntimeError("provider unavailable")

    agent = ComponentGenerationAgent.__new__(ComponentGenerationAgent)
    agent.client = type(
        "FakeClient",
        (),
        {"responses": FakeResponses()},
    )()
    agent.model = "test-model"
    agent.generation_prompt = "test prompt"
    scene = SceneGenerationInput(
        run_id="run-1",
        scene_id="scene_1",
        scene_type="metric",
        component_name="Scene1",
        fallback_component="GenericScene",
        duration_hint_seconds=10,
        creative_direction={"tone": "executive"},
        scene_architecture={},
        approved_facts=["Revenue grew 42%"],
        available_artifacts=[],
        allowed_primitives=["SceneFrame"],
    )

    with pytest.raises(RuntimeError, match="provider unavailable"):
        agent.generate(scene)

    assert agent.client.responses.calls == 1


def test_agent_repair_includes_preview_images_when_supplied():
    class FakeResponses:
        def __init__(self):
            self.call = None

        def parse(self, **kwargs):
            self.call = kwargs
            return type(
                "FakeResponse",
                (),
                {
                    "output_parsed": GeneratedComponentOutput(
                        scene_id="scene_1",
                        component_name="Scene1",
                        source_code="export const Scene1 = () => <div>repaired scene</div>;",
                        used_primitives=["SceneFrame"],
                        generation_rationale="Fixed visible defects.",
                        expected_peak_frame_percentage=0.5,
                        fallback_component="GenericScene",
                    ),
                },
            )()

    responses = FakeResponses()
    agent = ComponentGenerationAgent.__new__(ComponentGenerationAgent)
    agent.client = type(
        "FakeClient",
        (),
        {"responses": responses},
    )()
    agent.model = "test-model"
    agent.repair_prompt = "Repair the component."

    scene = SceneGenerationInput(
        run_id="run-1",
        scene_id="scene_1",
        scene_type="metric",
        component_name="Scene1",
        fallback_component="GenericScene",
        duration_hint_seconds=10,
        creative_direction={"tone": "executive"},
        scene_architecture={},
        approved_facts=["Revenue grew 42%"],
        available_artifacts=[],
        allowed_primitives=["SceneFrame"],
    )
    component = GeneratedComponentOutput(
        scene_id="scene_1",
        component_name="Scene1",
        source_code="export const Scene1 = () => <div>original scene</div>;",
        used_primitives=["SceneFrame"],
        generation_rationale="Original layout.",
        expected_peak_frame_percentage=0.5,
        fallback_component="GenericScene",
    )
    frames = [
        {
            "label": "middle",
            "frame": 81,
            "image_url": "data:image/png;base64,cHJldmlldw==",
        }
    ]

    agent.repair(
        scene,
        component,
        SourceValidationResult(valid=False),
        visual_frames=frames,
    )

    content = responses.call["input"][0]["content"]
    assert content[0]["type"] == "input_text"
    assert content[1]["text"] == "Rendered preview frame: middle, frame 81."
    assert content[2] == {
        "type": "input_image",
        "image_url": "data:image/png;base64,cHJldmlldw==",
    }


def test_sdk_contract_uses_current_renderer_prop_declarations(
    monkeypatch, tmp_path
):
    sdk = tmp_path / "src" / "dynamic-sdk"
    sdk.mkdir(parents=True)
    (sdk / "primitives.tsx").write_text(
        """
type StackProps = {
  gap?: number;
  direction?: "row" | "column";
};
export const Stack: React.FC<StackProps> = () => null;
type SplitLayoutProps = {
  leftRatio?: number;
};
export const SplitLayout: React.FC<SplitLayoutProps> = () => null;
""",
        encoding="utf-8",
    )
    (sdk / "types.ts").write_text(
        "export type ChildrenProps = { children?: React.ReactNode; };",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "app.agents.component_generation.agent.RENDERER_DIR",
        tmp_path,
    )

    contract = ComponentGenerationAgent._read_sdk_public_api()

    assert "- Stack: StackProps" in contract
    assert "gap?: number;" in contract
    assert "leftRatio?: number;" in contract
    assert "space?:" not in contract
    assert "ratio?:" not in contract


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


def test_generate_scene_uses_one_attempt_without_aesthetic_score_gate():
    class FakeGraph:
        def __init__(self):
            self.calls = 0

        def invoke(self, state):
            self.calls += 1
            assert state["max_source_repair_attempts"] == 0
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

    result = service._generate_scene_once(scene, Path("./tmp"), "run-1")

    assert result["generation_attempts"] == 1
    assert "quality_action" not in result
    assert "quality_score" not in result
    assert service.graph.calls == 1


def test_generation_plan_includes_other_scene_composition_context():
    service = ComponentGenerationService.__new__(ComponentGenerationService)
    creative_plan = {
        "draft": {
            "narrative_thesis": "A career defined by measurable growth.",
            "creative_direction": {
                "creative_concept": "Momentum through evidence",
                "visual_motifs": ["arcs", "ascending lines"],
            },
            "scene_briefs": [
                {
                    "scene_id": "scene_1",
                    "component_strategy": "generated_component",
                    "scene_purpose": "Establish the candidate's trajectory",
                    "visual_story": "A line rises through career milestones.",
                    "layout_intent": "A left-to-right timeline",
                    "focal_element": "The final milestone",
                },
                {
                    "scene_id": "scene_2",
                    "component_strategy": "generated_component",
                    "scene_purpose": "Show commercial impact",
                    "visual_story": "A single metric transforms into a result.",
                    "layout_intent": "An oversized central figure",
                    "focal_element": "Revenue growth",
                },
            ],
        }
    }

    plan = service._build_generation_plan(
        run_id="run-1",
        creative_plan=creative_plan,
        storyboard={"scenes": []},
        artifact_manifest={"artifacts": []},
        max_scenes=2,
    )
    scenes = {scene.scene_id: scene for scene in plan.scenes}
    first_architecture = scenes["scene_1"].scene_architecture

    assert first_architecture["video_level_context"]["narrative_thesis"] == (
        "A career defined by measurable growth."
    )
    assert first_architecture["video_level_context"]["visual_motifs"] == [
        "arcs",
        "ascending lines",
    ]
    assert first_architecture["other_scene_designs"] == [
        {
            "scene_id": "scene_2",
            "scene_purpose": "Show commercial impact",
            "visual_story": "A single metric transforms into a result.",
            "layout_intent": "An oversized central figure",
            "focal_element": "Revenue growth",
        }
    ]


def test_generation_failure_records_safe_fallback(tmp_path):
    class FailedGraph:
        def invoke(self, state):
            raise RuntimeError("provider unavailable")

    service = ComponentGenerationService.__new__(ComponentGenerationService)
    service.graph = FailedGraph()
    scene = SceneGenerationInput(
        run_id="run-1",
        scene_id="scene_1",
        scene_type="metric",
        component_name="Scene1",
        fallback_component="GenericScene",
        duration_hint_seconds=10,
        creative_direction={"tone": "executive"},
        scene_architecture={},
        approved_facts=["Revenue grew 42%"],
        available_artifacts=[],
        allowed_primitives=["SceneFrame"],
    )

    result = service._generate_scene_once(scene, tmp_path, "run-1")

    assert result["status"] == "fallback"
    assert result["generation_attempts"] == 1
    assert "provider unavailable" in result["events"][0]["detail"]
    assert Path(result["manifest_file"]).exists()
