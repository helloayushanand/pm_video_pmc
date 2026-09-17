"""Python wrapper for the local Remotion renderer."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from app.config import RENDERER_DIR
from app.utils.json_utils import load_json
from app.utils.logging import get_logger


logger = get_logger(__name__)


class RenderServiceError(Exception):
    """Base exception for renderer failures."""


class RenderConfigurationError(RenderServiceError):
    """Raised when Node or Remotion is unavailable."""


class RemotionRenderService:
    """Render a candidate video through the local Remotion project."""

    def __init__(
        self,
        renderer_directory=None,
        composition_id="CandidateVideo",
        timeout_seconds=900,
    ):
        self.renderer_directory = Path(
            renderer_directory or RENDERER_DIR
        ).resolve()

        self.composition_id = composition_id
        self.timeout_seconds = timeout_seconds

    def validate_environment(self):
        """Validate local Node and Remotion prerequisites."""

        errors = []

        if shutil.which("node") is None:
            errors.append(
                "Node.js is not available in PATH."
            )

        if shutil.which("npm") is None:
            errors.append(
                "npm is not available in PATH."
            )

        package_json = (
            self.renderer_directory / "package.json"
        )

        if not package_json.exists():
            errors.append(
                f"Remotion package.json not found: {package_json}"
            )

        node_modules = (
            self.renderer_directory / "node_modules"
        )

        if not node_modules.exists():
            errors.append(
                "Remotion dependencies are not installed. "
                "Run npm install inside the renderer directory."
            )

        return errors

    def render(
        self,
        render_spec_path,
        output_path,
    ):
        """Render an MP4 using a local render specification."""

        validation_errors = self.validate_environment()

        if validation_errors:
            raise RenderConfigurationError(
                " ".join(validation_errors)
            )

        specification_path = Path(
            render_spec_path
        ).resolve()

        destination = Path(output_path).resolve()

        if not specification_path.exists():
            raise FileNotFoundError(
                f"Render specification not found: "
                f"{specification_path}"
            )

        render_spec = load_json(specification_path)

        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        temporary_props_path = (
            self.renderer_directory
            / "render-props.json"
        )

        temporary_props_path.write_text(
            json.dumps(
                {
                    "renderSpec": render_spec,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        command = [
            "npx",
            "remotion",
            "render",
            self.composition_id,
            str(destination),
            "--props",
            str(temporary_props_path),
            "--codec",
            "h264",
        ]

        logger.info(
            "Starting Remotion render."
        )

        completed = subprocess.run(
            command,
            cwd=self.renderer_directory,
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
            check=False,
            shell=False,
        )

        render_log_path = (
            destination.parent / "render_log.txt"
        )

        render_log_path.write_text(
            (
                "COMMAND\n"
                f"{' '.join(command)}\n\n"
                "STANDARD OUTPUT\n"
                f"{completed.stdout}\n\n"
                "STANDARD ERROR\n"
                f"{completed.stderr}\n"
            ),
            encoding="utf-8",
        )

        if completed.returncode != 0:
            raise RenderServiceError(
                "Remotion render failed. Review "
                f"{render_log_path}."
            )

        if not destination.exists():
            raise RenderServiceError(
                "Remotion completed without creating the MP4."
            )

        if destination.stat().st_size == 0:
            raise RenderServiceError(
                "The rendered MP4 is empty."
            )

        logger.info(
            "Remotion render completed successfully."
        )

        return {
            "provider": "remotion",
            "composition_id": self.composition_id,
            "output_path": str(destination),
            "file_size_bytes": destination.stat().st_size,
            "render_log": str(render_log_path),
            "return_code": completed.returncode,
        }
