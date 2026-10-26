"""Render approved generated scenes and integrate them into the full video timeline."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from app.config import RENDERER_DIR
from app.services.component_preview_service import ComponentPreviewService
from app.utils.json_utils import load_json, save_json
from app.utils.logging import get_logger

logger = get_logger(__name__)


class DynamicVideoRenderError(Exception):
    """Raised when the integrated dynamic video cannot be rendered."""


class DynamicVideoRenderService:
    """Render an ordered mix of generated and existing static scene segments.

    The authoritative audio remains the audio stream from the existing full
    video. Each timeline scene is resolved independently:

    * use an approved generated component when one is published and visually
      approved;
    * otherwise extract the corresponding interval from the existing video;
    * if a generated scene fails at runtime, record the failure and use the
      original static interval as a safe fallback.
    """

    def render(
        self,
        run_directory,
        output_directory,
        timeout_seconds=900,
    ):
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

        for required_path in (
            publish_path,
            preview_path,
            plan_path,
            artifact_path,
        ):
            if not required_path.exists():
                raise FileNotFoundError(
                    f"Required dynamic-render input is missing: {required_path}"
                )

        publish_report = load_json(publish_path)
        preview_report = load_json(preview_path)
        generation_plan = load_json(plan_path)
        artifact_manifest = load_json(artifact_path)

        if not publish_report.get("ready_for_runtime_integration"):
            raise DynamicVideoRenderError(
                "Published components are not ready for runtime integration."
            )
        if not preview_report.get("ready_for_phase_7"):
            raise DynamicVideoRenderError(
                "Per-scene visual QA is not approved."
            )

        source_video = self._find_source_video(run_path)
        source_probe = self._probe_media(source_video)
        fps = self._video_fps(source_probe)
        width, height = self._video_dimensions(source_probe)
        original_duration = self._duration(source_probe)

        timeline = self._resolve_timeline(
            run_path=run_path,
            source_duration=original_duration,
            fps=fps,
        )
        if not timeline:
            raise DynamicVideoRenderError("The resolved scene timeline is empty.")

        published_by_scene = {
            item["scene_id"]: item
            for item in publish_report.get("published", [])
        }
        preview_by_scene = {
            item["scene_id"]: item
            for item in preview_report.get("results", [])
        }
        scene_inputs = {
            item["scene_id"]: item
            for item in generation_plan.get("scenes", [])
        }

        renderer = Path(RENDERER_DIR).expanduser().resolve()
        workspace_root = (
            renderer
            / ".phase7_dynamic_render_workspaces"
            / run_path.name
        )
        if workspace_root.exists():
            shutil.rmtree(workspace_root)
        workspace_root.mkdir(parents=True, exist_ok=True)

        segments_dir = output_path / "segments"
        if segments_dir.exists():
            shutil.rmtree(segments_dir)
        segments_dir.mkdir(parents=True, exist_ok=True)

        scene_resolution: list[dict[str, Any]] = []
        fallback_events: list[dict[str, Any]] = []
        segment_paths: list[Path] = []
        render_logs: list[str] = []

        for index, timeline_scene in enumerate(timeline):
            scene_id = timeline_scene["scene_id"]
            generated_component = published_by_scene.get(scene_id)
            preview_result = preview_by_scene.get(scene_id)
            scene_input = scene_inputs.get(scene_id)
            segment_path = (
                segments_dir
                / f"{index + 1:02d}_{self._safe_name(scene_id)}.mp4"
            )

            requested_strategy = (
                "generated_component"
                if generated_component is not None
                else "static_component"
            )
            generated_is_available = (
                generated_component is not None
                and preview_result is not None
                and bool(preview_result.get("visual_approved"))
                and preview_result.get("status") == "visual_approved"
                and scene_input is not None
            )
            failure_reason = None

            if generated_is_available:
                try:
                    result = self._render_generated_segment(
                        run_path=run_path,
                        workspace_root=workspace_root,
                        published_item=generated_component,
                        scene_input=scene_input,
                        artifact_manifest=artifact_manifest,
                        destination=segment_path,
                        duration_seconds=timeline_scene["duration_seconds"],
                        fps=fps,
                        width=width,
                        height=height,
                        timeout_seconds=timeout_seconds,
                    )
                    render_logs.append(
                        self._format_process_log(
                            scene_id,
                            "generated_component",
                            result,
                        )
                    )
                    resolved_strategy = "generated_component"
                except Exception as error:
                    failure_reason = f"{type(error).__name__}: {error}"
                    logger.warning(
                        "Generated scene %s failed; using the static interval: %s",
                        scene_id,
                        failure_reason,
                    )
                    result = self._extract_static_segment(
                        source_video=source_video,
                        destination=segment_path,
                        start_seconds=timeline_scene["start_seconds"],
                        duration_seconds=timeline_scene["duration_seconds"],
                        fps=fps,
                        width=width,
                        height=height,
                        timeout_seconds=timeout_seconds,
                    )
                    render_logs.append(
                        self._format_process_log(
                            scene_id,
                            "static_fallback",
                            result,
                        )
                    )
                    resolved_strategy = "static_fallback"
                    fallback_events.append(
                        {
                            "scene_id": scene_id,
                            "reason": failure_reason,
                            "fallback_component": generated_component.get(
                                "fallback_component"
                            ),
                            "segment_path": str(segment_path),
                        }
                    )
            else:
                result = self._extract_static_segment(
                    source_video=source_video,
                    destination=segment_path,
                    start_seconds=timeline_scene["start_seconds"],
                    duration_seconds=timeline_scene["duration_seconds"],
                    fps=fps,
                    width=width,
                    height=height,
                    timeout_seconds=timeout_seconds,
                )
                render_logs.append(
                    self._format_process_log(
                        scene_id,
                        "static_segment",
                        result,
                    )
                )
                resolved_strategy = "static_segment"

            if not segment_path.exists() or segment_path.stat().st_size == 0:
                raise DynamicVideoRenderError(
                    f"Resolved segment is missing or empty: {segment_path}"
                )

            segment_paths.append(segment_path)
            scene_resolution.append(
                {
                    **timeline_scene,
                    "requested_strategy": requested_strategy,
                    "resolved_strategy": resolved_strategy,
                    "component_name": (
                        generated_component.get("component_name")
                        if generated_component
                        else None
                    ),
                    "fallback_component": (
                        generated_component.get("fallback_component")
                        if generated_component
                        else None
                    ),
                    "source_hash_verified": bool(generated_component),
                    "visual_qa_approved": bool(
                        preview_result and preview_result.get("visual_approved")
                    ),
                    "failure_reason": failure_reason,
                    "segment_path": str(segment_path),
                }
            )

        final_video = output_path / "candidate_video_dynamic.mp4"
        assembly_result = self._assemble_segments(
            segment_paths=segment_paths,
            source_video=source_video,
            destination=final_video,
            timeout_seconds=timeout_seconds,
        )
        render_logs.append(
            self._format_process_log(
                "full_video",
                "assembly",
                assembly_result,
            )
        )
        (output_path / "render_log.txt").write_text(
            "\n\n".join(render_logs),
            encoding="utf-8",
        )

        if not final_video.exists() or final_video.stat().st_size == 0:
            raise DynamicVideoRenderError(
                "Integrated dynamic video was not created."
            )

        final_probe = self._probe_media(final_video)
        final_duration = self._duration(final_probe)
        has_video = self._has_stream(final_probe, "video")
        has_audio = self._has_stream(final_probe, "audio")
        duration_delta = abs(final_duration - original_duration)
        dynamic_scene_count = sum(
            1
            for item in scene_resolution
            if item["resolved_strategy"] == "generated_component"
        )
        static_scene_count = sum(
            1
            for item in scene_resolution
            if item["resolved_strategy"]
            in {"static_segment", "static_fallback"}
        )

        technical_checks = {
            "video_exists": final_video.exists(),
            "video_non_empty": final_video.stat().st_size > 0,
            "has_video_stream": has_video,
            "has_audio_stream": has_audio,
            "original_duration_seconds": original_duration,
            "final_duration_seconds": final_duration,
            "duration_delta_seconds": duration_delta,
            "duration_within_tolerance": duration_delta <= 0.50,
            "resolved_scene_count": len(scene_resolution),
            "passed": (
                final_video.exists()
                and final_video.stat().st_size > 0
                and has_video
                and has_audio
                and duration_delta <= 0.50
                and len(scene_resolution) == len(timeline)
            ),
        }
        renderer_manifest = {
            "schema_version": "2.0",
            "run_id": run_path.name,
            "source_video": str(source_video),
            "final_video": str(final_video),
            "video_width": width,
            "video_height": height,
            "fps": fps,
            "original_duration_seconds": original_duration,
            "final_duration_seconds": final_duration,
            "scene_resolution": scene_resolution,
        }
        summary = {
            "status": (
                "rendered"
                if technical_checks["passed"]
                else "rendered_with_technical_warnings"
            ),
            "output_video": str(final_video),
            "source_video": str(source_video),
            "dynamic_scene_count": dynamic_scene_count,
            "static_scene_count": static_scene_count,
            "fallback_count": len(fallback_events),
            "technical_checks": technical_checks,
            "ready_for_phase_7c": technical_checks["passed"],
        }

        save_json(
            {"scenes": scene_resolution},
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

    def _resolve_timeline(self, run_path, source_duration, fps):
        """Resolve ordered scene boundaries from render spec or storyboard."""
        render_spec_path = run_path / "08_render_spec" / "render_spec.json"
        storyboard_path = run_path / "05_storyboard" / "storyboard.json"

        render_spec = (
            load_json(render_spec_path)
            if render_spec_path.exists()
            else {}
        )
        storyboard = (
            load_json(storyboard_path)
            if storyboard_path.exists()
            else {}
        )
        raw_scenes = self._extract_scene_collection(render_spec)
        if not raw_scenes:
            raw_scenes = self._extract_scene_collection(storyboard)
        if not raw_scenes:
            raise DynamicVideoRenderError(
                "No scene collection was found in render_spec.json or "
                "storyboard.json."
            )

        scenes = []
        running_start = 0.0
        for index, raw_scene in enumerate(raw_scenes):
            scene_id = (
                raw_scene.get("scene_id")
                or raw_scene.get("sceneId")
                or raw_scene.get("id")
                or f"scene_{index + 1:02d}"
            )
            start_seconds = self._first_number(
                raw_scene,
                ["start_seconds", "start_time", "start", "from_seconds"],
            )
            end_seconds = self._first_number(
                raw_scene,
                ["end_seconds", "end_time", "end", "to_seconds"],
            )
            duration_seconds = self._first_number(
                raw_scene,
                [
                    "duration_seconds",
                    "approx_duration_seconds",
                    "duration",
                ],
            )
            start_frame = self._first_number(
                raw_scene,
                ["start_frame", "from_frame"],
            )
            end_frame = self._first_number(
                raw_scene,
                ["end_frame", "to_frame"],
            )
            duration_frames = self._first_number(
                raw_scene,
                ["duration_in_frames", "duration_frames"],
            )

            if start_seconds is None and start_frame is not None:
                start_seconds = start_frame / fps
            if end_seconds is None and end_frame is not None:
                end_seconds = end_frame / fps
            if duration_seconds is None and duration_frames is not None:
                duration_seconds = duration_frames / fps
            if start_seconds is None:
                start_seconds = running_start
            if end_seconds is None and duration_seconds is not None:
                end_seconds = start_seconds + duration_seconds

            if end_seconds is None:
                next_start = self._next_start_seconds(raw_scenes, index, fps)
                if next_start is not None:
                    end_seconds = next_start
                elif index == len(raw_scenes) - 1:
                    end_seconds = source_duration
                else:
                    raise DynamicVideoRenderError(
                        f"Unable to resolve an end time for scene {scene_id}."
                    )

            start_seconds = max(0.0, float(start_seconds))
            end_seconds = min(source_duration, float(end_seconds))
            if end_seconds <= start_seconds:
                raise DynamicVideoRenderError(
                    f"Invalid timeline interval for {scene_id}: "
                    f"{start_seconds} to {end_seconds}."
                )

            scenes.append(
                {
                    "scene_id": str(scene_id),
                    "scene_type": raw_scene.get(
                        "scene_type",
                        raw_scene.get("type", "generic"),
                    ),
                    "start_seconds": start_seconds,
                    "end_seconds": end_seconds,
                    "duration_seconds": end_seconds - start_seconds,
                    "start_frame": int(round(start_seconds * fps)),
                    "end_frame": int(round(end_seconds * fps)),
                }
            )
            running_start = end_seconds

        scenes.sort(key=lambda item: item["start_seconds"])
        scenes[0]["start_seconds"] = 0.0
        scenes[0]["start_frame"] = 0
        for index in range(1, len(scenes)):
            previous_end = scenes[index - 1]["end_seconds"]
            current_start = scenes[index]["start_seconds"]
            if abs(current_start - previous_end) <= 0.50:
                scenes[index]["start_seconds"] = previous_end
                scenes[index]["start_frame"] = int(round(previous_end * fps))
                scenes[index]["duration_seconds"] = (
                    scenes[index]["end_seconds"] - previous_end
                )
        scenes[-1]["end_seconds"] = source_duration
        scenes[-1]["end_frame"] = int(round(source_duration * fps))
        scenes[-1]["duration_seconds"] = (
            source_duration - scenes[-1]["start_seconds"]
        )
        return scenes

    @staticmethod
    def _extract_scene_collection(value):
        if isinstance(value, list):
            return value
        if not isinstance(value, dict):
            return []
        for key in (
            "scenes",
            "timeline",
            "scene_specs",
            "segments",
            "scene_timeline",
        ):
            candidate = value.get(key)
            if isinstance(candidate, list) and candidate:
                return candidate
        for candidate in value.values():
            if not isinstance(candidate, dict):
                continue
            nested = DynamicVideoRenderService._extract_scene_collection(candidate)
            if nested:
                return nested
        return []

    @staticmethod
    def _first_number(value, keys):
        for key in keys:
            candidate = value.get(key)
            if candidate is None:
                continue
            try:
                return float(candidate)
            except (TypeError, ValueError):
                continue
        return None

    def _next_start_seconds(self, raw_scenes, index, fps):
        if index + 1 >= len(raw_scenes):
            return None
        next_scene = raw_scenes[index + 1]
        seconds = self._first_number(
            next_scene,
            ["start_seconds", "start_time", "start", "from_seconds"],
        )
        if seconds is not None:
            return seconds
        frame = self._first_number(
            next_scene,
            ["start_frame", "from_frame"],
        )
        return frame / fps if frame is not None else None

    def _render_generated_segment(
        self,
        run_path,
        workspace_root,
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
        scene_workspace = (
            workspace_root
            / self._safe_name(scene_input["scene_id"])
        )
        if scene_workspace.exists():
            shutil.rmtree(scene_workspace)
        src = scene_workspace / "src"
        public = scene_workspace / "public"
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
        source_text = published_source.read_text(encoding="utf-8-sig")
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
            .replace(
                'from "@/dynamic-sdk"',
                'from "../dynamic-sdk"',
            )
            .replace(
                "from '@/dynamic-sdk'",
                "from '../dynamic-sdk'",
            )
        )
        component_copy = generated / published_source.name
        component_copy.write_text(workspace_text, encoding="utf-8")

        duration_frames = max(1, int(round(duration_seconds * fps)))
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
            '  id: "DynamicScene",\n'
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
        (scene_workspace / "package.json").write_text(
            '{"name":"phase7-scene-render","private":true}',
            encoding="utf-8",
        )

        remotion = renderer / "node_modules" / ".bin" / "remotion.cmd"
        command = [
            str(remotion),
            "render",
            "src/index.ts",
            "DynamicScene",
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
            cwd=str(scene_workspace),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        if completed.returncode != 0:
            raise DynamicVideoRenderError(
                "Generated scene rendering failed: "
                + (completed.stderr or completed.stdout or "")
            )
        return self._process_result(command, completed)

    def _extract_static_segment(
        self,
        source_video,
        destination,
        start_seconds,
        duration_seconds,
        fps,
        width,
        height,
        timeout_seconds,
    ):
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise FileNotFoundError("ffmpeg is not available on PATH.")
        command = [
            ffmpeg,
            "-y",
            "-ss",
            f"{start_seconds:.6f}",
            "-i",
            str(source_video),
            "-t",
            f"{duration_seconds:.6f}",
            "-an",
            "-vf",
            f"scale={width}:{height},fps={fps},setsar=1",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
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
                "Static interval extraction failed: "
                + (completed.stderr or completed.stdout or "")
            )
        return self._process_result(command, completed)

    def _assemble_segments(
        self,
        segment_paths,
        source_video,
        destination,
        timeout_seconds,
    ):
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise FileNotFoundError("ffmpeg is not available on PATH.")
        concat_file = destination.parent / "segments.txt"
        concat_file.write_text(
            "\n".join(
                f"file '{self._concat_path(path)}'"
                for path in segment_paths
            ),
            encoding="utf-8",
        )
        video_only = destination.parent / "video_without_audio.mp4"
        concatenate_command = [
            ffmpeg,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-an",
            str(video_only),
        ]
        concatenate = subprocess.run(
            concatenate_command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        if concatenate.returncode != 0:
            raise DynamicVideoRenderError(
                "Scene concatenation failed: "
                + (concatenate.stderr or concatenate.stdout or "")
            )

        audio_command = [
            ffmpeg,
            "-y",
            "-i",
            str(video_only),
            "-i",
            str(source_video),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0?",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            "-movflags",
            "+faststart",
            str(destination),
        ]
        audio_result = subprocess.run(
            audio_command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        if audio_result.returncode != 0:
            raise DynamicVideoRenderError(
                "Narration attachment failed: "
                + (audio_result.stderr or audio_result.stdout or "")
            )
        return {
            "command": audio_command,
            "return_code": audio_result.returncode,
            "stdout": (
                "CONCATENATION\n"
                + (concatenate.stdout or "")
                + "\n"
                + (concatenate.stderr or "")
                + "\nAUDIO MUX\n"
                + (audio_result.stdout or "")
            ),
            "stderr": audio_result.stderr or "",
        }

    def _find_source_video(self, run_path):
        preferred_paths = [
            run_path / "09_video" / "candidate_video.mp4",
            run_path / "09_video" / "final_video.mp4",
            run_path / "09_video" / "video.mp4",
        ]
        for path in preferred_paths:
            if path.exists() and path.stat().st_size > 0:
                return path.resolve()

        candidates = []
        for path in run_path.rglob("*.mp4"):
            lowered = str(path).lower()
            if "10_dynamic_render" in lowered:
                continue
            if "dynamic" in path.name.lower() or "preview" in path.name.lower():
                continue
            candidates.append(path)
        if not candidates:
            raise FileNotFoundError(
                f"No existing static MP4 was found under {run_path}."
            )
        candidates.sort(
            key=lambda path: (path.stat().st_size, path.stat().st_mtime),
            reverse=True,
        )
        return candidates[0].resolve()

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
                f"ffprobe failed for {path}: "
                + (completed.stderr or completed.stdout or "")
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
                return max(1, int(round(float(numerator) / float(denominator))))
        return 30

    @staticmethod
    def _safe_name(value):
        return re.sub(r"[^A-Za-z0-9_-]", "_", str(value))

    @staticmethod
    def _concat_path(path):
        return str(Path(path).resolve()).replace("\\", "/").replace("'", "'\\''")

    @staticmethod
    def _process_result(command, completed):
        return {
            "command": command,
            "return_code": completed.returncode,
            "stdout": completed.stdout or "",
            "stderr": completed.stderr or "",
        }

    @staticmethod
    def _format_process_log(scene_id, strategy, result):
        return "\n".join(
            [
                "=" * 72,
                f"SCENE: {scene_id}",
                f"STRATEGY: {strategy}",
                f"RETURN CODE: {result.get('return_code')}",
                "COMMAND:",
                " ".join(str(value) for value in result.get("command", [])),
                "STDOUT:",
                result.get("stdout", ""),
                "STDERR:",
                result.get("stderr", ""),
            ]
        )

    @staticmethod
    def _markdown(summary, scene_resolution):
        checks = summary["technical_checks"]
        lines = [
            "# Dynamic Video Render Summary",
            "",
            f"Status: {summary['status']}",
            f"Output: `{summary['output_video']}`",
            f"Source video: `{summary['source_video']}`",
            f"Dynamic scenes: {summary['dynamic_scene_count']}",
            f"Static scenes: {summary['static_scene_count']}",
            f"Runtime fallbacks: {summary['fallback_count']}",
            f"Technical checks passed: {checks['passed']}",
            f"Duration delta: {checks['duration_delta_seconds']:.3f}s",
            f"Ready for Phase 7C: {summary['ready_for_phase_7c']}",
            "",
            "## Scene Resolution",
            "",
        ]
        for item in scene_resolution:
            lines.extend(
                [
                    f"### {item['scene_id']}",
                    f"- Interval: {item['start_seconds']:.3f}s to "
                    f"{item['end_seconds']:.3f}s",
                    f"- Requested: {item['requested_strategy']}",
                    f"- Resolved: {item['resolved_strategy']}",
                    f"- Component: {item.get('component_name')}",
                    f"- Fallback: {item.get('fallback_component')}",
                    "",
                ]
            )
        return "\n".join(lines)
