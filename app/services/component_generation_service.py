"""Run the component-generation graph for creative-plan generated scenes."""

from __future__ import annotations

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
    """Generate components for scenes explicitly selected by the Creative Director.

    The creative plan is authoritative for generated-scene eligibility.
    Python ranks eligible scenes only when the number of requested generated
    scenes exceeds max_scenes. There is no secondary minimum-score veto.
    """

    def __init__(self, model=None):
        self.agent = ComponentGenerationAgent(model=model)
        self.graph = build_component_graph(self.agent)

    def generate(
        self,
        run_directory,
        output_directory,
        max_scenes=5,
        minimum_dynamic_score=None,
    ):
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
                "Final artifact manifest missing. Complete artifact generation "
                "before generating components."
            )
        artifact_manifest = load_json(artifact_manifest_path)

        plan = self._build_generation_plan(
            run_id=run_path.name,
            creative_plan=creative_plan,
            storyboard=storyboard,
            artifact_manifest=artifact_manifest,
            max_scenes=max_scenes,
        )
        save_json(
            plan.model_dump(mode="json"),
            output_path / "generation_plan.json",
        )

        results = []
        for scene in plan.scenes:
            logger.info(
                "Generating Creative Director-selected component for %s "
                "with ranking score %.3f.",
                scene.scene_id,
                float(
                    scene.scene_architecture.get(
                        "dynamic_value_score",
                        0.0,
                    )
                ),
            )
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
        save_json(
            report,
            output_path / "component_generation_report.json",
        )
        (output_path / "component_generation_summary.md").write_text(
            self._markdown(report),
            encoding="utf-8",
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
        draft = creative_plan.get("draft", creative_plan)
        direction = draft.get("creative_direction", {})
        storyboard_scenes = {
            scene.get("scene_id"): scene
            for scene in storyboard.get("scenes", [])
            if scene.get("scene_id")
        }
        approved_artifacts = self._approved_artifacts(artifact_manifest)

        # The Creative Director is authoritative for eligibility.
        # custom_component_required is accepted as an additional explicit signal.
        eligible_briefs = [
            brief
            for brief in draft.get("scene_briefs", [])
            if (
                brief.get("component_strategy") == "generated_component"
                or bool(brief.get("custom_component_required"))
            )
        ]

        ranked = []
        for original_index, brief in enumerate(eligible_briefs):
            score = self._dynamic_scene_score(brief)
            ranked.append(
                {
                    "brief": brief,
                    "score": score,
                    "original_index": original_index,
                }
            )

        # Score is now ranking-only. It never vetoes a Creative Director decision.
        ranked.sort(
            key=lambda item: (
                -item["score"],
                item["original_index"],
            )
        )
        selected = ranked[: max(0, int(max_scenes))]

        omitted = ranked[max(0, int(max_scenes)) :]
        for item in omitted:
            logger.info(
                "Generated scene %s omitted only because max_scenes=%s was "
                "reached. Ranking score: %.3f.",
                item["brief"].get("scene_id"),
                max_scenes,
                item["score"],
            )

        scene_inputs = []
        for selected_item in selected:
            brief = selected_item["brief"]
            score = selected_item["score"]
            scene_id = brief["scene_id"]
            story_scene = storyboard_scenes.get(scene_id, {})
            duration = self._scene_duration_seconds(story_scene, brief)
            component_name = self._safe_component_name(
                brief.get("component_name_suggestion")
                or f"Generated{scene_id.title().replace('_', '')}Scene"
            )
            approved_facts = self._approved_facts(brief, story_scene)
            requested_artifact_ids = self._artifact_ids_for_brief(brief)
            scene_artifacts = [
                artifact
                for artifact in approved_artifacts
                if artifact.artifact_id in requested_artifact_ids
            ]

            required_artifact_ids = self._required_artifact_ids_for_brief(brief)
            available_artifact_ids = {
                artifact.artifact_id for artifact in scene_artifacts
            }
            missing_required = sorted(
                required_artifact_ids - available_artifact_ids
            )

            architecture = dict(brief)
            architecture["dynamic_value_score"] = score
            architecture["dynamic_selection_reason"] = (
                self._dynamic_selection_reason(brief, score)
            )
            architecture["requested_artifact_ids"] = sorted(
                requested_artifact_ids
            )
            architecture["available_artifact_ids"] = sorted(
                available_artifact_ids
            )
            architecture["missing_required_artifact_ids"] = missing_required

            if missing_required:
                logger.warning(
                    "Scene %s is selected for generation but required artifacts "
                    "are unavailable or unapproved: %s. The component generator "
                    "must use its declared fallback treatment for those artifacts.",
                    scene_id,
                    ", ".join(missing_required),
                )

            scene_inputs.append(
                SceneGenerationInput(
                    run_id=run_id,
                    scene_id=scene_id,
                    scene_type=brief.get("scene_type", "generic"),
                    component_name=component_name,
                    fallback_component=brief.get(
                        "fallback_component",
                        "GenericScene",
                    ),
                    duration_hint_seconds=max(duration, 1.0),
                    creative_direction=direction,
                    scene_architecture=architecture,
                    approved_facts=approved_facts,
                    available_artifacts=scene_artifacts,
                    allowed_primitives=ALLOWED_PRIMITIVES,
                )
            )

        logger.info(
            "Creative plan requested %s generated scene(s); selected %s "
            "within max_scenes=%s.",
            len(eligible_briefs),
            len(scene_inputs),
            max_scenes,
        )

        return ComponentGenerationPlan(
            run_id=run_id,
            scenes=scene_inputs,
        )

    @staticmethod
    def _approved_artifacts(artifact_manifest):
        approved = []
        for item in artifact_manifest.get("artifacts", []):
            if not item.get("approved"):
                continue
            approved.append(
                ApprovedArtifactReference(
                    artifact_id=item["artifact_id"],
                    artifact_type=item.get("artifact_type", "other"),
                    renderer_path=item.get("renderer_path"),
                    local_path=item.get("local_path"),
                    approved=True,
                    alt_text=item.get("alt_text", item["artifact_id"]),
                )
            )
        return approved

    @staticmethod
    def _dynamic_scene_score(scene_brief):
        """Ranking score only; never overrides generated_component eligibility."""
        score = 0.0

        if scene_brief.get("custom_component_required"):
            score += 0.30

        if scene_brief.get("component_strategy") == "generated_component":
            score += 0.20

        facts = scene_brief.get("approved_facts", []) or []
        score += min(len(facts) * 0.05, 0.15)

        artifact_requirements = (
            scene_brief.get("artifact_requirements", []) or []
        )
        if artifact_requirements:
            score += 0.15

        high_value_types = {
            "candidate_intro",
            "executive_summary",
            "career_timeline",
            "career_journey",
            "career_milestone",
            "quantified_highlights",
            "quantified_achievements",
            "leadership_scope",
            "organisation_structure",
            "organization_structure",
            "transformation_story",
            "executive_strengths",
            "strength_summary",
            "commercial_impact",
            "geographic_scope",
        }
        if scene_brief.get("scene_type") in high_value_types:
            score += 0.15

        narrative_priority = scene_brief.get("narrative_priority")
        if isinstance(narrative_priority, (int, float)):
            score += (
                min(max(float(narrative_priority), 0.0), 1.0)
                * 0.05
            )
        elif str(narrative_priority).lower() in {
            "high",
            "critical",
            "hero",
        }:
            score += 0.05

        if scene_brief.get("fallback_component"):
            score += 0.05

        if scene_brief.get("scene_type") in {
            "closing",
            "confidentiality",
            "legal",
            "compensation_availability",
        }:
            score -= 0.30

        return round(min(max(score, 0.0), 1.0), 4)

    @staticmethod
    def _dynamic_selection_reason(brief, score):
        reasons = []
        if brief.get("component_strategy") == "generated_component":
            reasons.append("Creative Director selected generated_component")
        if brief.get("custom_component_required"):
            reasons.append("custom component explicitly required")
        if brief.get("artifact_requirements"):
            reasons.append("scene has planned visual artifacts")
        if brief.get("approved_facts"):
            reasons.append("scene contains candidate-specific approved facts")
        if not reasons:
            reasons.append("scene was explicitly selected for generation")
        return (
            f"Ranking score {score:.2f}; eligibility comes from the Creative "
            "Director: "
            + "; ".join(reasons)
            + "."
        )

    @staticmethod
    def _scene_duration_seconds(story_scene, brief):
        for key in (
            "duration_seconds",
            "approx_duration_seconds",
            "duration_hint_seconds",
        ):
            value = story_scene.get(key)
            if value is None:
                value = brief.get(key)
            if value is None:
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                continue

        start = story_scene.get("start_seconds")
        end = story_scene.get("end_seconds")
        try:
            if start is not None and end is not None:
                return float(end) - float(start)
        except (TypeError, ValueError):
            pass
        return 6.0

    @staticmethod
    def _approved_facts(brief, story_scene):
        values = []
        for source in (
            brief.get("approved_facts", []),
            story_scene.get("approved_facts", []),
        ):
            for value in source or []:
                text = str(value).strip()
                if text and text not in values:
                    values.append(text)
        return values

    @staticmethod
    def _artifact_ids_for_brief(brief):
        artifact_ids = set()
        for value in brief.get("artifact_requirements", []) or []:
            if isinstance(value, str):
                artifact_ids.add(value)
                continue
            if isinstance(value, dict):
                artifact_id = (
                    value.get("artifact_id")
                    or value.get("id")
                    or value.get("artifactId")
                )
                if artifact_id:
                    artifact_ids.add(str(artifact_id))
        return artifact_ids

    @staticmethod
    def _required_artifact_ids_for_brief(brief):
        artifact_ids = set()
        for value in brief.get("artifact_requirements", []) or []:
            if not isinstance(value, dict):
                continue
            if not value.get("required"):
                continue
            artifact_id = (
                value.get("artifact_id")
                or value.get("id")
                or value.get("artifactId")
            )
            if artifact_id:
                artifact_ids.add(str(artifact_id))
        return artifact_ids

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
        return {
            key: value
            for key, value in result.items()
            if key in allowed
        }

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
        for index, result in enumerate(ready, start=1):
            component = result["generated_component"]["component_name"]
            source_stem = Path(result["source_file"]).stem
            alias = f"GeneratedComponent{index}"
            lines.append(
                f'import {{{component} as {alias}}} '
                f'from "./source/{source_stem}";'
            )
            entries.append(f'  "{result["scene_id"]}": {alias},')

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
            1
            for result in results
            if result.get("status") == "ready_for_compilation"
        )
        fallback = sum(
            1
            for result in results
            if result.get("status") == "fallback"
        )
        usage_calls = []
        for result in results:
            metadata = result.get("last_call_metadata")
            if metadata:
                usage_calls.append(metadata)

        return {
            "run_id": plan.run_id,
            "planned_scene_count": len(plan.scenes),
            "selected_scene_ids": [
                scene.scene_id for scene in plan.scenes
            ],
            "selected_scene_scores": {
                scene.scene_id: scene.scene_architecture.get(
                    "dynamic_value_score",
                    0.0,
                )
                for scene in plan.scenes
            },
            "ready_for_compilation_count": ready,
            "fallback_count": fallback,
            "registry_path": str(registry_path),
            "results": [
                {
                    "scene_id": result.get("scene_id"),
                    "status": result.get("status"),
                    "source_file": result.get("source_file"),
                    "manifest_file": result.get("manifest_file"),
                    "generation_attempts": result.get(
                        "generation_attempts",
                        0,
                    ),
                    "repair_attempts": result.get(
                        "source_repair_attempts",
                        0,
                    ),
                    "validation_errors": result.get(
                        "source_validation_errors",
                        [],
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
            f"Selected scenes: {report['planned_scene_count']}",
            (
                "Ready for compilation: "
                f"{report['ready_for_compilation_count']}"
            ),
            f"Fallbacks: {report['fallback_count']}",
            "",
            "## Scene Results",
            "",
        ]
        for result in report["results"]:
            score = report["selected_scene_scores"].get(
                result["scene_id"],
                0.0,
            )
            lines.extend(
                [
                    f"### {result['scene_id']}",
                    f"- Ranking score: {score:.2f}",
                    f"- Status: {result['status']}",
                    f"- Source: {result['source_file']}",
                    (
                        "- Generation attempts: "
                        f"{result['generation_attempts']}"
                    ),
                    (
                        "- Repair attempts: "
                        f"{result['repair_attempts']}"
                    ),
                    "",
                ]
            )
        return "\n".join(lines)