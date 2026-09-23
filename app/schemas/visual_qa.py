"""Schemas for preview-frame and visual-quality assessment."""
from __future__ import annotations
from pydantic import BaseModel, ConfigDict, Field


class StrictBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class VisualIssue(StrictBaseModel):
    issue_id: str
    category: str
    severity: str
    blocking: bool = False
    frame_label: str | None = None
    description: str
    recommended_change: str


class VisualQAResult(StrictBaseModel):
    approved: bool

    approved_with_warnings: bool = False

    blocking_issue_count: int = Field(
        default=0,
        ge=0,
    )

    warning_count: int = Field(
        default=0,
        ge=0,
    )

    overall_score: float = Field(
        ge=0,
        le=1,
    )

    hierarchy_score: float = Field(
        ge=0,
        le=1,
    )

    readability_score: float = Field(
        ge=0,
        le=1,
    )

    balance_score: float = Field(
        ge=0,
        le=1,
    )

    brand_consistency_score: float = Field(
        ge=0,
        le=1,
    )

    artifact_relevance_score: float = Field(
        ge=0,
        le=1,
    )

    summary: str

    strengths: list[str] = Field(
        default_factory=list,
    )

    issues: list[VisualIssue] = Field(
        default_factory=list,
    )

    required_changes: list[str] = Field(
        default_factory=list,
    )


class DeterministicPreviewCheck(StrictBaseModel):
    valid: bool
    frame_count: int = Field(ge=0)
    missing_frames: list[str] = Field(default_factory=list)
    invalid_images: list[str] = Field(default_factory=list)
    dimension_mismatches: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
