"""OpenAI-backed component generator and source-repair agents."""

from __future__ import annotations

import json
from pathlib import Path

from openai import OpenAI
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
)

from app.config import (
    PROMPTS_DIR,
    settings,
)
from app.schemas.generated_component import (
    GeneratedComponentOutput,
    SceneGenerationInput,
)


class ComponentAgentError(Exception):
    """Raised when a component-generation agent call fails."""


class ComponentGenerationAgent:
    """
    Generate and repair bounded TSX scene components.

    Generation and repair share one canonical Dynamic SDK
    contract loaded from component_sdk_contract.txt.
    """

    def __init__(
        self,
        api_key=None,
        model=None,
    ):
        self.api_key = (
            api_key
            or settings.openai_api_key
        )

        self.model = (
            model
            or settings.openai_model
        )

        if not self.api_key:
            raise ComponentAgentError(
                "OPENAI_API_KEY is not configured."
            )

        self.client = OpenAI(
            api_key=self.api_key
        )

        self.sdk_contract = (
            self._read_prompt(
                "component_sdk_contract.txt"
            )
        )

        generation_base = (
            self._read_prompt(
                "component_generation.txt"
            )
        )

        repair_base = (
            self._read_prompt(
                "component_source_repair.txt"
            )
        )

        self.generation_prompt = (
            self._compose_instructions(
                generation_base
            )
        )

        self.repair_prompt = (
            self._compose_instructions(
                repair_base
            )
        )

    @staticmethod
    def _read_prompt(
        filename,
    ):
        path = (
            Path(PROMPTS_DIR)
            / filename
        )

        if not path.exists():
            raise FileNotFoundError(
                f"Prompt not found: {path}"
            )

        return path.read_text(
            encoding="utf-8-sig"
        ).strip()

    def _compose_instructions(
        self,
        task_prompt,
    ):
        """
        Combine task-specific instructions with the canonical
        generated-component SDK contract.

        The same contract is supplied to generation and repair.
        """

        return (
            task_prompt.strip()
            + "\n\n"
            + "=" * 72
            + "\n"
            + "CANONICAL SDK CONTRACT\n"
            + "=" * 72
            + "\n\n"
            + self.sdk_contract.strip()
        )

    @retry(
        wait=wait_exponential(
            multiplier=2,
            min=2,
            max=20,
        ),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def generate(
        self,
        scene_input: SceneGenerationInput,
    ):
        payload = {
            "task":
                "generate_component",

            "scene_package":
                scene_input.model_dump(
                    mode="json"
                ),
        }

        response = (
            self.client
            .responses
            .parse(
                model=self.model,

                instructions=
                    self.generation_prompt,

                input=json.dumps(
                    payload,
                    ensure_ascii=False,
                ),

                text_format=
                    GeneratedComponentOutput,
            )
        )

        parsed = (
            response.output_parsed
        )

        if parsed is None:
            raise ComponentAgentError(
                "No parsed component output "
                "was returned."
            )

        if not isinstance(
            parsed,
            GeneratedComponentOutput,
        ):
            parsed = (
                GeneratedComponentOutput
                .model_validate(
                    parsed
                )
            )

        return (
            parsed,
            self._metadata(
                response,
                "component_generation",
            ),
        )

    @retry(
        wait=wait_exponential(
            multiplier=2,
            min=2,
            max=20,
        ),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def repair(
        self,
        scene_input,
        generated_component,
        validation,
    ):
        payload = {
            "task":
                "repair_component_source",

            "scene_package":
                scene_input.model_dump(
                    mode="json"
                ),

            "current_component":
                generated_component.model_dump(
                    mode="json"
                ),

            "validation":
                validation.model_dump(
                    mode="json"
                ),
        }

        response = (
            self.client
            .responses
            .parse(
                model=self.model,

                instructions=
                    self.repair_prompt,

                input=json.dumps(
                    payload,
                    ensure_ascii=False,
                ),

                text_format=
                    GeneratedComponentOutput,
            )
        )

        parsed = (
            response.output_parsed
        )

        if parsed is None:
            raise ComponentAgentError(
                "No parsed repaired component "
                "was returned."
            )

        if not isinstance(
            parsed,
            GeneratedComponentOutput,
        ):
            parsed = (
                GeneratedComponentOutput
                .model_validate(
                    parsed
                )
            )

        return (
            parsed,
            self._metadata(
                response,
                "component_source_repair",
            ),
        )

    def _metadata(
        self,
        response,
        operation,
    ):
        usage = getattr(
            response,
            "usage",
            None,
        )

        if hasattr(
            usage,
            "model_dump",
        ):
            usage = usage.model_dump(
                mode="json",
                warnings=False,
            )

        return {
            "provider":
                "openai",

            "operation":
                operation,

            "model":
                self.model,

            "response_id":
                getattr(
                    response,
                    "id",
                    None,
                ),

            "status":
                getattr(
                    response,
                    "status",
                    "completed",
                ),

            "usage":
                usage,

            "sdk_contract":
                "component_sdk_contract_v1",
        }