from app.agents.component_generation.graph import build_phase_4a_graph
from app.agents.component_generation.source_validator import validate_generated_source
from app.schemas.generated_component import ApprovedArtifactReference, SceneGenerationInput

def scene_input():
    return SceneGenerationInput(run_id="run_test", scene_id="scene_01", scene_type="metrics", component_name="CommercialImpactScene", fallback_component="GenericScene", duration_hint_seconds=8, creative_direction={}, scene_architecture={}, approved_facts=["Approved fact"], available_artifacts=[ApprovedArtifactReference(artifact_id="chart", artifact_type="chart", approved=True, alt_text="Chart")], allowed_primitives=["SceneFrame", "MetricValue"])

def test_rejects_filesystem():
    result = validate_generated_source('import fs from "node:fs"; export const CommercialImpactScene = 1; // GeneratedSceneProps', scene_input())
    assert not result.valid

def test_accepts_bounded_source():
    source = 'import React from "react"; import type {GeneratedSceneProps} from "../dynamic-sdk"; export const CommercialImpactScene: React.FC<GeneratedSceneProps> = () => null;'
    assert validate_generated_source(source, scene_input()).valid

def test_graph_runs():
    result = build_phase_4a_graph().invoke({"run_id": "run_test", "scene_id": "scene_01", "scene_input": scene_input().model_dump(mode="json"), "events": []})
    assert result["status"] == "ready_for_component_generator_agent"
