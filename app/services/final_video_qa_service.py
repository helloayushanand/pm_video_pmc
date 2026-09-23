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
        render_dir = run_path / "10_dynamic_render"
        video_path = render_dir / "candidate_video_dynamic.mp4"
        render_summary_path = render_dir / "render_summary.json"
        manifest_path = render_dir / "renderer_manifest.json"
        if not video_path.exists():
            raise FileNotFoundError(f"Dynamic video is missing: {video_path}")
        if not render_summary_path.exists() or not manifest_path.exists():
            raise FileNotFoundError("Phase 7B render metadata is incomplete.")

        render_summary = load_json(render_summary_path)
        renderer_manifest = load_json(manifest_path)
        if not render_summary.get("ready_for_phase_7c"):
            raise FinalVideoQAError("Phase 7B technical checks are not approved.")

        probe = self._probe(video_path)
        duration = self._duration(probe)
        sample_points = self._sample_points(duration, renderer_manifest)
        frames_dir = output_path / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)
        frames, extraction_errors = self._extract_frames(video_path, frames_dir, sample_points, timeout_seconds)
        deterministic = self._deterministic_checks(video_path, probe, frames, extraction_errors)
        save_json(deterministic, output_path / "technical_qa.json")

        cohesion = None
        if deterministic["passed"] and run_cohesion_qa:
            cohesion = self._run_cohesion_qa(frames, deterministic, renderer_manifest)
            cohesion = self._apply_policy(cohesion)
            save_json(cohesion.model_dump(mode="json"), output_path / "cohesion_qa.json")

        cohesion_approved = bool(cohesion and cohesion.approved)
        if not deterministic["passed"]:
            status = "technical_qa_failed"
        elif run_cohesion_qa and not cohesion_approved:
            status = "cohesion_review_required"
        else:
            status = "qa_approved"

        video_sha256 = self._sha256_file(video_path)
        report = {
            "status": status,
            "video_path": str(video_path),
            "video_sha256": video_sha256,
            "duration_seconds": duration,
            "sample_points": sample_points,
            "frames": frames,
            "technical_qa": deterministic,
            "cohesion_qa": cohesion.model_dump(mode="json") if cohesion else None,
            "ready_for_final_approval": deterministic["passed"] and (cohesion_approved if run_cohesion_qa else True),
        }
        save_json(report, output_path / "final_video_qa_report.json")
        (output_path / "final_video_qa_summary.md").write_text(self._markdown(report), encoding="utf-8")
        return report

    def _run_cohesion_qa(self, frames, technical_qa, renderer_manifest):
        if self.client is None:
            raise FinalVideoQAError("OPENAI_API_KEY is required for cohesion QA.")
        instructions = (Path(PROMPTS_DIR) / "full_video_cohesion_qa.txt").read_text(encoding="utf-8-sig").strip()
        content = [{"type": "input_text", "text": json.dumps({"technical_qa": technical_qa, "renderer_manifest": renderer_manifest}, ensure_ascii=False)}]
        for frame in frames:
            encoded = base64.b64encode(Path(frame["path"]).read_bytes()).decode("ascii")
            content.append({"type": "input_text", "text": f"Sample: {frame['label']} at {frame['timestamp_seconds']:.3f} seconds"})
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
        approved = not blocking and result.overall_score >= 0.70 and result.pacing_score >= 0.65
        result.approved = approved
        result.approved_with_warnings = approved and warnings > 0
        result.blocking_issue_count = len(blocking)
        result.warning_count = warnings
        return result

    @staticmethod
    def _sample_points(duration, renderer_manifest):
        intro_end = 0.0
        scenes = renderer_manifest.get("scene_resolution", [])
        if scenes:
            intro_end = float(scenes[0].get("end_seconds", 0.0))
        epsilon = min(0.25, max(duration * 0.002, 0.04))
        raw = [
            ("opening", min(duration - epsilon, max(epsilon, duration * 0.02))),
            ("intro_peak", min(duration - epsilon, max(epsilon, intro_end * 0.65 if intro_end else duration * 0.10))),
            ("before_intro_boundary", min(duration - epsilon, max(epsilon, intro_end - epsilon))),
            ("after_intro_boundary", min(duration - epsilon, max(epsilon, intro_end + epsilon))),
            ("quarter", min(duration - epsilon, max(epsilon, duration * 0.25))),
            ("middle", min(duration - epsilon, max(epsilon, duration * 0.50))),
            ("three_quarter", min(duration - epsilon, max(epsilon, duration * 0.75))),
            ("closing", min(duration - epsilon, max(epsilon, duration * 0.97))),
        ]
        points = []
        seen = set()
        for label, value in raw:
            rounded = round(value, 3)
            if rounded in seen:
                continue
            seen.add(rounded)
            points.append({"label": label, "timestamp_seconds": rounded})
        return points

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
            frames.append({"label": item["label"], "timestamp_seconds": item["timestamp_seconds"], "path": str(destination)})
        return frames, errors

    @staticmethod
    def _deterministic_checks(video_path, probe, frames, extraction_errors):
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
        passed = video_path.exists() and video_path.stat().st_size > 0 and has_video and has_audio and len(frames) >= 6 and not extraction_errors and not invalid_frames and not black_suspects
        return {
            "passed": passed,
            "video_exists": video_path.exists(),
            "video_non_empty": video_path.exists() and video_path.stat().st_size > 0,
            "has_video_stream": has_video,
            "has_audio_stream": has_audio,
            "sampled_frame_count": len(frames),
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
        return "\n".join([
            "# Final Dynamic Video QA Summary", "",
            f"Status: {report['status']}",
            f"Video: `{report['video_path']}`",
            f"Video SHA-256: `{report['video_sha256']}`",
            f"Technical QA passed: {technical['passed']}",
            f"Sampled frames: {technical['sampled_frame_count']}",
            f"Cohesion approved: {cohesion.get('approved')}",
            f"Approved with warnings: {cohesion.get('approved_with_warnings')}",
            f"Ready for final approval: {report['ready_for_final_approval']}",
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
