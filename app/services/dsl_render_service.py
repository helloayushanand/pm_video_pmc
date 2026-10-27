"""Render a DSL VideoSpec to MP4 via Remotion CLI."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from app.config import RENDERER_DIR
from app.utils.logging import get_logger

logger = get_logger(__name__)


class DSLRenderError(Exception):
    pass


def _snake_to_camel(name: str) -> str:
    parts = name.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


def _camelise(obj: object) -> object:
    """Recursively convert dict keys from snake_case to camelCase."""
    if isinstance(obj, dict):
        return {_snake_to_camel(k): _camelise(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_camelise(item) for item in obj]
    return obj


class DSLRenderService:
    """Render a VideoSpec JSON into an MP4 using the Remotion DSLRender composition."""

    def __init__(self, renderer_dir: Path | None = None):
        self.renderer = (renderer_dir or Path(RENDERER_DIR)).resolve()
        self.remotion_bin = self.renderer / "node_modules" / ".bin" / "remotion.cmd"
        if not self.remotion_bin.exists():
            alt = self.renderer / "node_modules" / ".bin" / "remotion"
            if alt.exists():
                self.remotion_bin = alt
            else:
                raise DSLRenderError(
                    f"Remotion CLI not found at {self.remotion_bin}. Run npm install."
                )

    def render(
        self,
        video_spec_dict: dict,
        output_path: str | Path,
        artifact_manifest: dict | None = None,
        scene_audio: list[dict] | None = None,
        timeout_seconds: int = 300,
    ) -> Path:
        """Render a VideoSpec dict to an MP4 file.

        Parameters
        ----------
        video_spec_dict : dict
            Serialised VideoSpec (JSON-compatible dict).
        output_path : path
            Where to write the final .mp4.
        artifact_manifest : dict, optional
            {"artifacts": [...]} — images to copy into Remotion public/.
        scene_audio : list[dict], optional
            [{"scene_id": ..., "audio_path": ..., "duration_seconds": ...}]
        timeout_seconds : int
            Max time for the Remotion render process.
        """
        output = Path(output_path).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)

        public_dir = self.renderer / "public"
        copied_dirs: list[Path] = []

        try:
            # Copy artifact images to Remotion public/artifacts/
            if artifact_manifest and artifact_manifest.get("artifacts"):
                artifacts_pub = public_dir / "artifacts"
                artifacts_pub.mkdir(parents=True, exist_ok=True)
                copied_dirs.append(artifacts_pub)
                artifacts_src = output.parent.parent / "05b_artifacts"
                for entry in artifact_manifest["artifacts"]:
                    src = artifacts_src / f"{entry['artifactId']}.png"
                    if src.exists():
                        shutil.copy2(src, artifacts_pub / src.name)

            # Copy audio files to Remotion public/audio/
            audio_map: dict[str, str] = {}
            if scene_audio:
                audio_pub = public_dir / "audio"
                audio_pub.mkdir(parents=True, exist_ok=True)
                copied_dirs.append(audio_pub)
                for item in scene_audio:
                    src = Path(item["audio_path"])
                    if src.exists():
                        shutil.copy2(src, audio_pub / src.name)
                        audio_map[item["scene_id"]] = f"audio/{src.name}"

            # Build Remotion props
            props_payload = {
                "videoSpec": _camelise(video_spec_dict),
            }
            if artifact_manifest and artifact_manifest.get("artifacts"):
                props_payload["artifacts"] = artifact_manifest
            if audio_map:
                props_payload["sceneAudio"] = audio_map

            props_file = output.parent / "render_props.json"
            props_file.write_text(
                json.dumps(props_payload, ensure_ascii=False),
                encoding="utf-8",
            )

            import os
            concurrency = os.getenv("REMOTION_CONCURRENCY", str(os.cpu_count() or 4))
            command = [
                str(self.remotion_bin),
                "render",
                "src/index.ts",
                "DSLRender",
                str(output),
                "--props",
                str(props_file),
                "--codec",
                "h264",
                "--pixel-format",
                "yuv420p",
                "--log",
                "warn",
                "--concurrency",
                concurrency,
                "--enforce-audio-track",
            ]

            logger.info("Rendering DSL video → %s", output)

            completed = subprocess.run(
                command,
                cwd=str(self.renderer),
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )

            if completed.returncode != 0:
                detail = (completed.stderr or completed.stdout or "unknown error")[:2000]
                raise DSLRenderError(
                    f"Remotion render failed (exit {completed.returncode}): {detail}"
                )

            if not output.exists() or output.stat().st_size == 0:
                raise DSLRenderError("Render completed but output file is missing or empty.")

            logger.info("Render complete: %s (%.1f MB)", output, output.stat().st_size / 1_048_576)
            return output

        finally:
            # Clean up copied public/ directories
            for d in copied_dirs:
                shutil.rmtree(d, ignore_errors=True)
