"""Schemas for full-video cohesion review and release approval."""
from __future__ import annotations
from pydantic import BaseModel, ConfigDict, Field


class StrictBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class FullVideoIssue(StrictBaseModel):
    issue_id: str
    category: str
    severity: str
    blocking: bool = False
    timestamp_label: str | None = None
    description: str
    recommended_change: str


class FullVideoCohesionResult(StrictBaseModel):
    approved: bool
    approved_with_warnings: bool = False
    overall_score: float = Field(ge=0, le=1)
    typography_consistency_score: float = Field(ge=0, le=1)
    palette_consistency_score: float = Field(ge=0, le=1)
    transition_cohesion_score: float = Field(ge=0, le=1)
    pacing_score: float = Field(ge=0, le=1)
    confidentiality_consistency_score: float = Field(ge=0, le=1)
    blocking_issue_count: int = Field(default=0, ge=0)
    warning_count: int = Field(default=0, ge=0)
    summary: str
    strengths: list[str] = Field(default_factory=list)
    issues: list[FullVideoIssue] = Field(default_factory=list)
    required_changes: list[str] = Field(default_factory=list)
