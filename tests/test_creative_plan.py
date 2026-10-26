"""Tests for Phase 2 creative-planning schemas."""

import pytest
from pydantic import ValidationError

from app.schemas.creative_plan import (
    CohesionReview,
    ComponentStrategy,
    CreativeDirection,
    CreativePlanDraft,
    SceneArchitectureBrief,
)


def create_direction():
    return CreativeDirection(
        creative_concept=(
            "Transformation through scale"
        ),
        palette_variant=(
            "warm_charcoal_gold"
        ),
        typography_variant=(
            "editorial_sans"
        ),
        transition_family=(
            "soft_mask"
        ),
        image_treatment=(
            "editorial_crop"
        ),
        metric_treatment=(
            "large_typographic"
        ),
        chart_treatment=(
            "minimal_flat"
        ),
        background_treatment=(
            "warm_gradient"
        ),
        creative_rationale=(
            "The candidate story is best expressed "
            "through scale, transformation, and "
            "measured editorial pacing."
        ),
        confidentiality_treatment=(
            "Persistent upper-right label."
        ),
    )


def create_scene(scene_id):
    return SceneArchitectureBrief(
        scene_id=scene_id,
        scene_type=(
            "quantified_highlights"
        ),
        scene_purpose=(
            "Show commercial impact."
        ),
        component_strategy=(
            ComponentStrategy
            .GENERATED_COMPONENT
        ),
        component_name_suggestion=(
            "CommercialImpactScene"
        ),
        fallback_component=(
            "MetricHighlights"
        ),
        visual_story=(
            "A dominant metric anchors "
            "supporting evidence."
        ),
        layout_intent=(
            "Asymmetric editorial layout."
        ),
        visual_hierarchy=[
            "Headline",
            "Hero metric",
            "Supporting metrics",
        ],
        focal_element="Hero metric",
        content_density="medium",
        animation_intent=(
            "Progressive measured reveal."
        ),
        transition_in="soft_mask",
        transition_out="fade",
        background_treatment=(
            "Warm gradient."
        ),
        typography_treatment=(
            "Large editorial typography."
        ),
        color_emphasis=(
            "Gold hero metric."
        ),
    )


def test_creative_plan_draft_is_valid():
    draft = CreativePlanDraft(
        candidate_name="Test Candidate",
        video_title="Candidate Snapshot",
        narrative_thesis=(
            "A transformation-focused leader."
        ),
        opening_hook=(
            "A career built on measurable impact."
        ),
        closing_message=(
            "Full dossier shared separately."
        ),
        creative_direction=(
            create_direction()
        ),
        scene_briefs=[
            create_scene("scene_01")
        ],
    )

    assert len(draft.scene_briefs) == 1


def test_duplicate_scene_ids_are_rejected():
    with pytest.raises(ValidationError):
        CreativePlanDraft(
            candidate_name="Test Candidate",
            video_title="Candidate Snapshot",
            narrative_thesis="Thesis",
            opening_hook="Hook",
            closing_message="Closing",
            creative_direction=(
                create_direction()
            ),
            scene_briefs=[
                create_scene("scene_01"),
                create_scene("scene_01"),
            ],
        )


def test_cohesion_review_score_range():
    with pytest.raises(ValidationError):
        CohesionReview(
            approved=True,
            overall_cohesion_score=1.2,
            design_consistency_score=0.9,
            scene_variety_score=0.8,
            narrative_visual_alignment_score=0.9,
            brand_consistency_score=0.9,
            summary="Invalid score.",
        )
