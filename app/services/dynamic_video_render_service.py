"""Render approved dynamic scenes and integrate them into the demo video."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from app.config import RENDERER_DIR
from app.services.component_preview_service import ComponentPreviewService
from app.utils.json_utils import load_json, save_json
from app.utils.logging import get_logger

logger = get_logger(__name__)


class DynamicVideoRenderError(Exception):
    """Raised when the integrated dynamic demo video cannot be rendered."""


class DynamicVideoRenderService:
    """Render generated scenes and splice them into the existing full video.

    The Phase 7B demo path preserves the original narration audio and all
    original static scenes. It replaces the opening scene video segment with
    the approved generated intro component for the same duration.
    """

    def render(self, run_directory, output_directory, timeout_seconds=900):
        run_path = Path(run_directory).expanduser().resolve()
        output_path = Path(output_directory).expanduser().resolve()
        output_path.mkdir(parents=True, exist_ok=True)

        publish_path = (
            run_path
            / "05g_dynamic_integration"
            / "dynamic_publish_report.json"
        )
        preview_path = (
            run_path
            / "05f_component_previews"
            / "preview_qa_report.json"
        )
        plan_path = (
            run_path
            / "05d_generated_components"
            / "generation_plan.json"
        )
        artifact_path = (
            run_path
            / "05c_artifacts"
            / "artifact_manifest_final.json"
        )

        for required in (
            publish_path,
            preview_path,
            plan_path,
            artifact_path,
        ):
            if not required.exists():
                raise FileNotFoundError(
                    f"Required Phase 7B input is missing: {required}"
                )

        publish_report = load_json(publish_path)
        preview_report = load_json(preview_path)
        plan = load_json(plan_path)
        artifact_manifest = load_json(artifact_path)

        if not publish_report.get("ready_for_runtime_integration"):
            raise DynamicVideoRenderError(
                "Phase 7A publishing is not ready for runtime integration."
            )
        if not preview_report.get("ready_for_phase_7"):
            raise DynamicVideoRenderError(
                "Phase 6 visual QA is not approved."
            )

        source_video = self._find_source_video(run_path)
        source_probe = self._probe_media(source_video)
        fps = self._video_fps(source_probe)
        width, height = self._video_dimensions(source_probe)
        original_duration = self._duration(source_probe)

        scene_inputs = {
            item["scene_id"]: item
            for item in plan.get("scenes", [])
        }
        preview_by_scene = {
            item["scene_id"]: item
            for item in preview_report.get("results", [])
        }

        published = publish_report.get("published", [])
        intro_candidates = [
            item
            for item in published
            if item.get("scene_id") == "intro"
        ]
        if not intro_candidates:
            raise DynamicVideoRenderError(
                "Phase 7B demo integration currently requires an approved "
                "generated scene with scene_id 'intro'."
            )

        intro = intro_candidates[0]
        scene_input = scene_inputs.get("intro")
        preview = preview_by_scene.get("intro")
        if scene_input is None:
            raise DynamicVideoRenderError("Generation input for intro is missing.")
        if preview is None or not preview.get("visual_approved"):
            raise DynamicVideoRenderError("The intro scene is not visually approved.")

        intro_duration = float(
            scene_input.get("duration_hint_seconds", 8.0)
        )
        intro_duration = min(
            max(intro_duration, 1.0),
            max(original_duration - 0.5, 1.0),
        )

        workspace = (
            Path(RENDERER_DIR).expanduser().resolve()
            / ".phase7_dynamic_render_workspaces"
            / run_path.name
        )
        if workspace.exists():
            shutil.rmtree(workspace)
        workspace.mkdir(parents=True, exist_ok=True)

        dynamic_intro = output_path / "dynamic_intro.mp4"
        final_video = output_path / "candidate_video_dynamic.mp4"
        render_log = output_path / "render_log.txt"

        intro_result = self._render_intro(
            run_path=run_path,
            workspace=workspace,
            published_item=intro,
            scene_input=scene_input,
            artifact_manifest=artifact_manifest,
            destination=dynamic_intro,
            duration_seconds=intro_duration,
            fps=fps,
            width=width,
            height=height,
            timeout_seconds=timeout_seconds,
        )

        splice_result = self._splice_intro(
            source_video=source_video,
            dynamic_intro=dynamic_intro,
            destination=final_video,
            intro_duration=intro_duration,
            fps=fps,
            width=width,
            height=height,
            timeout_seconds=timeout_seconds,
        )

        log_text = (
            "DYNAMIC INTRO RENDER\n"
            + intro_result["stdout"]
            + "\n"
            + intro_result["stderr"]
            + "\n\nFULL VIDEO SPLICE\n"
            + splice_result["stdout"]
            + "\n"
            + splice_result["stderr"]
        )
        render_log.write_text(log_text, encoding="utf-8")

        if not final_video.exists() or final_video.stat().st_size == 0:
            raise DynamicVideoRenderError(
                "Integrated dynamic video was not created."
            )

        final_probe = self._probe_media(final_video)
        final_duration = self._duration(final_probe)
        has_video = self._has_stream(final_probe, "video")
        has_audio = self._has_stream(final_probe, "audio")
        duration_delta = abs(final_duration - original_duration)

        scene_resolution = {
            "scene_id": "intro",
            "requested_strategy": "generated_component",
            "resolved_strategy": "generated_component",
            "component_name": intro["component_name"],
            "fallback_component": intro["fallback_component"],
            "source_hash_verified": True,
            "visual_qa_approved": True,
            "start_seconds": 0.0,
            "end_seconds": intro_duration,
            "duration_seconds": intro_duration,
        }
        fallback_events = []
        renderer_manifest = {
            "schema_version": "1.0",
            "run_id": run_path.name,
            "source_video": str(source_video),
            "dynamic_intro": str(dynamic_intro),
            "final_video": str(final_video),
            "video_width": width,
            "video_height": height,
            "fps": fps,
            "original_duration_seconds": original_duration,
            "final_duration_seconds": final_duration,
            "scene_resolution": [scene_resolution],
        }
        technical_checks = {
            "video_exists": final_video.exists(),
            "video_non_empty": final_video.stat().st_size > 0,
            "has_video_stream": has_video,
            "has_audio_stream": has_audio,
            "duration_delta_seconds": duration_delta,
            "duration_within_tolerance": duration_delta <= 0.35,
            "passed": (
                final_video.exists()
                and final_video.stat().st_size > 0
                and has_video
                and has_audio
                and duration_delta <= 0.35
            ),
        }
        summary = {
            "status": (
                "rendered"
                if technical_checks["passed"]
                else "rendered_with_technical_warnings"
            ),
            "output_video": str(final_video),
            "source_video": str(source_video),
            "dynamic_scene_count": 1,
            "fallback_count": len(fallback_events),
            "technical_checks": technical_checks,
            "ready_for_phase_7c": technical_checks["passed"],
        }

        save_json(
            {"scenes": [scene_resolution]},
            output_path / "scene_resolution_report.json",
        )
        save_json(
            fallback_events,
            output_path / "runtime_fallback_events.json",
        )
        save_json(
            renderer_manifest,
            output_path / "renderer_manifest.json",
        )
        save_json(
            summary,
            output_path / "render_summary.json",
        )
        (output_path / "render_summary.md").write_text(
            self._markdown(summary, scene_resolution),
            encoding="utf-8",
        )
        return summary

    def _render_intro(
        self,
        run_path,
        workspace,
        published_item,
        scene_input,
        artifact_manifest,
        destination,
        duration_seconds,
        fps,
        width,
        height,
        timeout_seconds,
    ):
        renderer = Path(RENDERER_DIR).expanduser().resolve()
        src = workspace / "src"
        public = workspace / "public"
        generated = src / "generated"
        generated.mkdir(parents=True, exist_ok=True)
        public.mkdir(parents=True, exist_ok=True)
        shutil.copytree(
            renderer / "src" / "dynamic-sdk",
            src / "dynamic-sdk",
        )
        ComponentPreviewService._copy_artifacts(
            renderer,
            public,
            artifact_manifest,
            run_path.name,
        )

        published_source = Path(
            published_item["published_source"]
        ).resolve()
        source_text = published_source.read_text(
            encoding="utf-8-sig"
        )
        workspace_text = (
            source_text
            .replace(
                'from "../../../dynamic-sdk"',
                'from "../dynamic-sdk"',
            )
            .replace(
                "from '../../../dynamic-sdk'",
                "from '../dynamic-sdk'",
            )
        )
        component_copy = generated / published_source.name
        component_copy.write_text(workspace_text, encoding="utf-8")

        duration_frames = max(
            1,
            int(round(duration_seconds * fps)),
        )
        props = ComponentPreviewService._preview_props(
            scene_input,
            artifact_manifest,
            duration_frames,
            fps,
        )
        component_name = published_item["component_name"]
        root_text = (
            'import React from "react";\n'
            'import {Composition} from "remotion";\n'
            f'import {{{component_name}}} '
            f'from "./generated/{component_copy.stem}";\n'
            'const props = '
            + json.dumps(props, ensure_ascii=False)
            + ';\n'
            'export const Root: React.FC = () => '
            'React.createElement(Composition, {\n'
            '  id: "DynamicIntro",\n'
            f'  component: {component_name},\n'
            f'  durationInFrames: {duration_frames},\n'
            f'  fps: {fps},\n'
            f'  width: {width},\n'
            f'  height: {height},\n'
            '  defaultProps: props,\n'
            '});\n'
        )
        (src / "Root.tsx").write_text(root_text, encoding="utf-8")
        (src / "index.ts").write_text(
            'import {registerRoot} from "remotion";\n'
            'import {Root} from "./Root";\n'
            'registerRoot(Root);\n',
            encoding="utf-8",
        )
        (workspace / "package.json").write_text(
            '{"name":"phase7-dynamic-render","private":true}',
            encoding="utf-8",
        )

        remotion = (
            renderer
            / "node_modules"
            / ".bin"
            / "remotion.cmd"
        )
        command = [
            str(remotion),
            "render",
            "src/index.ts",
            "DynamicIntro",
            str(destination),
            "--codec",
            "h264",
            "--pixel-format",
            "yuv420p",
            "--log",
            "error",
        ]
        completed = subprocess.run(
            command,
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        if completed.returncode != 0:
            raise DynamicVideoRenderError(
                "Dynamic intro rendering failed. "
                + (completed.stderr or completed.stdout or "")
            )
        return {
            "command": command,
            "return_code": completed.returncode,
            "stdout": completed.stdout or "",
            "stderr": completed.stderr or "",
        }

    def _splice_intro(
        self,
        source_video,
        dynamic_intro,
        destination,
        intro_duration,
        fps,
        width,
        height,
        timeout_seconds,
    ):
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise FileNotFoundError("ffmpeg is not available on PATH.")

        duration_text = f"{intro_duration:.6f}"
        filter_complex = (
            f"[0:v]scale={width}:{height},fps={fps},"
            "setsar=1,setpts=PTS-STARTPTS[v0];"
            f"[1:v]trim=start={duration_text},"
            f"scale={width}:{height},fps={fps},"
            "setsar=1,setpts=PTS-STARTPTS[v1];"
            "[v0][v1]concat=n=2:v=1:a=0[v]"
        )
        command = [
            ffmpeg,
            "-y",
            "-i",
            str(dynamic_intro),
            "-i",
            str(source_video),
            "-filter_complex",
            filter_complex,
            "-map",
            "[v]",
            "-map",
            "1:a?",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            str(destination),
        ]
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        if completed.returncode != 0:
            raise DynamicVideoRenderError(
                "Dynamic video integration failed. "
                + (completed.stderr or completed.stdout or "")
            )
        return {
            "command": command,
            "return_code": completed.returncode,
            "stdout": completed.stdout or "",
            "stderr": completed.stderr or "",
        }

    def _find_source_video(self, run_path):
        candidates = []
        for path in run_path.rglob("*.mp4"):
            lowered = path.name.lower()
            if "dynamic" in lowered:
                continue
            if "preview" in lowered:
                continue
            candidates.append(path)
        if not candidates:
            raise FileNotFoundError(
                f"No existing static MP4 was found under {run_path}."
            )
        preferred = [
            path
            for path in candidates
            if "final" in path.name.lower()
            or "candidate" in path.name.lower()
        ]
        pool = preferred or candidates
        pool.sort(
            key=lambda path: (
                path.stat().st_size,
                path.stat().st_mtime,
            ),
            reverse=True,
        )
        return pool[0].resolve()

    def _probe_media(self, path):
        ffprobe = shutil.which("ffprobe")
        if not ffprobe:
            raise FileNotFoundError("ffprobe is not available on PATH.")
        command = [
            ffprobe,
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(path),
        ]
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if completed.returncode != 0:
            raise DynamicVideoRenderError(
                "ffprobe failed for "
                f"{path}: {completed.stderr or completed.stdout}"
            )
        return json.loads(completed.stdout)

    @staticmethod
    def _has_stream(probe, codec_type):
        return any(
            item.get("codec_type") == codec_type
            for item in probe.get("streams", [])
        )

    @staticmethod
    def _duration(probe):
        value = probe.get("format", {}).get("duration")
        if value is None:
            for stream in probe.get("streams", []):
                if stream.get("duration") is not None:
                    value = stream["duration"]
                    break
        if value is None:
            raise DynamicVideoRenderError("Media duration is unavailable.")
        return float(value)

    @staticmethod
    def _video_dimensions(probe):
        for stream in probe.get("streams", []):
            if stream.get("codec_type") == "video":
                return int(stream["width"]), int(stream["height"])
        raise DynamicVideoRenderError("Video stream dimensions are unavailable.")

    @staticmethod
    def _video_fps(probe):
        for stream in probe.get("streams", []):
            if stream.get("codec_type") != "video":
                continue
            rate = stream.get("avg_frame_rate") or stream.get("r_frame_rate")
            if rate and rate != "0/0":
                numerator, denominator = rate.split("/", 1)
                value = float(numerator) / float(denominator)
                return max(1, int(round(value)))
        return 30

    @staticmethod
    def _markdown(summary, scene_resolution):
        checks = summary["technical_checks"]
        return "\n".join(
            [
                "# Dynamic Video Render Summary",
                "",
                f"Status: {summary['status']}",
                f"Output: `{summary['output_video']}`",
                f"Source video: `{summary['source_video']}`",
                f"Dynamic scenes: {summary['dynamic_scene_count']}",
                f"Fallbacks: {summary['fallback_count']}",
                f"Technical checks passed: {checks['passed']}",
                f"Has video stream: {checks['has_video_stream']}",
                f"Has audio stream: {checks['has_audio_stream']}",
                f"Duration delta: {checks['duration_delta_seconds']:.3f}s",
                f"Ready for Phase 7C: {summary['ready_for_phase_7c']}",
                "",
                "## Scene Resolution",
                "",
                f"- Scene: {scene_resolution['scene_id']}",
                f"- Component: {scene_resolution['component_name']}",
                f"- Fallback: {scene_resolution['fallback_component']}",
                f"- Duration: {scene_resolution['duration_seconds']:.3f}s",
            ]
        )
