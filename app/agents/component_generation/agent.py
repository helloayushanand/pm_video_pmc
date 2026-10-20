"""OpenAI-backed component generator and source-repair agents."""

from __future__ import annotations

import json
import re
from pathlib import Path

from openai import OpenAI
from openai.types.responses import ResponseInputParam
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
)

from app.config import (
    PROMPTS_DIR,
    RENDERER_DIR,
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
            api_key=self.api_key,
            max_retries=0,
        )

        self.sdk_contract = (
            self._read_prompt(
                "component_sdk_contract.txt"
            )
        )
        self.sdk_public_api = self._read_sdk_public_api()

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
    def _extract_type_alias(source, name):
        match = re.search(
            rf"\btype\s+{re.escape(name)}\s*=",
            source,
        )
        if match is None:
            raise ComponentAgentError(
                f"Dynamic SDK prop type {name} is missing."
            )

        start = match.start()
        index = match.end()
        brace_depth = 0
        bracket_depth = 0
        paren_depth = 0
        quote = None
        escaped = False
        while index < len(source):
            character = source[index]
            if quote:
                if escaped:
                    escaped = False
                elif character == "\\":
                    escaped = True
                elif character == quote:
                    quote = None
            elif character in {"'", '"', "`"}:
                quote = character
            elif character == "{":
                brace_depth += 1
            elif character == "}":
                brace_depth -= 1
            elif character == "[":
                bracket_depth += 1
            elif character == "]":
                bracket_depth -= 1
            elif character == "(":
                paren_depth += 1
            elif character == ")":
                paren_depth -= 1
            elif (
                character == ";"
                and brace_depth == 0
                and bracket_depth == 0
                and paren_depth == 0
            ):
                return source[start:index + 1].strip()
            index += 1

        raise ComponentAgentError(
            f"Dynamic SDK prop type {name} is not terminated."
        )

    @classmethod
    def _read_sdk_public_api(cls):
        sdk_dir = (
            Path(RENDERER_DIR)
            / "src"
            / "dynamic-sdk"
        )
        primitives_path = sdk_dir / "primitives.tsx"
        types_path = sdk_dir / "types.ts"
        if not primitives_path.exists() or not types_path.exists():
            raise FileNotFoundError(
                "Dynamic SDK TypeScript sources are required to build "
                "the component-generation contract."
            )

        primitives_source = primitives_path.read_text(
            encoding="utf-8-sig"
        )
        types_source = types_path.read_text(
            encoding="utf-8-sig"
        )
        exported_components = re.findall(
            r"export\s+const\s+(\w+)\s*:\s*React\.FC<(\w+)>",
            primitives_source,
        )
        if not exported_components:
            raise ComponentAgentError(
                "No exported Dynamic SDK component signatures were found."
            )

        props = []
        seen_types = set()
        for component_name, props_type in exported_components:
            if props_type not in seen_types:
                props.append(
                    cls._extract_type_alias(
                        primitives_source,
                        props_type,
                    )
                )
                seen_types.add(props_type)
        return (
            "These signatures are extracted from the renderer's current "
            "TypeScript source. They are authoritative; when a prose "
            "instruction or older example differs, follow these declarations.\n\n"
            "Exported component-to-props mapping:\n"
            + "\n".join(
                f"- {component_name}: {props_type}"
                for component_name, props_type in exported_components
            )
            + "\n\nExact prop type declarations:\n"
            + "\n".join(props)
            + "\n\nSupporting Dynamic SDK types:\n"
            + types_source
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
            + "\n\n"
            + "=" * 72
            + "\n"
            + "SOURCE-DERIVED DYNAMIC SDK PUBLIC API\n"
            + "=" * 72
            + "\n\n"
            + self.sdk_public_api
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
        visual_frames=None,
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

        repair_input: str | ResponseInputParam = json.dumps(
            payload,
            ensure_ascii=False,
        )
        if visual_frames:
            content: list[dict[str, str]] = [
                {
                    "type": "input_text",
                    "text": repair_input,
                }
            ]
            for frame in visual_frames:
                content.append(
                    {
                        "type": "input_text",
                        "text": (
                            f"Rendered preview frame: {frame['label']}, "
                            f"frame {frame['frame']}."
                        ),
                    }
                )
                content.append(
                    {
                        "type": "input_image",
                        "image_url": frame["image_url"],
                    }
                )
            repair_input = [
                {
                    "role": "user",
                    "content": content,
                }
            ]

        response = (
            self.client
            .responses
            .parse(
                model=self.model,

                instructions=
                    self.repair_prompt,

                input=repair_input,

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