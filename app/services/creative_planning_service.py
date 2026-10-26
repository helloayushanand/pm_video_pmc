"""OpenAI service for creative direction and scene architecture."""

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
    APP_DIR,
    PROMPTS_DIR,
    settings,
)
from app.schemas.creative_plan import (
    CohesionReview,
    CreativePlan,
    CreativePlanDraft,
)
from app.utils.json_utils import save_json
from app.utils.logging import get_logger


logger = get_logger(__name__)


class CreativePlanningError(Exception):
    """Base exception for creative-planning failures."""


class CreativePlanningConfigurationError(
    CreativePlanningError
):
    """Raised when creative-planning configuration is invalid."""


class CreativePlanningService:
    """Generate and review candidate-specific creative plans."""

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
            raise CreativePlanningConfigurationError(
                "OPENAI_API_KEY is not configured."
            )

        if not self.model:
            raise CreativePlanningConfigurationError(
                "OPENAI_MODEL is not configured."
            )

        self.client = OpenAI(
            api_key=self.api_key
        )

    def generate_plan(
        self,
        video_content,
        storyboard,
        output_directory,
    ):
        """Generate the creative plan and cohesion review."""

        output_path = Path(
            output_directory
        ).expanduser().resolve()

        output_path.mkdir(
            parents=True,
            exist_ok=True,
        )

        generation_prompt_path = (
            PROMPTS_DIR
            / "creative_plan_generation.txt"
        )

        review_prompt_path = (
            PROMPTS_DIR
            / "creative_plan_cohesion_review.txt"
        )

        if not generation_prompt_path.exists():
            raise FileNotFoundError(
                "Creative-plan prompt not found: "
                f"{generation_prompt_path}"
            )

        if not review_prompt_path.exists():
            raise FileNotFoundError(
                "Cohesion-review prompt not found: "
                f"{review_prompt_path}"
            )

        generation_prompt = (
            generation_prompt_path
            .read_text(
                encoding="utf-8-sig"
            )
            .strip()
        )

        review_prompt = (
            review_prompt_path
            .read_text(
                encoding="utf-8-sig"
            )
            .strip()
        )

        primitive_names = [
            "SceneFrame",
            "SafeArea",
            "Stack",
            "SplitLayout",
            "AsymmetricGrid",
            "EditorialColumn",
            "OverflowBoundary",
            "SectionLabel",
            "DisplayTitle",
            "BodyCopy",
            "AutoFitText",
            "MetricValue",
            "MetricCard",
            "ApprovedAsset",
            "PortraitFrame",
            "FadeReveal",
            "SlideReveal",
            "MaskReveal",
            "StaggerGroup",
            "ConfidentialityLabel",
        ]

        request_payload = {
            "video_content": video_content,
            "storyboard": storyboard,
            "dynamic_scene_sdk": {
                "approved_primitives": primitive_names,
                "generated_code_target": (
                    "React and Remotion TSX"
                ),
                "custom_components_enabled": True,
            },
        }

        save_json(
            {
                "provider": "openai",
                "operation": (
                    "creative_plan_generation"
                ),
                "model": self.model,
                "primitive_count": len(
                    primitive_names
                ),
            },
            output_path
            / "creative_plan_request.json",
        )

        logger.info(
            "Generating creative direction and "
            "scene architecture using %s.",
            self.model,
        )

        try:
            draft_response = self._parse_response(
                instructions=generation_prompt,
                input_payload=request_payload,
                output_model=CreativePlanDraft,
            )

        except Exception as error:
            raise CreativePlanningError(
                "Creative-plan generation failed: "
                f"{error}"
            ) from error

        draft = draft_response.output_parsed

        if draft is None:
            raise CreativePlanningError(
                "OpenAI returned no parsed "
                "CreativePlanDraft."
            )

        if not isinstance(
            draft,
            CreativePlanDraft,
        ):
            draft = (
                CreativePlanDraft
                .model_validate(draft)
            )

        save_json(
            draft.model_dump(
                mode="json"
            ),
            output_path
            / "creative_plan_draft.json",
        )

        self._save_response_metadata(
            response=draft_response,
            operation=(
                "creative_plan_generation"
            ),
            output_path=(
                output_path
                / "creative_plan_metadata.json"
            ),
        )

        review_payload = {
            "creative_plan_draft": (
                draft.model_dump(
                    mode="json"
                )
            )
        }

        logger.info(
            "Reviewing cross-scene visual cohesion."
        )

        try:
            review_response = self._parse_response(
                instructions=review_prompt,
                input_payload=review_payload,
                output_model=CohesionReview,
            )

        except Exception as error:
            raise CreativePlanningError(
                "Creative-plan cohesion review failed: "
                f"{error}"
            ) from error

        review = review_response.output_parsed

        if review is None:
            raise CreativePlanningError(
                "OpenAI returned no parsed "
                "CohesionReview."
            )

        if not isinstance(
            review,
            CohesionReview,
        ):
            review = (
                CohesionReview
                .model_validate(review)
            )

        save_json(
            review.model_dump(
                mode="json"
            ),
            output_path
            / "cohesion_review.json",
        )

        self._save_response_metadata(
            response=review_response,
            operation=(
                "creative_plan_cohesion_review"
            ),
            output_path=(
                output_path
                / "cohesion_review_metadata.json"
            ),
        )

        final_plan = CreativePlan(
            draft=draft,
            cohesion_review=review,
        )

        final_path = (
            output_path
            / "creative_plan.json"
        )

        save_json(
            final_plan.model_dump(
                mode="json"
            ),
            final_path,
        )

        preview_path = (
            output_path
            / "creative_plan_preview.md"
        )

        preview_path.write_text(
            self._build_markdown_preview(
                final_plan
            ),
            encoding="utf-8",
        )

        return final_plan

    @retry(
        wait=wait_exponential(
            multiplier=2,
            min=2,
            max=20,
        ),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def _parse_response(
        self,
        instructions,
        input_payload,
        output_model,
    ):
        """Call OpenAI with a strict Pydantic output model."""

        user_text = json.dumps(
            input_payload,
            ensure_ascii=False,
        )

        return self.client.responses.parse(
            model=self.model,
            instructions=instructions,
            input=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": user_text,
                        }
                    ],
                }
            ],
            text_format=output_model,
        )

    def _save_response_metadata(
        self,
        response,
        operation,
        output_path,
    ):
        """Save call metadata and usage without SDK internals."""

        usage = getattr(
            response,
            "usage",
            None,
        )

        if hasattr(
            usage,
            "model_dump",
        ):
            usage_data = usage.model_dump(
                mode="json",
                warnings=False,
            )
        else:
            usage_data = None

        metadata = {
            "provider": "openai",
            "operation": operation,
            "model": self.model,
            "response_id": getattr(
                response,
                "id",
                None,
            ),
            "status": getattr(
                response,
                "status",
                "completed",
            ),
            "usage": usage_data,
        }

        save_json(
            metadata,
            output_path,
        )

    @staticmethod
    def _build_markdown_preview(
        plan,
    ):
        """Create a human-readable creative-plan preview."""

        draft = plan.draft
        direction = draft.creative_direction
        review = plan.cohesion_review

        lines = [
            "# Creative Plan",
            "",
            f"Candidate: {draft.candidate_name}",
            "",
            f"Video title: {draft.video_title}",
            "",
            "## Narrative",
            "",
            f"Thesis: {draft.narrative_thesis}",
            "",
            f"Opening hook: {draft.opening_hook}",
            "",
            f"Closing message: {draft.closing_message}",
            "",
            "## Creative Direction",
            "",
            (
                "Creative concept: "
                f"{direction.creative_concept}"
            ),
            "",
            (
                "Visual tone: "
                f"{direction.visual_tone.value}"
            ),
            "",
            (
                "Motion character: "
                f"{direction.motion_character.value}"
            ),
            "",
            (
                "Palette: "
                f"{direction.palette_variant}"
            ),
            "",
            (
                "Typography: "
                f"{direction.typography_variant}"
            ),
            "",
            (
                "Creative rationale: "
                f"{direction.creative_rationale}"
            ),
            "",
            "## Scene Architecture",
            "",
        ]

        for scene in draft.scene_briefs:
            lines.extend(
                [
                    (
                        "### "
                        f"{scene.scene_id}: "
                        f"{scene.component_name_suggestion}"
                    ),
                    "",
                    (
                        "Strategy: "
                        f"{scene.component_strategy.value}"
                    ),
                    "",
                    (
                        "Purpose: "
                        f"{scene.scene_purpose}"
                    ),
                    "",
                    (
                        "Visual story: "
                        f"{scene.visual_story}"
                    ),
                    "",
                    (
                        "Layout: "
                        f"{scene.layout_intent}"
                    ),
                    "",
                    (
                        "Focal element: "
                        f"{scene.focal_element}"
                    ),
                    "",
                    (
                        "Animation: "
                        f"{scene.animation_intent}"
                    ),
                    "",
                    (
                        "Fallback: "
                        f"{scene.fallback_component}"
                    ),
                    "",
                    (
                        "Artifacts: "
                        f"{len(scene.artifact_requirements)}"
                    ),
                    "",
                ]
            )

        lines.extend(
            [
                "## Cohesion Review",
                "",
                (
                    "Approved: "
                    f"{review.approved}"
                ),
                "",
                (
                    "Overall score: "
                    f"{review.overall_cohesion_score:.2f}"
                ),
                "",
                (
                    "Design consistency: "
                    f"{review.design_consistency_score:.2f}"
                ),
                "",
                (
                    "Scene variety: "
                    f"{review.scene_variety_score:.2f}"
                ),
                "",
                (
                    "Narrative alignment: "
                    f"{review.narrative_visual_alignment_score:.2f}"
                ),
                "",
                (
                    "Brand consistency: "
                    f"{review.brand_consistency_score:.2f}"
                ),
                "",
                review.summary,
                "",
            ]
        )

        if review.required_changes:
            lines.extend(
                [
                    "## Required Changes",
                    "",
                ]
            )

            for change in review.required_changes:
                lines.append(
                    f"- {change}"
                )

        return "\n".join(lines)
