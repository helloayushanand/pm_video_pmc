"""LangGraph component generation, validation, repair, and persistence."""

from __future__ import annotations

import json
import re
from pathlib import Path

from langgraph.graph import END, START, StateGraph

from app.agents.component_generation.agent import ComponentGenerationAgent
from app.agents.component_generation.source_validator import (
    validate_generated_source,
)
from app.agents.component_generation.state import DynamicComponentState
from app.schemas.generated_component import (
    ComponentGenerationStatus,
    GeneratedComponentManifest,
    GeneratedComponentOutput,
    SceneGenerationInput,
)
from app.utils.json_utils import save_json


def _event(state, node, status, detail=None):
    events = list(state.get("events", []))
    event = {"node": node, "status": status}
    if detail:
        event["detail"] = detail
    events.append(event)
    return events


def prepare_scene_node(state: DynamicComponentState) -> dict:
    scene_input = SceneGenerationInput.model_validate(state["scene_input"])
    return {
        "scene_id": scene_input.scene_id,
        "fallback_component": scene_input.fallback_component,
        "generation_attempts": int(state.get("generation_attempts", 0)),
        "source_repair_attempts": int(state.get("source_repair_attempts", 0)),
        "max_generation_attempts": int(state.get("max_generation_attempts", 1)),
        "max_source_repair_attempts": int(
            state.get("max_source_repair_attempts", 2)
        ),
        "status": "scene_prepared",
        "events": _event(state, "prepare_scene", "completed"),
    }


def build_component_graph(agent: ComponentGenerationAgent):
    def generate_node(state: DynamicComponentState) -> dict:
        scene_input = SceneGenerationInput.model_validate(state["scene_input"])
        component, metadata = agent.generate(scene_input)
        return {
            "generated_component": component.model_dump(mode="json"),
            "generated_source": component.source_code,
            "generation_attempts": int(state.get("generation_attempts", 0)) + 1,
            "last_call_metadata": metadata,
            "status": ComponentGenerationStatus.GENERATED.value,
            "events": _event(state, "component_generator", "completed"),
        }

    def validate_node(state: DynamicComponentState) -> dict:
        scene_input = SceneGenerationInput.model_validate(state["scene_input"])
        result = validate_generated_source(
            state.get("generated_source") or "", scene_input
        )
        return {
            "source_validation": result.model_dump(mode="json"),
            "source_validation_errors": [
                issue.message for issue in result.issues
            ],
            "status": (
                ComponentGenerationStatus.SOURCE_VALID.value
                if result.valid
                else ComponentGenerationStatus.SOURCE_INVALID.value
            ),
            "events": _event(
                state,
                "validate_source",
                "passed" if result.valid else "failed",
            ),
        }

    def repair_node(state: DynamicComponentState) -> dict:
        scene_input = SceneGenerationInput.model_validate(state["scene_input"])
        current = GeneratedComponentOutput.model_validate(
            state["generated_component"]
        )
        validation = validate_generated_source(
            state.get("generated_source") or "", scene_input
        )
        repaired, metadata = agent.repair(scene_input, current, validation)
        return {
            "generated_component": repaired.model_dump(mode="json"),
            "generated_source": repaired.source_code,
            "source_repair_attempts": int(
                state.get("source_repair_attempts", 0)
            )
            + 1,
            "last_call_metadata": metadata,
            "status": "source_repaired",
            "events": _event(state, "source_repair_agent", "completed"),
        }

    def persist_node(state: DynamicComponentState) -> dict:
        output_dir = Path(state["output_directory"]).resolve()
        source_dir = output_dir / "source"
        manifest_dir = output_dir / "manifests"
        metadata_dir = output_dir / "metadata"
        for directory in (source_dir, manifest_dir, metadata_dir):
            directory.mkdir(parents=True, exist_ok=True)

        scene_input = SceneGenerationInput.model_validate(state["scene_input"])
        component = GeneratedComponentOutput.model_validate(
            state["generated_component"]
        )
        validation = validate_generated_source(
            component.source_code, scene_input
        )
        safe_scene = re.sub(r"[^A-Za-z0-9_-]", "_", scene_input.scene_id)
        source_path = source_dir / f"{safe_scene}_{component.component_name}.tsx"
        source_path.write_text(component.source_code, encoding="utf-8")
        manifest = GeneratedComponentManifest(
            scene_id=component.scene_id,
            component_name=component.component_name,
            source_file=str(source_path),
            status=ComponentGenerationStatus.READY_FOR_COMPILATION,
            used_primitives=component.used_primitives,
            used_artifacts=component.used_artifacts,
            fallback_component=component.fallback_component,
            expected_peak_frame_percentage=(
                component.expected_peak_frame_percentage
            ),
            generation_attempts=int(state.get("generation_attempts", 0)),
            repair_attempts=int(state.get("source_repair_attempts", 0)),
            validation=validation,
        )
        manifest_path = manifest_dir / f"{safe_scene}.json"
        save_json(manifest.model_dump(mode="json"), manifest_path)
        metadata = state.get("last_call_metadata")
        if metadata:
            save_json(metadata, metadata_dir / f"{safe_scene}_last_call.json")
        return {
            "source_file": str(source_path),
            "manifest_file": str(manifest_path),
            "status": ComponentGenerationStatus.READY_FOR_COMPILATION.value,
            "events": _event(state, "persist_component", "completed"),
        }

    def fallback_node(state: DynamicComponentState) -> dict:
        output_dir = Path(state["output_directory"]).resolve()
        manifest_dir = output_dir / "manifests"
        manifest_dir.mkdir(parents=True, exist_ok=True)
        scene_input = SceneGenerationInput.model_validate(state["scene_input"])
        safe_scene = re.sub(r"[^A-Za-z0-9_-]", "_", scene_input.scene_id)
        manifest_path = manifest_dir / f"{safe_scene}.json"
        save_json(
            {
                "scene_id": scene_input.scene_id,
                "component_name": None,
                "source_file": None,
                "status": ComponentGenerationStatus.FALLBACK.value,
                "fallback_component": scene_input.fallback_component,
                "generation_attempts": int(state.get("generation_attempts", 0)),
                "repair_attempts": int(
                    state.get("source_repair_attempts", 0)
                ),
                "validation": state.get("source_validation"),
            },
            manifest_path,
        )
        return {
            "manifest_file": str(manifest_path),
            "status": ComponentGenerationStatus.FALLBACK.value,
            "events": _event(state, "activate_fallback", "completed"),
        }

    def route_after_validation(state: DynamicComponentState) -> str:
        validation = state.get("source_validation") or {}
        if validation.get("valid"):
            return "persist_component"
        if int(state.get("source_repair_attempts", 0)) < int(
            state.get("max_source_repair_attempts", 2)
        ):
            return "repair_source"
        return "activate_fallback"

    graph = StateGraph(DynamicComponentState)
    graph.add_node("prepare_scene", prepare_scene_node)
    graph.add_node("generate_component", generate_node)
    graph.add_node("validate_source", validate_node)
    graph.add_node("repair_source", repair_node)
    graph.add_node("persist_component", persist_node)
    graph.add_node("activate_fallback", fallback_node)
    graph.add_edge(START, "prepare_scene")
    graph.add_edge("prepare_scene", "generate_component")
    graph.add_edge("generate_component", "validate_source")
    graph.add_conditional_edges(
        "validate_source",
        route_after_validation,
        {
            "persist_component": "persist_component",
            "repair_source": "repair_source",
            "activate_fallback": "activate_fallback",
        },
    )
    graph.add_edge("repair_source", "validate_source")
    graph.add_edge("persist_component", END)
    graph.add_edge("activate_fallback", END)
    return graph.compile()


def build_phase_4a_graph():
    """Build the Phase 4A foundation graph for compatibility tests."""

    def phase_4a_ready_node(
        state: DynamicComponentState,
    ) -> dict:
        return {
            "status": (
                "ready_for_component_generator_agent"
            ),
            "events": _event(
                state,
                "phase_4a_ready",
                "completed",
            ),
        }

    graph = StateGraph(
        DynamicComponentState
    )

    graph.add_node(
        "prepare_scene",
        prepare_scene_node,
    )

    graph.add_node(
        "phase_4a_ready",
        phase_4a_ready_node,
    )

    graph.add_edge(
        START,
        "prepare_scene",
    )

    graph.add_edge(
        "prepare_scene",
        "phase_4a_ready",
    )

    graph.add_edge(
        "phase_4a_ready",
        END,
    )

    return graph.compile()
