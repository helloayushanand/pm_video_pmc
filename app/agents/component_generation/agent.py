"""OpenAI-backed component generator and source-repair agents."""

from __future__ import annotations

import json
from pathlib import Path

from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import PROMPTS_DIR, settings
from app.schemas.generated_component import (
    GeneratedComponentOutput,
    SceneGenerationInput,
)


class ComponentAgentError(Exception):
    """Raised when a component-generation agent call fails."""


class ComponentGenerationAgent:
    """Generate and repair bounded TSX scene components."""

    def __init__(self, api_key=None, model=None):
        self.api_key = api_key or settings.openai_api_key
        self.model = model or settings.openai_model
        if not self.api_key:
            raise ComponentAgentError("OPENAI_API_KEY is not configured.")
        self.client = OpenAI(api_key=self.api_key)
        self.generation_prompt = self._read_prompt("component_generation.txt")
        self.repair_prompt = self._read_prompt("component_source_repair.txt")

    @staticmethod
    def _read_prompt(filename):
        path = Path(PROMPTS_DIR) / filename
        if not path.exists():
            raise FileNotFoundError(f"Prompt not found: {path}")
        return path.read_text(encoding="utf-8-sig").strip()

    @retry(
        wait=wait_exponential(multiplier=2, min=2, max=20),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def generate(self, scene_input: SceneGenerationInput):
        payload = {
            "task": "generate_component",
            "scene_package": scene_input.model_dump(mode="json"),
        }
        response = self.client.responses.parse(
            model=self.model,
            instructions=self.generation_prompt,
            input=json.dumps(payload, ensure_ascii=False),
            text_format=GeneratedComponentOutput,
        )
        parsed = response.output_parsed
        if parsed is None:
            raise ComponentAgentError("No parsed component output was returned.")
        if not isinstance(parsed, GeneratedComponentOutput):
            parsed = GeneratedComponentOutput.model_validate(parsed)
        return parsed, self._metadata(response, "component_generation")

    @retry(
        wait=wait_exponential(multiplier=2, min=2, max=20),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def repair(self, scene_input, generated_component, validation):
        payload = {
            "task": "repair_component_source",
            "scene_package": scene_input.model_dump(mode="json"),
            "current_component": generated_component.model_dump(mode="json"),
            "validation": validation.model_dump(mode="json"),
        }
        response = self.client.responses.parse(
            model=self.model,
            instructions=self.repair_prompt,
            input=json.dumps(payload, ensure_ascii=False),
            text_format=GeneratedComponentOutput,
        )
        parsed = response.output_parsed
        if parsed is None:
            raise ComponentAgentError("No parsed repaired component was returned.")
        if not isinstance(parsed, GeneratedComponentOutput):
            parsed = GeneratedComponentOutput.model_validate(parsed)
        return parsed, self._metadata(response, "component_source_repair")

    def _metadata(self, response, operation):
        usage = getattr(response, "usage", None)
        if hasattr(usage, "model_dump"):
            usage = usage.model_dump(mode="json", warnings=False)
        return {
            "provider": "openai",
            "operation": operation,
            "model": self.model,
            "response_id": getattr(response, "id", None),
            "status": getattr(response, "status", "completed"),
            "usage": usage,
        }
