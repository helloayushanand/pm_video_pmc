"""Python wrapper for the local Remotion video renderer."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from app.config import RENDERER_DIR
from app.utils.json_utils import load_json
from app.utils.logging import get_logger


logger = get_logger(__name__)


class RenderServiceError(Exception):
    """Base exception for rendering failures."""


class RenderConfigurationError(RenderServiceError):
    """Raised when the local rendering environment is incomplete."""


class RemotionRenderService:
    """Render candidate videos using the local Remotion project."""

    def __init__(
        self,
        renderer_directory=None,
        composition_id="CandidateVideo",
        entry_point="src/index.ts",
        timeout_seconds=1800,
    ):
        """
        Initialise the local Remotion renderer.

        Args:
            renderer_directory:
                Path to the local Remotion project.

            composition_id:
                Remotion composition to render.

            entry_point:
                Remotion project entry point.

            timeout_seconds:
                Maximum time allowed for one render.
        """

        self.renderer_directory = Path(
            renderer_directory or RENDERER_DIR
        ).expanduser().resolve()

        self.composition_id = composition_id
        self.entry_point = entry_point
        self.timeout_seconds = timeout_seconds

    def validate_environment(self):
        """Return configuration issues preventing local rendering."""

        errors = []

        node_executable = shutil.which("node")

        npm_executable = (
            shutil.which("npm.cmd")
            or shutil.which("npm")
        )

        npx_executable = (
            shutil.which("npx.cmd")
            or shutil.which("npx")
        )

        if node_executable is None:
            errors.append(
                "Node.js is not available in PATH."
            )

        if npm_executable is None:
            errors.append(
                "npm is not available in PATH."
            )

        if npx_executable is None:
            errors.append(
                "npx is not available in PATH."
            )

        if not self.renderer_directory.exists():
            errors.append(
                "Remotion project directory was not found: "
                f"{self.renderer_directory}"
            )

            return errors

        package_json_path = (
            self.renderer_directory
            / "package.json"
        )

        if not package_json_path.exists():
            errors.append(
                "Remotion package.json was not found: "
                f"{package_json_path}"
            )

        entry_point_path = (
            self.renderer_directory
            / self.entry_point
        )

        if not entry_point_path.exists():
            errors.append(
                "Remotion entry point was not found: "
                f"{entry_point_path}"
            )

        node_modules_directory = (
            self.renderer_directory
            / "node_modules"
        )

        if not node_modules_directory.exists():
            errors.append(
                "Remotion dependencies are not installed. "
                "Run npm install inside the renderer directory."
            )

        remotion_cli_directory = (
            node_modules_directory
            / "@remotion"
            / "cli"
        )

        if (
            node_modules_directory.exists()
            and not remotion_cli_directory.exists()
        ):
            errors.append(
                "The @remotion/cli package was not found. "
                "Run npm install inside the renderer directory."
            )

        return errors

    def render(
        self,
        render_spec_path,
        output_path,
    ):
        """
        Render an MP4 using a local render specification.

        The method:

        1. Validates Node.js and Remotion
        2. Loads the render specification
        3. Copies narration into Remotion public assets
        4. Creates a temporary Remotion props file
        5. Runs the Remotion CLI
        6. Saves stdout and stderr in render_log.txt
        7. Verifies that an MP4 was created
        """

        validation_errors = (
            self.validate_environment()
        )

        if validation_errors:
            raise RenderConfigurationError(
                " ".join(validation_errors)
            )

        specification_path = Path(
            render_spec_path
        ).expanduser().resolve()

        destination = Path(
            output_path
        ).expanduser().resolve()

        if not specification_path.exists():
            raise FileNotFoundError(
                "Render specification was not found: "
                f"{specification_path}"
            )

        if not specification_path.is_file():
            raise RenderServiceError(
                "Render specification path is not a file: "
                f"{specification_path}"
            )

        render_spec = load_json(
            specification_path
        )

        self._validate_render_spec(
            render_spec
        )

        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        renderer_audio_path = (
            self._prepare_audio_asset(
                render_spec
            )
        )

        render_spec["audio"]["source_path"] = (
            "generated/voiceover.mp3"
        )

        props_path = (
            self.renderer_directory
            / "render-props.json"
        )

        props_payload = {
            "renderSpec": render_spec,
        }

        props_path.write_text(
            json.dumps(
                props_payload,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        render_log_path = (
            destination.parent
            / "render_log.txt"
        )

        npx_executable = (
            shutil.which("npx.cmd")
            or shutil.which("npx")
        )

        if npx_executable is None:
            raise RenderConfigurationError(
                "npx is not available in PATH."
            )

        command = [
            npx_executable,
            "remotion",
            "render",
            self.entry_point,
            self.composition_id,
            str(destination),
            "--props",
            str(props_path),
            "--codec",
            "h264",
            "--pixel-format",
            "yuv420p",
            "--overwrite",
        ]

        logger.info(
            "Starting Remotion render."
        )

        logger.info(
            "Composition: %s",
            self.composition_id,
        )

        logger.info(
            "Render destination: %s",
            destination,
        )

        logger.info(
            "Render specification: %s",
            specification_path,
        )

        logger.info(
            "Renderer narration asset: %s",
            renderer_audio_path,
        )

        try:
            completed = subprocess.run(
                command,
                cwd=self.renderer_directory,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
                shell=False,
                env=os.environ.copy(),
            )

        except subprocess.TimeoutExpired as error:
            render_log_path.write_text(
                (
                    "RENDER TIMEOUT\n\n"
                    f"Command: {self._format_command(command)}\n"
                    f"Timeout: {self.timeout_seconds} seconds\n"
                ),
                encoding="utf-8",
            )

            raise RenderServiceError(
                "Remotion rendering exceeded the configured "
                f"timeout of {self.timeout_seconds} seconds. "
                f"Review {render_log_path}."
            ) from error

        except Exception as error:
            render_log_path.write_text(
                (
                    "RENDER PROCESS ERROR\n\n"
                    f"Command: {self._format_command(command)}\n"
                    f"Error: {type(error).__name__}: {error}\n"
                ),
                encoding="utf-8",
            )

            raise RenderServiceError(
                "Unable to start the Remotion renderer. "
                f"Review {render_log_path}."
            ) from error

        render_log_path.write_text(
            (
                "COMMAND\n"
                f"{self._format_command(command)}\n\n"
                "WORKING DIRECTORY\n"
                f"{self.renderer_directory}\n\n"
                "RETURN CODE\n"
                f"{completed.returncode}\n\n"
                "STANDARD OUTPUT\n"
                f"{completed.stdout}\n\n"
                "STANDARD ERROR\n"
                f"{completed.stderr}\n"
            ),
            encoding="utf-8",
        )

        if completed.returncode != 0:
            raise RenderServiceError(
                "Remotion rendering failed with return code "
                f"{completed.returncode}. "
                f"Review the render log: {render_log_path}"
            )

        if not destination.exists():
            raise RenderServiceError(
                "Remotion completed without creating the expected "
                f"MP4 file: {destination}"
            )

        if destination.stat().st_size == 0:
            raise RenderServiceError(
                "The generated MP4 file is empty: "
                f"{destination}"
            )

        logger.info(
            "Remotion render completed successfully."
        )

        logger.info(
            "Rendered video size: %s bytes",
            destination.stat().st_size,
        )

        return {
            "provider": "remotion",
            "render_mode": "local_cli",
            "composition_id": self.composition_id,
            "entry_point": self.entry_point,
            "renderer_directory": str(
                self.renderer_directory
            ),
            "render_specification": str(
                specification_path
            ),
            "props_path": str(
                props_path
            ),
            "audio_asset": str(
                renderer_audio_path
            ),
            "output_path": str(
                destination
            ),
            "file_size_bytes": (
                destination.stat().st_size
            ),
            "render_log": str(
                render_log_path
            ),
            "return_code": (
                completed.returncode
            ),
        }

    def _validate_render_spec(
        self,
        render_spec,
    ):
        """Validate required fields in the render specification."""

        if not isinstance(render_spec, dict):
            raise RenderServiceError(
                "Render specification must be a JSON object."
            )

        required_top_level_fields = [
            "render_id",
            "candidate_name",
            "video",
            "theme",
            "audio",
            "scenes",
        ]

        missing_fields = [
            field
            for field in required_top_level_fields
            if field not in render_spec
        ]

        if missing_fields:
            raise RenderServiceError(
                "Render specification is missing required fields: "
                f"{', '.join(missing_fields)}"
            )

        video_settings = render_spec.get(
            "video",
            {},
        )

        required_video_fields = [
            "width",
            "height",
            "fps",
            "duration_frames",
        ]

        missing_video_fields = [
            field
            for field in required_video_fields
            if field not in video_settings
        ]

        if missing_video_fields:
            raise RenderServiceError(
                "Render video settings are missing fields: "
                f"{', '.join(missing_video_fields)}"
            )

        if video_settings["width"] <= 0:
            raise RenderServiceError(
                "Render width must be greater than zero."
            )

        if video_settings["height"] <= 0:
            raise RenderServiceError(
                "Render height must be greater than zero."
            )

        if video_settings["fps"] <= 0:
            raise RenderServiceError(
                "Render FPS must be greater than zero."
            )

        if video_settings["duration_frames"] <= 0:
            raise RenderServiceError(
                "Render duration must be greater than zero."
            )

        scenes = render_spec.get(
            "scenes",
            [],
        )

        if not isinstance(scenes, list):
            raise RenderServiceError(
                "Render scenes must be a list."
            )

        if not scenes:
            raise RenderServiceError(
                "Render specification contains no scenes."
            )

        for index, scene in enumerate(scenes):
            if not isinstance(scene, dict):
                raise RenderServiceError(
                    f"Scene {index} is not a JSON object."
                )

            required_scene_fields = [
                "scene_id",
                "component",
                "start_frame",
                "duration_frames",
                "props",
            ]

            missing_scene_fields = [
                field
                for field in required_scene_fields
                if field not in scene
            ]

            if missing_scene_fields:
                raise RenderServiceError(
                    f"Scene {index} is missing fields: "
                    f"{', '.join(missing_scene_fields)}"
                )

            if scene["start_frame"] < 0:
                raise RenderServiceError(
                    f"Scene {index} has a negative start frame."
                )

            if scene["duration_frames"] <= 0:
                raise RenderServiceError(
                    f"Scene {index} has an invalid duration."
                )

        audio_settings = render_spec.get(
            "audio",
            {},
        )

        if not isinstance(audio_settings, dict):
            raise RenderServiceError(
                "Render audio configuration must be an object."
            )

        if not audio_settings.get("source_path"):
            raise RenderServiceError(
                "Render specification does not contain "
                "an audio source path."
            )

    def _prepare_audio_asset(
        self,
        render_spec,
    ):
        """Copy generated narration into Remotion's public directory."""

        source_value = render_spec["audio"][
            "source_path"
        ]

        audio_source_path = Path(
            source_value
        ).expanduser().resolve()

        if not audio_source_path.exists():
            raise RenderServiceError(
                "Voiceover audio was not found: "
                f"{audio_source_path}"
            )

        if not audio_source_path.is_file():
            raise RenderServiceError(
                "Voiceover audio path is not a file: "
                f"{audio_source_path}"
            )

        if audio_source_path.stat().st_size == 0:
            raise RenderServiceError(
                "Voiceover audio is empty: "
                f"{audio_source_path}"
            )

        generated_assets_directory = (
            self.renderer_directory
            / "public"
            / "generated"
        )

        generated_assets_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        renderer_audio_path = (
            generated_assets_directory
            / "voiceover.mp3"
        )

        shutil.copy2(
            audio_source_path,
            renderer_audio_path,
        )

        if not renderer_audio_path.exists():
            raise RenderServiceError(
                "Failed to copy voiceover audio into "
                "the Remotion public directory."
            )

        return renderer_audio_path

    @staticmethod
    def _format_command(command):
        """Return a readable command string for logs."""

        formatted_parts = []

        for item in command:
            item_text = str(item)

            if " " in item_text:
                formatted_parts.append(
                    f'"{item_text}"'
                )
            else:
                formatted_parts.append(
                    item_text
                )

        return " ".join(
            formatted_parts
        )