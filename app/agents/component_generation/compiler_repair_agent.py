"""OpenAI compiler-repair agent for generated Remotion components."""
from __future__ import annotations
import json
from pathlib import Path
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential
from app.config import PROMPTS_DIR, settings
from app.schemas.generated_component import GeneratedComponentOutput, SceneGenerationInput

class CompilerRepairAgentError(Exception):
    """Raised when compiler repair cannot be generated."""

class CompilerRepairAgent:
    def __init__(self, api_key=None, model=None):
        self.api_key = api_key or settings.openai_api_key
        self.model = model or settings.openai_model
        if not self.api_key:
            raise CompilerRepairAgentError("OPENAI_API_KEY is not configured.")
        self.client = OpenAI(api_key=self.api_key)
        prompt_path = Path(PROMPTS_DIR) / "component_compiler_repair.txt"
        self.prompt = prompt_path.read_text(encoding="utf-8-sig").strip()

    @retry(wait=wait_exponential(multiplier=2, min=2, max=20), stop=stop_after_attempt(3), reraise=True)
    def repair(self, scene_input, current_component, compiler_output, sdk_contract):
        payload = {
            "task": "repair_typescript_compiler_errors",
            "scene_package": scene_input.model_dump(mode="json"),
            "current_component": current_component.model_dump(mode="json"),
            "compiler_output": compiler_output,
            "dynamic_sdk_contract": sdk_contract,
        }
        response = self.client.responses.parse(
            model=self.model,
            instructions=self.prompt,
            input=json.dumps(payload, ensure_ascii=False),
            text_format=GeneratedComponentOutput,
        )
        parsed = response.output_parsed
        if parsed is None:
            raise CompilerRepairAgentError("No parsed compiler repair was returned.")
        if not isinstance(parsed, GeneratedComponentOutput):
            parsed = GeneratedComponentOutput.model_validate(parsed)
        usage = getattr(response, "usage", None)
        if hasattr(usage, "model_dump"):
            usage = usage.model_dump(mode="json", warnings=False)
        metadata = {
            "provider": "openai", "operation": "component_compiler_repair",
            "model": self.model, "response_id": getattr(response, "id", None),
            "status": getattr(response, "status", "completed"), "usage": usage,
        }
        return parsed, metadata
