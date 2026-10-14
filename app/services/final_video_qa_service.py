"""Run technical and visual cohesion QA on the integrated dynamic video."""
from __future__ import annotations
import base64
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from PIL import Image
from openai import OpenAI
from app.config import PROMPTS_DIR, settings
from app.schemas.final_video_qa import FullVideoCohesionResult
from app.utils.json_utils import load_json, save_json
from app.utils.logging import get_logger

logger = get_logger(__name__)


class FinalVideoQAError(Exception):
    """Raised when final-video QA cannot be completed."""


class FinalVideoQAService:
    """Sample the complete video, run technical checks, and assess cohesion."""

    def __init__(self, model=None, api_key=None):
        self.model = model or settings.openai_model
        self.api_key = api_key or settings.openai_api_key
        self.client = OpenAI(api_key=self.api_key) if self.api_key else None

    def review(self, run_directory, output_directory, run_cohesion_qa=True, timeout_seconds=300):
        run_path = Path(run_directory).expanduser().resolve()
        output_path = Path(output_directory).expanduser().resolve()
        output_path.mkdir(parents=True, exist_ok=True)
        video_path, renderer_manifest = self._resolve_render_inputs(run_path)
        generation_plan_path = (
            run_path
            / "05d_generated_components"
            / "generation_plan.json"
        )
        generation_plan = (
            load_json(generation_plan_path)
            if generation_plan_path.exists()
            else {}
        )

        probe = self._probe(video_path)
        duration = self._duration(probe)
        sample_points = self._sample_points(duration, renderer_manifest)
        frames_dir = output_path / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)
        frames, extraction_errors = self._extract_frames(video_path, frames_dir, sample_points, timeout_seconds)
        deterministic = self._deterministic_checks(
            video_path,
            probe,
            frames,
            extraction_errors,
            sample_points,
            renderer_manifest,
        )
        save_json(deterministic, output_path / "technical_qa.json")
        scene_context = self._scene_context(
            renderer_manifest,
            generation_plan,
        )

        cohesion = None
        if deterministic["passed"] and run_cohesion_qa:
            cohesion = self._run_cohesion_qa(
                frames,
                deterministic,
                scene_context,
            )
            cohesion = self._apply_policy(cohesion)
            save_json(cohesion.model_dump(mode="json"), output_path / "cohesion_qa.json")

        cohesion_approved = bool(cohesion and cohesion.approved)
        if not deterministic["passed"]:
            status = "technical_issues_reported"
        elif run_cohesion_qa and cohesion:
            status = (
                "visual_qa_complete_with_concerns"
                if cohesion.warning_count or cohesion.blocking_issue_count
                else "visual_qa_complete"
            )
        else:
            status = "technical_checks_only"

        video_sha256 = self._sha256_file(video_path)
        report = {
            "status": status,
            "video_path": str(video_path),
            "video_sha256": video_sha256,
            "duration_seconds": duration,
            "sample_points": sample_points,
            "frames": frames,
            "scene_coverage": deterministic["scene_coverage"],
            "technical_qa": deterministic,
            "cohesion_qa": cohesion.model_dump(mode="json") if cohesion else None,
            "delivery_blocked": False,
            "visual_assessment_completed": cohesion is not None,
            "quality_concerns_found": bool(
                not deterministic["passed"]
                or (
                    cohesion
                    and (
                        not cohesion.approved
                        or cohesion.warning_count
                        or cohesion.blocking_issue_count
                    )
                )
            ),
            "ready_for_final_approval": deterministic["passed"] and (cohesion_approved if run_cohesion_qa else True),
        }
        save_json(report, output_path / "final_video_qa_report.json")
        (output_path / "final_video_qa_summary.md").write_text(self._markdown(report), encoding="utf-8")
        return report

    @staticmethod
    def _resolve_render_inputs(run_path):
        video_dir = run_path / "09_video"
        metadata_path = video_dir / "render_metadata.json"
        render_spec_path = run_path / "08_render_spec" / "render_spec.json"
        if metadata_path.exists() and render_spec_path.exists():
            render_metadata = load_json(metadata_path)
            render_result = render_metadata.get("result", {})
            output_value = (
                render_metadata.get("output_path")
                or render_result.get("output_path")
            )
            video_path = (
                Path(output_value).expanduser().resolve()
                if output_value
                else video_dir / "candidate_snapshot.mp4"
            )
            if not video_path.exists() or video_path.stat().st_size == 0:
                raise FileNotFoundError(
                    f"Master-render video is missing or empty: {video_path}"
                )
            if render_result.get("return_code", 0) != 0:
                raise FinalVideoQAError(
                    "Master-render metadata records a failed render."
                )

            render_spec = load_json(render_spec_path)
            renderer_manifest = FinalVideoQAService._master_render_manifest(
                render_spec
            )
            return video_path, renderer_manifest

        dynamic_dir = run_path / "10_dynamic_render"
        dynamic_video = dynamic_dir / "candidate_video_dynamic.mp4"
        dynamic_summary_path = dynamic_dir / "render_summary.json"
        dynamic_manifest_path = dynamic_dir / "renderer_manifest.json"

        if not dynamic_video.exists():
            raise FileNotFoundError(
                "Neither complete master-render outputs nor a dynamic "
                "rendered video are available for final QA."
            )
        if (
            not dynamic_summary_path.exists()
            or not dynamic_manifest_path.exists()
        ):
            raise FileNotFoundError(
                "Dynamic-render metadata is incomplete."
            )
        dynamic_summary = load_json(dynamic_summary_path)
        if not dynamic_summary.get("ready_for_phase_7c"):
            raise FinalVideoQAError(
                "Dynamic-render technical checks are not approved."
            )
        return dynamic_video, load_json(dynamic_manifest_path)

    @staticmethod
    def _master_render_manifest(render_spec):
        video_settings = render_spec.get("video", {})
        fps = float(video_settings.get("fps") or 0)
        if fps <= 0:
            raise FinalVideoQAError(
                "Master render specification has an invalid FPS value."
            )

        scenes = []
        for scene in render_spec.get("scenes", []):
            start_frame = int(scene.get("start_frame", 0))
            duration_frames = int(scene.get("duration_frames", 0))
            props = scene.get("props", {})
            scenes.append(
                {
                    "scene_id": scene.get("scene_id"),
                    "start_seconds": start_frame / fps,
                    "end_seconds": (
                        start_frame + duration_frames
                    ) / fps,
                    "resolved_strategy": scene.get("renderer_strategy"),
                    "component_name": scene.get("component"),
                    "fallback_component": scene.get("component"),
                    "props": props,
                }
            )
        return {
            "schema_version": render_spec.get("schema_version"),
            "render_type": "master_single_composition",
            "fps": fps,
            "scene_resolution": scenes,
        }

    def _run_cohesion_qa(self, frames, technical_qa, scene_context):
        if self.client is None:
            raise FinalVideoQAError("OPENAI_API_KEY is required for cohesion QA.")
        instructions = (Path(PROMPTS_DIR) / "full_video_cohesion_qa.txt").read_text(encoding="utf-8-sig").strip()
        content = [{
            "type": "input_text",
            "text": json.dumps(
                {
                    "technical_qa": technical_qa,
                    "scene_context": scene_context,
                },
                ensure_ascii=False,
            ),
        }]
        for frame in frames:
            encoded = base64.b64encode(Path(frame["path"]).read_bytes()).decode("ascii")
            content.append(
                {
                    "type": "input_text",
                    "text": (
                        f"Sample: {frame['label']} "
                        f"(scene_id={frame.get('scene_id')}, "
                        f"role={frame.get('sample_role')}, "
                        f"resolved_strategy={frame.get('resolved_strategy')}) "
                        f"at {frame['timestamp_seconds']:.3f} seconds."
                    ),
                }
            )
            content.append({"type": "input_image", "image_url": f"data:image/png;base64,{encoded}"})
        response = self.client.responses.parse(
            model=self.model,
            instructions=instructions,
            input=[{"role": "user", "content": content}],
            text_format=FullVideoCohesionResult,
        )
        parsed = response.output_parsed
        if parsed is None:
            raise FinalVideoQAError("Cohesion QA returned no parsed result.")
        if not isinstance(parsed, FullVideoCohesionResult):
            parsed = FullVideoCohesionResult.model_validate(parsed)
        return parsed

    @staticmethod
    def _apply_policy(result):
        blocking_categories = {"factual_integrity", "prohibited_content", "missing_confidentiality", "render_failure", "text_clipping", "severe_overlap", "black_frame"}
        blocking = []
        for issue in result.issues:
            category = issue.category.strip().lower().replace("-", "_").replace(" ", "_")
            severity = issue.severity.strip().lower()
            if issue.blocking or severity in {"critical", "high"} or category in blocking_categories:
                blocking.append(issue)
        warnings = len(result.issues) - len(blocking)
        approved = (
            not blocking
            and result.overall_score >= 0.70
            and result.pacing_score >= 0.65
        )
        result.approved = approved
        result.approved_with_warnings = approved and warnings > 0
        result.blocking_issue_count = len(blocking)
        result.warning_count = warnings
        return result

    @staticmethod
    def _sample_points(duration, renderer_manifest):
        scenes = sorted(
            renderer_manifest.get("scene_resolution", []),
            key=lambda scene: float(scene.get("start_seconds", 0.0)),
        )
        points = []
        if scenes:
            last_timestamp = max(0.0, duration - 0.01)
            for index, scene in enumerate(scenes, start=1):
                start = max(0.0, float(scene.get("start_seconds", 0.0)))
                end = min(
                    duration,
                    float(scene.get("end_seconds", duration)),
                )
                scene_duration = end - start
                if scene_duration <= 0:
                    continue

                opening_offset = min(0.2, scene_duration * 0.1)
                timestamps = (
                    ("opening", start + opening_offset),
                    ("midpoint", start + scene_duration * 0.5),
                )
                for role, timestamp in timestamps:
                    timestamp = min(last_timestamp, max(0.0, timestamp))
                    points.append(
                        {
                            "label": f"scene_{index:02d}_{role}",
                            "timestamp_seconds": round(timestamp, 3),
                            "scene_id": scene.get("scene_id"),
                            "sample_role": role,
                            "resolved_strategy": scene.get(
                                "resolved_strategy"
                            ),
                        }
                    )
        else:
            epsilon = min(0.25, max(duration * 0.002, 0.04))
            raw = [
                ("opening", duration * 0.02),
                ("quarter", duration * 0.25),
                ("middle", duration * 0.50),
                ("three_quarter", duration * 0.75),
                ("closing", duration * 0.97),
            ]
            points = [
                {
                    "label": label,
                    "timestamp_seconds": round(
                        min(duration - epsilon, max(epsilon, value)),
                        3,
                    ),
                    "scene_id": None,
                    "sample_role": "video_anchor",
                    "resolved_strategy": None,
                }
                for label, value in raw
            ]
        return points

    @staticmethod
    def _scene_context(renderer_manifest, generation_plan):
        planned_scenes = {
            scene.get("scene_id"): scene
            for scene in generation_plan.get("scenes", [])
            if scene.get("scene_id")
        }
        context = []
        for index, resolved in enumerate(
            renderer_manifest.get("scene_resolution", []),
            start=1,
        ):
            planned = planned_scenes.get(resolved.get("scene_id"), {})
            architecture = planned.get("scene_architecture", {})
            props = resolved.get("props", {})
            renderer_instructions = props.get(
                "renderer_instructions",
                {},
            )
            context.append(
                {
                    "sequence_index": index,
                    "scene_id": resolved.get("scene_id"),
                    "start_seconds": resolved.get("start_seconds"),
                    "end_seconds": resolved.get("end_seconds"),
                    "resolved_strategy": resolved.get("resolved_strategy"),
                    "component_name": resolved.get("component_name"),
                    "fallback_component": resolved.get(
                        "fallback_component"
                    ),
                    "failure_reason": resolved.get("failure_reason"),
                    "scene_purpose": (
                        architecture.get("scene_purpose")
                        or renderer_instructions.get("scene_purpose")
                        or props.get("purpose")
                    ),
                    "visual_story": (
                        architecture.get("visual_story")
                        or renderer_instructions.get("visual_story")
                    ),
                    "layout_intent": (
                        architecture.get("layout_intent")
                        or renderer_instructions.get("layout_intent")
                    ),
                    "visual_hierarchy": architecture.get(
                        "visual_hierarchy"
                    ),
                    "focal_element": architecture.get("focal_element"),
                    "approved_facts": (
                        planned.get("approved_facts")
                        or props.get("approved_facts", [])
                    ),
                }
            )
        return context

    @staticmethod
    def _extract_frames(video_path, frames_dir, sample_points, timeout_seconds):
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise FileNotFoundError("ffmpeg is not available on PATH.")
        frames = []
        errors = []
        for item in sample_points:
            destination = frames_dir / f"{item['label']}_{item['timestamp_seconds']:.3f}.png"
            command = [ffmpeg, "-y", "-ss", f"{item['timestamp_seconds']:.3f}", "-i", str(video_path), "-frames:v", "1", "-vf", "scale=1920:1080", str(destination)]
            completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout_seconds, check=False)
            if completed.returncode != 0 or not destination.exists():
                errors.append({"label": item["label"], "timestamp_seconds": item["timestamp_seconds"], "stdout": completed.stdout, "stderr": completed.stderr})
                continue
            frames.append(
                {
                    "label": item["label"],
                    "timestamp_seconds": item["timestamp_seconds"],
                    "scene_id": item.get("scene_id"),
                    "sample_role": item.get("sample_role"),
                    "resolved_strategy": item.get("resolved_strategy"),
                    "path": str(destination),
                }
            )
        return frames, errors

    @staticmethod
    def _deterministic_checks(
        video_path,
        probe,
        frames,
        extraction_errors,
        sample_points,
        renderer_manifest,
    ):
        has_video = any(item.get("codec_type") == "video" for item in probe.get("streams", []))
        has_audio = any(item.get("codec_type") == "audio" for item in probe.get("streams", []))
        invalid_frames = []
        black_suspects = []
        for frame in frames:
            path = Path(frame["path"])
            try:
                with Image.open(path) as image:
                    image.verify()
                with Image.open(path).convert("RGB") as image:
                    if image.size != (1920, 1080):
                        invalid_frames.append(f"{path.name}: {image.size[0]}x{image.size[1]}")
                    sample = image.resize((32, 18))
                    mean = sum(sum(pixel) for pixel in sample.getdata()) / (32 * 18 * 3)
                    if mean < 3.0:
                        black_suspects.append(path.name)
            except Exception as error:
                invalid_frames.append(f"{path}: {error}")
        sampled_scenes = {
            frame.get("scene_id")
            for frame in frames
            if frame.get("scene_id")
        }
        expected_scenes = {
            scene.get("scene_id")
            for scene in renderer_manifest.get("scene_resolution", [])
            if scene.get("scene_id")
        }
        uncovered_scenes = sorted(expected_scenes - sampled_scenes)
        scene_coverage = [
            {
                "scene_id": scene.get("scene_id"),
                "resolved_strategy": scene.get("resolved_strategy"),
                "sampled_frame_count": sum(
                    1
                    for frame in frames
                    if frame.get("scene_id") == scene.get("scene_id")
                ),
                "sample_labels": [
                    frame["label"]
                    for frame in frames
                    if frame.get("scene_id") == scene.get("scene_id")
                ],
            }
            for scene in renderer_manifest.get("scene_resolution", [])
        ]
        passed = (
            video_path.exists()
            and video_path.stat().st_size > 0
            and has_video
            and has_audio
            and bool(sample_points)
            and len(frames) == len(sample_points)
            and not uncovered_scenes
            and not extraction_errors
            and not invalid_frames
            and not black_suspects
        )
        return {
            "passed": passed,
            "video_exists": video_path.exists(),
            "video_non_empty": video_path.exists() and video_path.stat().st_size > 0,
            "has_video_stream": has_video,
            "has_audio_stream": has_audio,
            "sampled_frame_count": len(frames),
            "expected_sample_count": len(sample_points),
            "scene_coverage": scene_coverage,
            "uncovered_scene_ids": uncovered_scenes,
            "extraction_errors": extraction_errors,
            "invalid_frames": invalid_frames,
            "black_frame_suspects": black_suspects,
        }

    @staticmethod
    def _probe(video_path):
        ffprobe = shutil.which("ffprobe")
        if not ffprobe:
            raise FileNotFoundError("ffprobe is not available on PATH.")
        completed = subprocess.run([ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(video_path)], capture_output=True, text=True, timeout=60, check=False)
        if completed.returncode != 0:
            raise FinalVideoQAError(completed.stderr or completed.stdout)
        return json.loads(completed.stdout)

    @staticmethod
    def _duration(probe):
        value = probe.get("format", {}).get("duration")
        if value is None:
            raise FinalVideoQAError("Final video duration is unavailable.")
        return float(value)

    @staticmethod
    def _sha256_file(path):
        digest = hashlib.sha256()
        with Path(path).open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _markdown(report):
        cohesion = report.get("cohesion_qa") or {}
        technical = report["technical_qa"]
        scene_coverage = report.get("scene_coverage", [])
        covered_scene_count = sum(
            1 for scene in scene_coverage if scene["sampled_frame_count"]
        )
        return "\n".join([
            "# Final Dynamic Video QA Summary", "",
            f"Status: {report['status']}",
            f"Video: `{report['video_path']}`",
            f"Video SHA-256: `{report['video_sha256']}`",
            f"Technical QA passed: {technical['passed']}",
            f"Sampled frames: {technical['sampled_frame_count']}",
            f"Scenes sampled: {covered_scene_count}/{len(scene_coverage)}",
            f"Blocking visual issues: {cohesion.get('blocking_issue_count', 0)}",
            f"Visual warnings: {cohesion.get('warning_count', 0)}",
            f"Quality concerns found: {report['quality_concerns_found']}",
            f"Video delivery blocked: {report['delivery_blocked']}",
        ])


def create_final_video_approval(run_directory, reviewer, decision, notes):
    run_path = Path(run_directory).expanduser().resolve()
    qa_dir = run_path / "10_dynamic_render" / "final_qa"
    report_path = qa_dir / "final_video_qa_report.json"
    if not report_path.exists():
        raise FileNotFoundError("Final video QA report is missing.")
    report = load_json(report_path)
    if decision == "approved_for_demo" and not report.get("ready_for_final_approval"):
        raise FinalVideoQAError("Final QA is not approved; demo release is blocked.")
    payload = {
        "decision": decision,
        "approved": decision == "approved_for_demo",
        "reviewer": reviewer,
        "review_notes": notes,
        "video_path": report["video_path"],
        "video_sha256": report["video_sha256"],
        "qa_status": report["status"],
    }
    approval_path = qa_dir / "final_video_approval.json"
    save_json(payload, approval_path)
    return approval_path
