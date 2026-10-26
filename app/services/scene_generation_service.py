"""Scene DSL generation — single LLM call to produce a VideoSpec from dossier data."""

from __future__ import annotations

import json
from pathlib import Path

from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import PROMPTS_DIR, settings
from app.schemas.scene_dsl import VideoSpec
from app.utils.json_utils import save_json
from app.utils.logging import get_logger

logger = get_logger(__name__)


class SceneGenerationError(Exception):
    pass


class SceneGenerationService:
    """Generate a DSL VideoSpec from extracted dossier / video content."""

    def __init__(self, api_key=None, model=None):
        self.api_key = api_key or settings.openai_api_key
        self.model = model or settings.openai_model
        if not self.api_key:
            raise SceneGenerationError("OPENAI_API_KEY is not configured.")
        self.client = OpenAI(api_key=self.api_key)

    def generate_scenes(
        self,
        video_content: dict,
        dossier: dict | None = None,
        output_directory: str | Path | None = None,
        headshot_available: bool = False,
    ) -> VideoSpec:
        """Generate a validated VideoSpec via structured output.

        Parameters
        ----------
        video_content : dict
            Serialised VideoContent (selected highlights, milestones, etc.).
        dossier : dict, optional
            Full serialised Dossier for richer context. If not supplied, the
            LLM works from video_content alone.
        output_directory : path, optional
            When provided, the raw and validated JSON are persisted for debugging.
        """
        prompt_path = PROMPTS_DIR / "scene_dsl_generation.txt"
        if not prompt_path.exists():
            raise FileNotFoundError(f"Scene DSL prompt not found: {prompt_path}")

        instructions = prompt_path.read_text(encoding="utf-8-sig").strip()

        payload: dict = {"video_content": video_content}
        if dossier:
            payload["dossier"] = dossier
        if headshot_available:
            payload["headshot_available"] = True

        logger.info("Generating DSL scenes using %s …", self.model)

        response = self._call_llm(instructions, payload)
        video_spec = response.output_parsed

        if video_spec is None:
            raise SceneGenerationError("OpenAI returned no parsed VideoSpec.")

        if not isinstance(video_spec, VideoSpec):
            video_spec = VideoSpec.model_validate(video_spec)

        if output_directory:
            out = Path(output_directory).expanduser().resolve()
            out.mkdir(parents=True, exist_ok=True)
            save_json(
                video_spec.model_dump(mode="json", by_alias=True),
                out / "video_spec.json",
            )
            self._save_metadata(response, out / "scene_generation_metadata.json")

        logger.info(
            "Generated %d scenes for %s (%.0fs total).",
            len(video_spec.scenes),
            video_spec.candidate_name,
            sum(s.duration_seconds for s in video_spec.scenes),
        )
        return video_spec

    @retry(
        wait=wait_exponential(multiplier=2, min=2, max=20),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def _call_llm(self, instructions, payload):
        user_text = json.dumps(payload, ensure_ascii=False)
        return self.client.responses.parse(
            model=self.model,
            instructions=instructions,
            input=[
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": user_text}],
                }
            ],
            text_format=VideoSpec,
        )

    def _save_metadata(self, response, output_path):
        usage = getattr(response, "usage", None)
        if hasattr(usage, "model_dump"):
            usage_data = usage.model_dump(mode="json", warnings=False)
        else:
            usage_data = None

        save_json(
            {
                "provider": "openai",
                "operation": "scene_dsl_generation",
                "model": self.model,
                "response_id": getattr(response, "id", None),
                "usage": usage_data,
            },
            output_path,
        )
