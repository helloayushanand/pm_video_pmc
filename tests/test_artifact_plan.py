"""Tests for artifact-planning schemas."""

import pytest
from pydantic import ValidationError

from app.schemas.artifact_plan import (
    ArtifactPlan,
    ArtifactPlanItem,
    ArtifactStrategy,
    ArtifactType,
    FactualStatus,
)


def create_artifact(artifact_id):
    return ArtifactPlanItem(
        artifact_id=artifact_id,
        scene_id="scene_01",
        artifact_type=ArtifactType.CHART,
        source_strategy=(
            ArtifactStrategy
            .DETERMINISTIC_CHART
        ),
        factual_status=(
            FactualStatus.FACTUAL
        ),
        purpose="Show an approved metric.",
        visual_brief=(
            "A minimal factual metric chart."
        ),
        fallback_strategy=(
            "Use a typographic metric."
        ),
    )


def test_artifact_plan_is_valid():
    plan = ArtifactPlan(
        candidate_name="Test Candidate",
        creative_concept=(
            "Transformation through scale"
        ),
        artifacts=[
            create_artifact("artifact_001")
        ],
    )

    assert len(plan.artifacts) == 1


def test_duplicate_artifact_ids_are_rejected():
    with pytest.raises(ValidationError):
        ArtifactPlan(
            candidate_name="Test Candidate",
            creative_concept="Test concept",
            artifacts=[
                create_artifact(
                    "artifact_001"
                ),
                create_artifact(
                    "artifact_001"
                ),
            ],
        )


def test_invalid_dimensions_are_rejected():
    with pytest.raises(ValidationError):
        ArtifactPlanItem(
            artifact_id="artifact_001",
            scene_id="scene_01",
            artifact_type=(
                ArtifactType.IMAGE
            ),
            source_strategy=(
                ArtifactStrategy
                .IMAGE_GENERATION
            ),
            factual_status=(
                FactualStatus.DECORATIVE
            ),
            purpose="Decorative background.",
            visual_brief="Abstract background.",
            fallback_strategy=(
                "Use a gradient background."
            ),
            preferred_width=0,
        )
