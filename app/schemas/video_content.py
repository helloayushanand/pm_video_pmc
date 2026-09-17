"""Schema for facts selected from a dossier for video generation."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.dossier import SourceReference


class StrictBaseModel(BaseModel):
    """Base model that rejects unexpected fields."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )


class CandidateIntroduction(StrictBaseModel):
    """Candidate information shown in the opening scene."""

    name: str
    title: str | None = None
    company: str | None = None
    location: str | None = None
    photo_asset_id: str | None = None


class SelectedCareerMilestone(StrictBaseModel):
    """A career milestone selected for the candidate video."""

    company: str
    title: str
    period: str | None = None
    summary: str | None = None
    source_references: list[SourceReference] = Field(default_factory=list)


class SelectedHighlight(StrictBaseModel):
    """A candidate achievement selected for the video."""

    statement: str
    short_label: str
    metric_value: str | None = None
    metric_label: str | None = None
    company: str | None = None
    priority: int = Field(default=1, ge=1, le=10)
    source_references: list[SourceReference] = Field(default_factory=list)


class SelectedLeadershipScope(StrictBaseModel):
    """Leadership information selected for visual presentation."""

    headline: str | None = None
    reports_to: str | None = None
    direct_reports: int | None = Field(default=None, ge=0)
    total_team_size: int | None = Field(default=None, ge=0)
    functions_led: list[str] = Field(default_factory=list)
    geographic_scope: list[str] = Field(default_factory=list)
    source_references: list[SourceReference] = Field(default_factory=list)


class SelectedStrength(StrictBaseModel):
    """One concise professional strength selected for the video."""

    title: str
    description: str
    source_references: list[SourceReference] = Field(default_factory=list)


class OptionalCandidateDetails(StrictBaseModel):
    """Sensitive or optional details controlled by generation settings."""

    include_compensation: bool = False
    compensation_summary: str | None = None
    include_availability: bool = True
    availability_summary: str | None = None


class ExcludedContent(StrictBaseModel):
    """Information deliberately excluded from the generated video."""

    description: str
    reason: str
    source_page: int | None = Field(default=None, ge=1)


class VideoContent(StrictBaseModel):
    """Sanitised and selected content used to create a storyboard."""

    schema_version: str = "1.0"
    candidate_intro: CandidateIntroduction
    executive_summary: str
    career_milestones: list[SelectedCareerMilestone] = Field(
        default_factory=list
    )
    selected_highlights: list[SelectedHighlight] = Field(
        default_factory=list
    )
    leadership_scope: SelectedLeadershipScope | None = None
    strengths: list[SelectedStrength] = Field(default_factory=list)
    optional_details: OptionalCandidateDetails = Field(
        default_factory=OptionalCandidateDetails
    )
    excluded_content: list[ExcludedContent] = Field(default_factory=list)
    recommended_duration_seconds: float = Field(default=45.0, gt=0)
    content_notes: list[str] = Field(default_factory=list)
