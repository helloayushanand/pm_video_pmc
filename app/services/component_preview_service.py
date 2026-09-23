"""Render representative preview frames for compile-approved components."""
from __future__ import annotations
import base64
import json
import shutil
import subprocess
from pathlib import Path
from PIL import Image
from openai import OpenAI
from app.config import RENDERER_DIR, PROMPTS_DIR, settings
from app.schemas.visual_qa import DeterministicPreviewCheck, VisualQAResult
from app.utils.json_utils import load_json, save_json
from app.utils.logging import get_logger

logger = get_logger(__name__)


class ComponentPreviewError(Exception):
    """Raised when preview preparation or rendering fails."""


class ComponentPreviewService:
    """Build a preview workspace, render frames, and run visual QA."""

    def __init__(self, model=None, api_key=None):
        self.model = model or settings.openai_model
        self.api_key = api_key or settings.openai_api_key
        self.client = OpenAI(api_key=self.api_key) if self.api_key else None

    def run(self, run_directory, output_directory, run_visual_qa=True, timeout_seconds=180):
        run_path = Path(run_directory).expanduser().resolve()
        output_path = Path(output_directory).expanduser().resolve()
        output_path.mkdir(parents=True, exist_ok=True)
        compiled_path = run_path / "05e_component_compilation" / "approved_compiled_components.json"
        if not compiled_path.exists():
            raise FileNotFoundError("approved_compiled_components.json is missing. Complete Phase 5 first.")
        compiled = load_json(compiled_path).get("compiled_components", [])
        if not compiled:
            raise ComponentPreviewError("No compile-approved generated components were found.")

        plan = load_json(run_path / "05d_generated_components" / "generation_plan.json")
        scenes = {item["scene_id"]: item for item in plan.get("scenes", [])}
        artifact_manifest = load_json(run_path / "05c_artifacts" / "artifact_manifest_final.json")
        results = []

        for item in compiled:
            scene_id = item["scene_id"]
            scene_input = scenes.get(scene_id)
            if scene_input is None:
                results.append({"scene_id": scene_id, "status": "failed", "error": "scene_input_missing"})
                continue
            result = self._render_scene(
                run_path, output_path, item, scene_input, artifact_manifest,
                run_visual_qa, timeout_seconds,
            )
            results.append(result)

        summary = {
            "scene_count": len(results),
            "preview_rendered_count": sum(1 for item in results if item.get("preview_rendered")),
            "visual_approved_count": sum(1 for item in results if item.get("visual_approved")),
            "visual_repair_required_count": sum(1 for item in results if item.get("status") == "visual_repair_required"),
            "failed_count": sum(1 for item in results if item.get("status") == "failed"),
            "ready_for_phase_7": bool(results) and all(item.get("visual_approved") for item in results),
            "results": results,
        }
        save_json(summary, output_path / "preview_qa_report.json")
        (output_path / "preview_qa_summary.md").write_text(self._markdown(summary), encoding="utf-8")
        return summary


    @staticmethod
    def _normalise_preview_imports(
        source_text,
    ):
        """Convert compile-time aliases into preview-relative imports."""

        preview_source_text = (
            source_text
            .replace(
                'from "@/dynamic-sdk"',
                'from "../dynamic-sdk"',
            )
            .replace(
                "from '@/dynamic-sdk'",
                "from '../dynamic-sdk'",
            )
        )

        if "@/dynamic-sdk" in preview_source_text:
            raise ComponentPreviewError(
                "Preview source still contains an "
                "unresolved @/dynamic-sdk import."
            )

        return preview_source_text

    def _render_scene(self, run_path, output_path, compiled_item, scene_input, artifact_manifest, run_visual_qa, timeout_seconds):
        renderer = Path(RENDERER_DIR).expanduser().resolve()
        workspace = renderer / ".phase6_preview_workspaces" / run_path.name / compiled_item["scene_id"]
        if workspace.exists():
            shutil.rmtree(workspace)
        src = workspace / "src"
        public = workspace / "public"
        generated = src / "generated"
        generated.mkdir(parents=True, exist_ok=True)
        public.mkdir(parents=True, exist_ok=True)
        shutil.copytree(renderer / "src" / "dynamic-sdk", src / "dynamic-sdk")

        source = Path(
            compiled_item["source_file"]
        ).resolve()

        source_copy = (
            generated
            / source.name
        )

        source_text = source.read_text(
            encoding="utf-8-sig"
        )

        preview_source_text = (
            self._normalise_preview_imports(
                source_text
            )
        )

        source_copy.write_text(
            preview_source_text,
            encoding="utf-8",
        )

        if "@/dynamic-sdk" in preview_source_text:
            raise ComponentPreviewError(
                "Preview source still contains an "
                "unresolved @/dynamic-sdk import."
            )



        self._copy_artifacts(renderer, public, artifact_manifest, run_path.name)

        duration_seconds = float(scene_input.get("duration_hint_seconds", 8.0))
        fps = 30
        duration_frames = max(30, int(round(duration_seconds * fps)))
        peak_percentage = self._peak_percentage(run_path, compiled_item["scene_id"])
        frame_map = {
            "early": max(0, int(duration_frames * 0.10)),
            "middle": max(0, int(duration_frames * 0.50)),
            "peak": max(0, min(duration_frames - 1, int(duration_frames * peak_percentage))),
            "late": max(0, min(duration_frames - 1, int(duration_frames * 0.90))),
        }
        self._write_preview_project(workspace, compiled_item, source_copy, scene_input, artifact_manifest, duration_frames, fps)
        preview_dir = output_path / "previews" / compiled_item["scene_id"]
        preview_dir.mkdir(parents=True, exist_ok=True)

        rendered = []
        errors = []
        remotion = renderer / "node_modules" / ".bin" / "remotion.cmd"
        for label, frame in frame_map.items():
            destination = preview_dir / f"{label}_{frame:04d}.png"
            command = [str(remotion), "still", "src/index.ts", "GeneratedScenePreview", str(destination), "--frame", str(frame), "--log", "error"]
            try:
                completed = subprocess.run(command, cwd=str(workspace), capture_output=True, text=True, timeout=timeout_seconds, check=False)
                if completed.returncode != 0:
                    errors.append({"label": label, "frame": frame, "stdout": completed.stdout, "stderr": completed.stderr})
                else:
                    rendered.append({"label": label, "frame": frame, "path": str(destination)})
            except subprocess.TimeoutExpired as error:
                errors.append({"label": label, "frame": frame, "timeout": True, "stdout": error.stdout or "", "stderr": error.stderr or ""})

        deterministic = self._check_frames(rendered, expected_count=len(frame_map), width=1920, height=1080)
        save_json(deterministic.model_dump(mode="json"), preview_dir / "deterministic_checks.json")
        visual_result = None
        if deterministic.valid and run_visual_qa:
            visual_result = self._run_visual_qa(scene_input, rendered)
            save_json(visual_result.model_dump(mode="json"), preview_dir / "visual_qa.json")

        visual_approved = bool(visual_result and visual_result.approved)
        if not deterministic.valid or errors:
            status = "failed"
        elif run_visual_qa and not visual_approved:
            status = "visual_repair_required"
        else:
            status = "visual_approved"

        return {
            "scene_id": compiled_item["scene_id"],
            "component_name": compiled_item["component_name"],
            "status": status,
            "preview_rendered": deterministic.valid,
            "visual_approved": visual_approved if run_visual_qa else deterministic.valid,
            "frames": rendered,
            "render_errors": errors,
            "deterministic_checks": deterministic.model_dump(mode="json"),
            "visual_qa": visual_result.model_dump(mode="json") if visual_result else None,
            "workspace": str(workspace),
        }

    def _write_preview_project(self, workspace, compiled_item, source_copy, scene_input, artifact_manifest, duration_frames, fps):
        component_name = compiled_item["component_name"]
        root = f"""import React from "react";\nimport {{Composition}} from "remotion";\nimport {{{component_name}}} from "./generated/{source_copy.stem}";\nimport {{defaultDynamicTheme}} from "./dynamic-sdk";\nconst props = {json.dumps(self._preview_props(scene_input, artifact_manifest, duration_frames, fps), ensure_ascii=False)};\nexport const Root: React.FC = () => React.createElement(Composition, {{id: "GeneratedScenePreview", component: {component_name}, durationInFrames: {duration_frames}, fps: {fps}, width: 1920, height: 1080, defaultProps: props}});\n"""
        (workspace / "src" / "Root.tsx").write_text(root, encoding="utf-8")
        (workspace / "src" / "index.ts").write_text('import {registerRoot} from "remotion";\nimport {Root} from "./Root";\nregisterRoot(Root);\n', encoding="utf-8")
        (workspace / "package.json").write_text('{"name":"phase6-preview","private":true}', encoding="utf-8")

    @staticmethod
    def _preview_props(scene_input, artifact_manifest, duration_frames, fps):
        artifacts = {
            "artifacts": [
                {
                    "artifactId": item["artifact_id"],
                    "assetType": item.get("artifact_type", "other"),
                    "rendererPath": item.get("renderer_path") or "",
                    "approved": bool(item.get("approved")),
                    "altText": item.get("alt_text", item["artifact_id"]),
                    "width": item.get("width"),
                    "height": item.get("height"),
                    "sourceReference": item.get("source_description"),
                }
                for item in artifact_manifest.get("artifacts", [])
                if item.get("approved")
            ]
        }
        approved_facts = scene_input.get("approved_facts", [])
        return {
            "context": {
                "sceneId": scene_input["scene_id"],
                "candidateName": "",
                "durationInFrames": duration_frames,
                "fps": fps,
                "theme": {
                    "themeId": "pm_premium_v1", "background": "#F4F1EA", "surface": "#FFFFFF",
                    "surfaceSecondary": "#E9E4DA", "foreground": "#16212B", "foregroundMuted": "#66717C",
                    "accent": "#B59252", "accentSecondary": "#315D78", "border": "rgba(22,33,43,0.12)",
                    "displayFont": "Aptos Display, Inter, Arial, sans-serif", "bodyFont": "Aptos, Inter, Arial, sans-serif",
                    "confidentialityText": "Private and Confidential"
                },
                "artifacts": artifacts,
            },
            "content": {"approvedFacts": approved_facts},
        }

    @staticmethod
    def _copy_artifacts(renderer, public, artifact_manifest, run_id):
        source_root = renderer / "public" / "generated" / "artifacts" / run_id
        destination_root = public / "generated" / "artifacts" / run_id
        if source_root.exists():
            shutil.copytree(source_root, destination_root, dirs_exist_ok=True)

    @staticmethod
    def _peak_percentage(run_path, scene_id):
        manifest_path = run_path / "05d_generated_components" / "manifests" / f"{scene_id}.json"
        if manifest_path.exists():
            value = load_json(manifest_path).get("expected_peak_frame_percentage", 0.65)
            try:
                return max(0.0, min(1.0, float(value)))
            except (TypeError, ValueError):
                pass
        return 0.65

    @staticmethod
    def _check_frames(rendered, expected_count, width, height):
        missing = []
        invalid = []
        dimensions = []
        errors = []
        labels = {item["label"] for item in rendered}
        for label in {"early", "middle", "peak", "late"}:
            if label not in labels:
                missing.append(label)
        for item in rendered:
            path = Path(item["path"])
            if not path.exists() or path.stat().st_size == 0:
                invalid.append(str(path))
                continue
            try:
                with Image.open(path) as image:
                    image.verify()
                with Image.open(path) as image:
                    if image.width != width or image.height != height:
                        dimensions.append(f"{path.name}: {image.width}x{image.height}")
            except Exception as error:
                invalid.append(str(path))
                errors.append(f"{path}: {error}")
        valid = len(rendered) == expected_count and not missing and not invalid and not dimensions and not errors
        return DeterministicPreviewCheck(valid=valid, frame_count=len(rendered), missing_frames=missing, invalid_images=invalid, dimension_mismatches=dimensions, errors=errors)

    def _run_visual_qa(self, scene_input, rendered):
        if self.client is None:
            raise ComponentPreviewError("OPENAI_API_KEY is required for visual QA.")
        prompt_path = Path(PROMPTS_DIR) / "component_visual_qa.txt"
        instructions = prompt_path.read_text(encoding="utf-8-sig").strip()
        content = [{"type": "input_text", "text": json.dumps({"scene_input": scene_input}, ensure_ascii=False)}]
        for frame in rendered:
            encoded = base64.b64encode(Path(frame["path"]).read_bytes()).decode("ascii")
            content.append({"type": "input_text", "text": f"Frame label: {frame['label']}, frame: {frame['frame']}"})
            content.append({"type": "input_image", "image_url": f"data:image/png;base64,{encoded}"})
        response = self.client.responses.parse(
            model=self.model,
            instructions=instructions,
            input=[{"role": "user", "content": content}],
            text_format=VisualQAResult,
        )
        parsed = response.output_parsed
        if parsed is None:
            raise ComponentPreviewError("Visual QA returned no parsed result.")
        if not isinstance(parsed, VisualQAResult):
            parsed = VisualQAResult.model_validate(parsed)
        return parsed

    @staticmethod
    def _markdown(summary):
        lines = ["# Preview and Visual QA Summary", "", f"Scenes: {summary['scene_count']}", f"Preview rendered: {summary['preview_rendered_count']}", f"Visual approved: {summary['visual_approved_count']}", f"Visual repair required: {summary['visual_repair_required_count']}", f"Failed: {summary['failed_count']}", f"Ready for Phase 7: {summary['ready_for_phase_7']}", "", "## Results", ""]
        for item in summary["results"]:
            lines.extend([f"### {item['scene_id']}", f"- Status: {item['status']}", f"- Preview rendered: {item['preview_rendered']}", f"- Visual approved: {item['visual_approved']}", f"- Workspace: `{item['workspace']}`", ""])
        return "\n".join(lines)
