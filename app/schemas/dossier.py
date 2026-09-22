"""Canonical structured schema extracted from a candidate dossier."""

from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictBaseModel(BaseModel):
    """Base model that rejects unexpected fields."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )


class SensitivityLevel(str, Enum):
    """Sensitivity category assigned to extracted information."""

    PROFESSIONAL = "professional"
    CONFIDENTIAL_PROFESSIONAL = "confidential_professional"
    FINANCIAL_SENSITIVE = "financial_sensitive"
    RESTRICTED_PII = "restricted_pii"
    SENSITIVE_PERSONAL = "sensitive_personal"


class ConfidenceLevel(str, Enum):
    """Readable confidence category for an extracted claim."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class MediaAssetType(str, Enum):
    """Supported media types extracted from a dossier."""

    CANDIDATE_PHOTO = "candidate_photo"
    COMPANY_LOGO = "company_logo"
    ORGANISATION_CHART = "organisation_chart"
    CHART = "chart"
    OTHER = "other"


class SourceReference(StrictBaseModel):
    """Traceability information connecting a claim to the source dossier."""

    page_number: int = Field(ge=1)
    section_name: str | None = None
    source_text: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    confidence_level: ConfidenceLevel = ConfidenceLevel.HIGH

    @field_validator("source_text")
    @classmethod
    def limit_source_text(cls, value: str | None) -> str | None:
        """Prevent excessively large source excerpts."""

        if value and len(value) > 2000:
            return value[:2000]
        return value


class CandidateProfile(StrictBaseModel):
    """Candidate identity and high-level professional profile."""

    full_name: str
    current_or_last_title: str | None = None
    current_or_last_company: str | None = None
    location: str | None = None
    professional_summary: str | None = None
    total_experience_years: float | None = Field(default=None, ge=0)
    industries: list[str] = Field(default_factory=list)
    functions: list[str] = Field(default_factory=list)
    source_references: list[SourceReference] = Field(default_factory=list)


class CareerEntry(StrictBaseModel):
    """One role in the candidate's career history."""

    company: str
    title: str
    start_date: str | None = None
    end_date: str | None = None
    is_current: bool = False
    location: str | None = None
    role_summary: str | None = None
    responsibilities: list[str] = Field(default_factory=list)
    achievements: list[str] = Field(default_factory=list)
    source_references: list[SourceReference] = Field(default_factory=list)


class CareerHighlight(StrictBaseModel):
    """A notable candidate achievement or professional highlight."""

    statement: str
    short_label: str | None = None
    metric_value: str | None = None
    metric_label: str | None = None
    company: str | None = None
    category: str | None = None
    video_eligible: bool = True
    sensitivity: SensitivityLevel = SensitivityLevel.PROFESSIONAL
    source_references: list[SourceReference] = Field(default_factory=list)


class OrganisationNode(StrictBaseModel):
    """One role or function in an organisation structure."""

    label: str
    role_title: str | None = None
    relationship: str | None = None
    headcount: int | None = Field(default=None, ge=0)


class OrganisationStructure(StrictBaseModel):
    """Simplified organisation structure around the candidate."""

    reports_to: str | None = None
    direct_reports: int | None = Field(default=None, ge=0)
    total_team_size: int | None = Field(default=None, ge=0)
    functions_led: list[str] = Field(default_factory=list)
    nodes: list[OrganisationNode] = Field(default_factory=list)
    source_references: list[SourceReference] = Field(default_factory=list)


class LeadershipScope(StrictBaseModel):
    """Scale and scope of the candidate's leadership experience."""

    team_size: int | None = Field(default=None, ge=0)
    direct_reports: int | None = Field(default=None, ge=0)
    budget_managed: str | None = None
    geographic_scope: list[str] = Field(default_factory=list)
    business_scope: list[str] = Field(default_factory=list)
    functions_led: list[str] = Field(default_factory=list)
    source_references: list[SourceReference] = Field(default_factory=list)


class Assessment(StrictBaseModel):
    """Professional assessment contained in the dossier."""

    functional_expertise: list[str] = Field(default_factory=list)
    stakeholder_and_people_leadership: list[str] = Field(
        default_factory=list
    )
    commercial_orientation: list[str] = Field(default_factory=list)
    additional_strengths: list[str] = Field(default_factory=list)
    development_considerations: list[str] = Field(default_factory=list)
    source_references: list[SourceReference] = Field(default_factory=list)


class Compensation(StrictBaseModel):
    """Candidate compensation information."""

    current_fixed: str | None = None
    current_variable: str | None = None
    current_total: str | None = None
    expected_compensation: str | None = None
    currency: str | None = None
    additional_components: list[str] = Field(default_factory=list)
    display_allowed: bool = False
    sensitivity: SensitivityLevel = SensitivityLevel.FINANCIAL_SENSITIVE
    source_references: list[SourceReference] = Field(default_factory=list)


class Availability(StrictBaseModel):
    """Candidate notice period and availability information."""

    notice_period: str | None = None
    earliest_start_date: str | None = None
    availability_notes: str | None = None
    display_allowed: bool = True
    sensitivity: SensitivityLevel = (
        SensitivityLevel.CONFIDENTIAL_PROFESSIONAL
    )
    source_references: list[SourceReference] = Field(default_factory=list)


class MediaAsset(StrictBaseModel):
    """A visual asset detected or extracted from the dossier."""

    asset_id: str
    asset_type: MediaAssetType
    source_page: int = Field(ge=1)
    local_path: str | None = None
    description: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    approved_for_video: bool = False


class SensitiveInformation(StrictBaseModel):
    """Sensitive source content excluded from automatic video generation."""

    category: SensitivityLevel
    description: str
    source_references: list[SourceReference] = Field(default_factory=list)
    allowed_in_video: bool = False

class AdditionalSection(StrictBaseModel):
    """An additional dossier section not covered by standard fields."""

    section_name: str
    summary: str | None = None
    key_points: list[str] = Field(default_factory=list)
    source_references: list[SourceReference] = Field(
        default_factory=list
    )


class DossierMetadata(StrictBaseModel):
    """Metadata describing the dossier extraction process."""

    document_id: str | None = None
    original_filename: str | None = None
    page_count: int | None = Field(default=None, ge=1)
    extraction_model: str | None = None
    extraction_timestamp: str | None = None
    schema_version: str = "1.0"
    warnings: list[str] = Field(default_factory=list)


class Dossier(StrictBaseModel):
    """Complete canonical representation of a candidate dossier."""

    metadata: DossierMetadata = Field(default_factory=DossierMetadata)
    candidate: CandidateProfile
    career_history: list[CareerEntry] = Field(default_factory=list)
    career_highlights: list[CareerHighlight] = Field(default_factory=list)
    organisation_structure: OrganisationStructure | None = None
    leadership_scope: LeadershipScope | None = None
    assessment: Assessment | None = None
    compensation: Compensation | None = None
    availability: Availability | None = None
    media_assets: list[MediaAsset] = Field(default_factory=list)
    sensitive_information: list[SensitiveInformation] = Field(
        default_factory=list
    )
    additional_sections: list[AdditionalSection] = Field(
    default_factory=list
    )
