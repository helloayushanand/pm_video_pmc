"""Run the LangGraph dynamic-component generator for eligible scenes."""

from __future__ import annotations

import json
import re
from pathlib import Path

from app.agents.component_generation.agent import ComponentGenerationAgent
from app.agents.component_generation.graph import build_component_graph
from app.schemas.generated_component import (
    ApprovedArtifactReference,
    ComponentGenerationPlan,
    SceneGenerationInput,
)
from app.utils.json_utils import load_json, save_json
from app.utils.logging import get_logger

logger = get_logger(__name__)

ALLOWED_PRIMITIVES = [
    "SceneFrame",
    "SafeArea",
    "Stack",
    "SplitLayout",
    "SectionLabel",
    "DisplayTitle",
    "BodyCopy",
    "AutoFitText",
    "MetricValue",
    "MetricCard",
    "ApprovedAsset",
    "FadeReveal",
    "SlideReveal",
    "StaggerGroup",
    "ConfidentialityLabel",
    "OverflowBoundary",
]


class ComponentGenerationService:
    """Prepare scene packages and invoke the component graph."""

    def __init__(self, model=None):
        self.agent = ComponentGenerationAgent(model=model)
        self.graph = build_component_graph(self.agent)

    def generate(self, run_directory, output_directory, max_scenes=2):
        run_path = Path(run_directory).expanduser().resolve()
        output_path = Path(output_directory).expanduser().resolve()
        output_path.mkdir(parents=True, exist_ok=True)

        creative_plan = load_json(
            run_path / "05b_creative_plan" / "creative_plan.json"
        )
        storyboard = load_json(
            run_path / "05_storyboard" / "storyboard.json"
        )
        artifact_manifest_path = (
            run_path / "05c_artifacts" / "artifact_manifest_final.json"
        )
        if not artifact_manifest_path.exists():
            raise FileNotFoundError(
                "Final artifact manifest missing. Complete Phase 3B first."
            )
        artifact_manifest = load_json(artifact_manifest_path)
        plan = self._build_generation_plan(
            run_path.name,
            creative_plan,
            storyboard,
            artifact_manifest,
            max_scenes,
        )
        save_json(plan.model_dump(mode="json"), output_path / "generation_plan.json")

        results = []
        for scene in plan.scenes:
            logger.info("Generating dynamic component for %s.", scene.scene_id)
            result = self.graph.invoke(
                {
                    "run_id": run_path.name,
                    "scene_id": scene.scene_id,
                    "scene_input": scene.model_dump(mode="json"),
                    "generation_attempts": 0,
                    "source_repair_attempts": 0,
                    "max_generation_attempts": 1,
                    "max_source_repair_attempts": 2,
                    "status": "pending",
                    "fallback_component": scene.fallback_component,
                    "output_directory": str(output_path),
                    "events": [],
                }
            )
            results.append(self._serializable_result(result))

        save_json(results, output_path / "generation_results.json")
        registry_path = self._write_registry(output_path, results)
        report = self._report(plan, results, registry_path)
        save_json(report, output_path / "component_generation_report.json")
        (output_path / "component_generation_summary.md").write_text(
            self._markdown(report), encoding="utf-8"
        )
        return report

    def _build_generation_plan(
        self,
        run_id,
        creative_plan,
        storyboard,
        artifact_manifest,
        max_scenes,
    ):
        draft = creative_plan.get("draft", {})
        direction = draft.get("creative_direction", {})
        storyboard_scenes = {
            scene.get("scene_id"): scene
            for scene in storyboard.get("scenes", [])
        }
        approved_artifacts = []
        for item in artifact_manifest.get("artifacts", []):
            if not item.get("approved"):
                continue
            approved_artifacts.append(
                ApprovedArtifactReference(
                    artifact_id=item["artifact_id"],
                    artifact_type=item.get("artifact_type", "other"),
                    renderer_path=item.get("renderer_path"),
                    local_path=item.get("local_path"),
                    approved=True,
                    alt_text=item.get("alt_text", item["artifact_id"]),
                )
            )

        scene_inputs = []
        for brief in draft.get("scene_briefs", []):
            if brief.get("component_strategy") != "generated_component":
                continue
            if len(scene_inputs) >= max_scenes:
                break
            scene_id = brief["scene_id"]
            story_scene = storyboard_scenes.get(scene_id, {})
            duration = float(story_scene.get("approx_duration_seconds", 8.0))
            component_name = self._safe_component_name(
                brief.get("component_name_suggestion")
                or f"Generated{scene_id.title().replace('_', '')}Scene"
            )
            fact_values = [
                str(value)
                for value in brief.get("approved_facts", [])
                if str(value).strip()
            ]
            scene_artifact_ids = {
                item.get("artifact_id")
                for item in brief.get("artifact_requirements", [])
            }
            scene_artifacts = [
                artifact
                for artifact in approved_artifacts
                if artifact.artifact_id in scene_artifact_ids
            ]
            scene_inputs.append(
                SceneGenerationInput(
                    run_id=run_id,
                    scene_id=scene_id,
                    scene_type=brief.get("scene_type", "generic"),
                    component_name=component_name,
                    fallback_component=brief.get(
                        "fallback_component", "GenericScene"
                    ),
                    duration_hint_seconds=max(duration, 1.0),
                    creative_direction=direction,
                    scene_architecture=brief,
                    approved_facts=fact_values,
                    available_artifacts=scene_artifacts,
                    allowed_primitives=ALLOWED_PRIMITIVES,
                )
            )
        return ComponentGenerationPlan(run_id=run_id, scenes=scene_inputs)

    @staticmethod
    def _safe_component_name(value):
        cleaned = re.sub(r"[^A-Za-z0-9_]", "", str(value))
        if not cleaned:
            return "GeneratedScene"
        if cleaned[0].isdigit():
            cleaned = "Scene" + cleaned
        return cleaned

    @staticmethod
    def _serializable_result(result):
        allowed = {
            "run_id",
            "scene_id",
            "scene_input",
            "generated_component",
            "source_validation",
            "source_validation_errors",
            "generation_attempts",
            "source_repair_attempts",
            "status",
            "fallback_component",
            "source_file",
            "manifest_file",
            "events",
            "last_call_metadata",
        }
        return {key: value for key, value in result.items() if key in allowed}

    @staticmethod
    def _write_registry(output_path, results):
        ready = [
            result
            for result in results
            if result.get("status") == "ready_for_compilation"
            and result.get("source_file")
        ]
        lines = [
            'import type React from "react";',
            'import type {GeneratedSceneProps} from "@/dynamic-sdk";',
            "",
        ]
        entries = []
        for index, result in enumerate(ready):
            component = result["generated_component"]["component_name"]
            source_stem = Path(result["source_file"]).stem
            alias = f"GeneratedComponent{index + 1}"
            lines.append(
                f'import {{{component} as {alias}}} from "./source/{source_stem}";'
            )
            entries.append(
                f'  "{result["scene_id"]}": {alias},'
            )
        lines.extend(
            [
                "",
                "export const generatedSceneRegistry: Record<",
                "  string,",
                "  React.FC<GeneratedSceneProps>",
                "> = {",
                *entries,
                "};",
                "",
            ]
        )
        path = output_path / "generated_registry.ts"
        path.write_text("\n".join(lines), encoding="utf-8")
        return path

    @staticmethod
    def _report(plan, results, registry_path):
        ready = sum(
            1 for result in results if result.get("status") == "ready_for_compilation"
        )
        fallback = sum(
            1 for result in results if result.get("status") == "fallback"
        )
        usage_calls = []
        for result in results:
            metadata = result.get("last_call_metadata")
            if metadata:
                usage_calls.append(metadata)
        return {
            "run_id": plan.run_id,
            "planned_scene_count": len(plan.scenes),
            "ready_for_compilation_count": ready,
            "fallback_count": fallback,
            "registry_path": str(registry_path),
            "results": [
                {
                    "scene_id": result.get("scene_id"),
                    "status": result.get("status"),
                    "source_file": result.get("source_file"),
                    "manifest_file": result.get("manifest_file"),
                    "generation_attempts": result.get("generation_attempts", 0),
                    "repair_attempts": result.get("source_repair_attempts", 0),
                    "validation_errors": result.get(
                        "source_validation_errors", []
                    ),
                }
                for result in results
            ],
            "usage_calls": usage_calls,
        }

    @staticmethod
    def _markdown(report):
        lines = [
            "# Dynamic Component Generation Summary",
            "",
            f"Run ID: {report['run_id']}",
            f"Planned scenes: {report['planned_scene_count']}",
            f"Ready for compilation: {report['ready_for_compilation_count']}",
            f"Fallbacks: {report['fallback_count']}",
            "",
            "## Scene Results",
            "",
        ]
        for result in report["results"]:
            lines.extend(
                [
                    f"### {result['scene_id']}",
                    f"- Status: {result['status']}",
                    f"- Source: {result['source_file']}",
                    f"- Generation attempts: {result['generation_attempts']}",
                    f"- Repair attempts: {result['repair_attempts']}",
                    "",
                ]
            )
        return "\n".join(lines)
