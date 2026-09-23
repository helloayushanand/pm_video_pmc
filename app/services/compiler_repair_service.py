"""Bounded compiler-repair workflow for generated components."""
from __future__ import annotations
import json
import shutil
import subprocess
from pathlib import Path
from app.config import RENDERER_DIR
from app.agents.component_generation.compiler_repair_agent import CompilerRepairAgent
from app.agents.component_generation.source_validator import validate_generated_source
from app.schemas.generated_component import GeneratedComponentOutput, SceneGenerationInput
from app.utils.json_utils import load_json, save_json
from app.utils.logging import get_logger
logger = get_logger(__name__)

class CompilerRepairServiceError(Exception):
    """Raised when Phase 5B cannot prepare or repair a component."""

class CompilerRepairService:
    def __init__(self, model=None):
        self.agent = CompilerRepairAgent(model=model)

    def repair(self, run_directory, output_directory, max_attempts=2, timeout_seconds=120):
        run_path = Path(run_directory).expanduser().resolve()
        output_path = Path(output_directory).expanduser().resolve()
        output_path.mkdir(parents=True, exist_ok=True)
        compilation_report_path = run_path / "05e_component_compilation" / "compilation_report.json"
        generation_results_path = run_path / "05d_generated_components" / "generation_results.json"
        generation_plan_path = run_path / "05d_generated_components" / "generation_plan.json"
        if not compilation_report_path.exists():
            raise FileNotFoundError("Phase 5A compilation_report.json is missing.")
        compilation_report = load_json(compilation_report_path)
        if compilation_report.get("compiled"):
            return self._already_compiled(output_path, compilation_report)
        if compilation_report.get("status") != "compiler_error":
            raise CompilerRepairServiceError(
                f"Phase 5B requires compiler_error status, received {compilation_report.get('status')}."
            )
        generation_results = load_json(generation_results_path)
        generation_plan = load_json(generation_plan_path)
        scene_inputs = {
            item["scene_id"]: SceneGenerationInput.model_validate(item)
            for item in generation_plan.get("scenes", [])
        }
        results_by_scene = {item["scene_id"]: item for item in generation_results}
        sdk_contract = self._load_sdk_contract()
        events = []
        final_results = []

        for compiled_item in compilation_report.get("components", []):
            scene_id = compiled_item["scene_id"]
            scene_input = scene_inputs.get(scene_id)
            generated_result = results_by_scene.get(scene_id)
            if scene_input is None or generated_result is None:
                final_results.append({"scene_id": scene_id, "status": "fallback", "reason": "scene_context_missing"})
                continue
            component = GeneratedComponentOutput.model_validate(generated_result["generated_component"])
            compiler_output = self._compiler_text(compilation_report)
            scene_result = self._repair_one(
                run_path, output_path, scene_input, component, compiler_output,
                sdk_contract, max_attempts, timeout_seconds, events,
            )
            final_results.append(scene_result)

        summary = {
            "scene_count": len(final_results),
            "compiled_repair_count": sum(1 for item in final_results if item["status"] == "repaired_compiled_pending_approval"),
            "fallback_count": sum(1 for item in final_results if item["status"] == "fallback"),
            "results": final_results,
            "ready_for_repaired_source_review": any(item["status"] == "repaired_compiled_pending_approval" for item in final_results),
        }
        save_json(events, output_path / "compiler_repair_events.json")
        save_json(summary, output_path / "compiler_repair_report.json")
        (output_path / "compiler_repair_summary.md").write_text(self._markdown(summary), encoding="utf-8")
        return summary

    def _repair_one(self, run_path, output_path, scene_input, component, compiler_output, sdk_contract, max_attempts, timeout_seconds, events):
        current = component
        last_errors = compiler_output
        scene_dir = output_path / "repaired"
        metadata_dir = output_path / "repair_metadata"
        scene_dir.mkdir(parents=True, exist_ok=True)
        metadata_dir.mkdir(parents=True, exist_ok=True)

        for attempt in range(1, max_attempts + 1):
            repaired, metadata = self.agent.repair(scene_input, current, last_errors, sdk_contract)
            validation = validate_generated_source(repaired.source_code, scene_input)
            event = {"scene_id": scene_input.scene_id, "attempt": attempt, "static_validation": validation.model_dump(mode="json"), "metadata": metadata}
            if not validation.valid:
                event["compile_status"] = "not_run_static_validation_failed"
                events.append(event)
                current = repaired
                last_errors = "\n".join(issue.message for issue in validation.issues)
                continue

            candidate_path = scene_dir / f"{scene_input.scene_id}_{repaired.component_name}_repair_{attempt}.tsx"
            candidate_path.write_text(repaired.source_code, encoding="utf-8")
            compile_result = self._compile_candidate(run_path, scene_input, repaired, candidate_path, timeout_seconds)
            event["compile_status"] = compile_result["status"]
            event["compiler_output"] = compile_result["compiler_output"]
            event["candidate_source"] = str(candidate_path)
            events.append(event)
            save_json(metadata, metadata_dir / f"{scene_input.scene_id}_attempt_{attempt}.json")
            if compile_result["compiled"]:
                manifest = {
                    "scene_id": scene_input.scene_id,
                    "component_name": repaired.component_name,
                    "repaired_source_file": str(candidate_path),
                    "status": "repaired_compiled_pending_approval",
                    "repair_attempts": attempt,
                    "fallback_component": scene_input.fallback_component,
                    "static_validation": validation.model_dump(mode="json"),
                    "compiler_output": compile_result["compiler_output"],
                }
                save_json(manifest, output_path / f"{scene_input.scene_id}_repaired_manifest.json")
                return manifest
            current = repaired
            last_errors = compile_result["compiler_output"]

        return {
            "scene_id": scene_input.scene_id,
            "component_name": component.component_name,
            "status": "fallback",
            "repair_attempts": max_attempts,
            "fallback_component": scene_input.fallback_component,
            "reason": "compiler_repair_limit_exhausted",
        }

    def _compile_candidate(self, run_path, scene_input, component, candidate_path, timeout_seconds):
        renderer = Path(RENDERER_DIR).expanduser().resolve()
        workspace = renderer / ".phase5_repair_workspaces" / run_path.name / scene_input.scene_id
        if workspace.exists():
            shutil.rmtree(workspace)
        src = workspace / "src"
        generated = src / "generated"
        generated.mkdir(parents=True, exist_ok=True)
        shutil.copytree(renderer / "src" / "dynamic-sdk", src / "dynamic-sdk")
        destination = generated / candidate_path.name
        shutil.copy2(candidate_path, destination)
        registry = src / "registry.ts"
        registry.write_text(
            'import type React from "react";\n'
            'import type {GeneratedSceneProps} from "@/dynamic-sdk";\n'
            f'import {{{component.component_name}}} from "./generated/{candidate_path.stem}";\n'
            f'export const value: React.FC<GeneratedSceneProps> = {component.component_name};\n',
            encoding="utf-8",
        )
        tsconfig = {
            "compilerOptions": {
                "target": "ES2020", "module": "ESNext", "moduleResolution": "Node",
                "jsx": "react-jsx", "strict": True, "noEmit": True,
                "esModuleInterop": True, "allowSyntheticDefaultImports": True,
                "skipLibCheck": True, "baseUrl": "./src", "paths": {"@/*": ["*"]},
                "types": ["node"], "lib": ["ES2020", "DOM", "DOM.Iterable"]
            },
            "include": ["src/**/*.ts", "src/**/*.tsx"], "exclude": ["node_modules"]
        }
        (workspace / "tsconfig.json").write_text(json.dumps(tsconfig, indent=2), encoding="utf-8")
        (workspace / "package.json").write_text('{"name":"repair-workspace","private":true}', encoding="utf-8")
        command = [str(renderer / "node_modules" / ".bin" / "tsc.cmd"), "--project", str(workspace / "tsconfig.json"), "--pretty", "false"]
        try:
            completed = subprocess.run(command, cwd=str(workspace), capture_output=True, text=True, timeout=timeout_seconds, check=False)
            output = (completed.stdout or "") + "\n" + (completed.stderr or "")
            return {"compiled": completed.returncode == 0, "status": "compiled" if completed.returncode == 0 else "compiler_error", "compiler_output": output, "return_code": completed.returncode}
        except subprocess.TimeoutExpired as error:
            output = (error.stdout or "") + "\n" + (error.stderr or "")
            return {"compiled": False, "status": "timeout", "compiler_output": output, "return_code": None}

    @staticmethod
    def _compiler_text(report):
        return (report.get("compiler_stdout") or "") + "\n" + (report.get("compiler_stderr") or "")

    @staticmethod
    @staticmethod
    def _load_sdk_contract():
        """Return the exact public Dynamic Scene SDK contract."""

        return {
            "GeneratedSceneProps": {
                "context": "SceneContext",
                "content": "Record<string, unknown>",
            },
            "SceneContext": {
                "sceneId": "string",
                "candidateName": "string",
                "durationInFrames": "number",
                "fps": "number",
                "theme": "DynamicTheme",
                "artifacts": "ArtifactManifest",
            },
            "DynamicTheme": {
                "themeId": "string",
                "background": "string",
                "surface": "string",
                "surfaceSecondary": "string",
                "foreground": "string",
                "foregroundMuted": "string",
                "accent": "string",
                "accentSecondary": "string",
                "border": "string",
                "displayFont": "string",
                "bodyFont": "string",
                "confidentialityText": "string",
            },
            "primitives": {
                "SceneFrame": {
                    "required": [
                        "theme",
                    ],
                    "optional": [
                        "background",
                        "showBrand",
                        "showConfidentiality",
                        "sceneLabel",
                        "children",
                    ],
                    "forbidden": [
                        "context",
                        "content",
                        "style",
                    ],
                },
                "SafeArea": {
                    "required": [],
                    "optional": [
                        "horizontal",
                        "vertical",
                        "children",
                    ],
                    "forbidden": [
                        "theme",
                        "style",
                    ],
                },
                "Stack": {
                    "required": [],
                    "optional": [
                        "direction",
                        "gap",
                        "align",
                        "wrap",
                        "style",
                        "children",
                    ],
                    "direction_values": [
                        "row",
                        "column",
                    ],
                    "align_values": [
                        "left",
                        "center",
                        "right",
                    ],
                    "forbidden": [
                        "justify",
                    ],
                },
                "SectionLabel": {
                    "required": [
                        "theme",
                    ],
                    "optional": [
                        "children",
                        "align",
                        "maxWidth",
                        "role",
                        "style",
                    ],
                },
                "DisplayTitle": {
                    "required": [
                        "theme",
                    ],
                    "optional": [
                        "children",
                        "align",
                        "maxWidth",
                        "role",
                        "style",
                    ],
                },
                "BodyCopy": {
                    "required": [
                        "theme",
                    ],
                    "optional": [
                        "children",
                        "align",
                        "maxWidth",
                        "role",
                        "style",
                    ],
                },
                "AutoFitText": {
                    "required": [
                        "text",
                        "theme",
                    ],
                    "optional": [
                        "maximumFontSize",
                        "minimumFontSize",
                        "maximumCharactersAtFullSize",
                        "align",
                        "style",
                    ],
                },
                "MetricValue": {
                    "required": [
                        "value",
                        "theme",
                    ],
                    "optional": [
                        "label",
                        "emphasis",
                        "align",
                    ],
                },
                "MetricCard": {
                    "required": [
                        "value",
                        "theme",
                    ],
                    "optional": [
                        "label",
                        "emphasis",
                        "align",
                        "delayFrames",
                    ],
                },
                "ApprovedAsset": {
                    "required": [
                        "artifactId",
                        "manifest",
                    ],
                    "optional": [
                        "fit",
                        "style",
                    ],
                },
                "FadeReveal": {
                    "required": [],
                    "optional": [
                        "delayFrames",
                        "durationFrames",
                        "children",
                    ],
                    "forbidden": [
                        "direction",
                        "distance",
                        "theme",
                    ],
                },
                "SlideReveal": {
                    "required": [],
                    "optional": [
                        "delayFrames",
                        "durationFrames",
                        "direction",
                        "distance",
                        "children",
                    ],
                },
                "StaggerGroup": {
                    "required": [],
                    "optional": [
                        "delayFrames",
                        "staggerFrames",
                        "direction",
                        "children",
                    ],
                },
                "ConfidentialityLabel": {
                    "required": [
                        "text",
                        "theme",
                    ],
                    "optional": [],
                    "forbidden": [
                        "align",
                        "style",
                    ],
                },
                "OverflowBoundary": {
                    "required": [],
                    "optional": [
                        "debug",
                        "children",
                    ],
                    "forbidden": [
                        "theme",
                        "style",
                    ],
                },
            },
            "react_create_element_rules": [
                (
                    "The second argument contains only the "
                    "component's declared properties."
                ),
                (
                    "Children may be passed as arguments after "
                    "the props object."
                ),
                (
                    "SceneFrame receives theme directly. "
                    "Do not pass context or content to SceneFrame."
                ),
                (
                    "SafeArea does not accept theme or style."
                ),
                (
                    "ConfidentialityLabel requires both text "
                    "and theme."
                ),
                (
                    "Use context.theme.confidentialityText as "
                    "the confidentiality label text."
                ),
                (
                    "Read durationInFrames, fps, theme, and "
                    "artifacts from props.context."
                ),
                (
                    "Use theme.accent instead of "
                    "theme.brand_primary."
                ),
            ],
            "allowed_imports": [
                "react",
                "remotion",
                "@/dynamic-sdk",
            ],
        }
    
    @staticmethod
    def _already_compiled(output_path, compilation_report):
        summary = {"scene_count": len(compilation_report.get("components", [])), "compiled_repair_count": 0, "fallback_count": 0, "results": [], "ready_for_repaired_source_review": False, "message": "Phase 5A already compiled successfully; repair was not invoked."}
        save_json(summary, output_path / "compiler_repair_report.json")
        return summary

    @staticmethod
    def _markdown(summary):
        lines = ["# Compiler Repair Summary", "", f"Scenes: {summary['scene_count']}", f"Compiled repairs pending approval: {summary['compiled_repair_count']}", f"Fallbacks: {summary['fallback_count']}", f"Ready for repaired-source review: {summary['ready_for_repaired_source_review']}", "", "## Results", ""]
        for item in summary["results"]:
            lines.extend([f"### {item['scene_id']}", f"- Status: {item['status']}", f"- Repair attempts: {item.get('repair_attempts', 0)}", f"- Repaired source: {item.get('repaired_source_file')}", f"- Fallback: {item.get('fallback_component')}", ""])
        return "\n".join(lines)
