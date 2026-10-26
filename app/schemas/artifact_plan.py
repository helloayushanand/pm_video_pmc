"""Schemas for artifact planning, generation, and approval."""

from __future__ import annotations

from enum import Enum

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)


class StrictBaseModel(BaseModel):
    """Base model that rejects unsupported fields."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )


class ArtifactStrategy(str, Enum):
    """Supported artifact-production strategies."""

    EXTRACT_FROM_DOSSIER = "extract_from_dossier"
    APPROVED_LOCAL_ASSET = "approved_local_asset"
    DETERMINISTIC_CHART = "deterministic_chart"
    DETERMINISTIC_DIAGRAM = "deterministic_diagram"
    IMAGE_GENERATION = "image_generation"
    REMOTION_NATIVE = "remotion_native"
    TYPOGRAPHY_ONLY = "typography_only"


class ArtifactStatus(str, Enum):
    """Lifecycle state of an artifact."""

    PLANNED = "planned"
    EXTRACTED = "extracted"
    GENERATED = "generated"
    READY = "ready"
    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    FAILED = "failed"
    FALLBACK = "fallback"


class ArtifactType(str, Enum):
    """Supported artifact categories."""

    PORTRAIT = "portrait"
    IMAGE = "image"
    LOGO = "logo"
    CHART = "chart"
    DIAGRAM = "diagram"
    TIMELINE = "timeline"
    ORGANISATION_CHART = "organisation_chart"
    MAP = "map"
    BACKGROUND = "background"
    ICON = "icon"
    TYPOGRAPHY = "typography"
    REMOTION_GRAPHIC = "remotion_graphic"
    OTHER = "other"


class FactualStatus(str, Enum):
    """Whether the artifact communicates factual information."""

    FACTUAL = "factual"
    DECORATIVE = "decorative"
    MIXED = "mixed"


class ArtifactPlanItem(StrictBaseModel):
    """One planned visual artifact."""

    artifact_id: str
    scene_id: str
    artifact_type: ArtifactType

    source_strategy: ArtifactStrategy
    factual_status: FactualStatus

    purpose: str
    visual_brief: str
    fallback_strategy: str

    required: bool = True

    data_reference: str | None = None

    source_reference_ids: list[str] = Field(
        default_factory=list
    )

    generation_constraints: list[str] = Field(
        default_factory=list
    )

    preferred_width: int | None = Field(
        default=None,
        gt=0,
    )

    preferred_height: int | None = Field(
        default=None,
        gt=0,
    )

    transparent_background: bool = False

    output_format: str = "png"

    requires_human_approval: bool = False


class ArtifactPlan(StrictBaseModel):
    """Complete artifact plan for one candidate video."""

    schema_version: str = "1.0"
    candidate_name: str
    creative_concept: str

    artifacts: list[ArtifactPlanItem] = Field(
        default_factory=list
    )

    global_constraints: list[str] = Field(
        default_factory=list
    )

    generation_notes: list[str] = Field(
        default_factory=list
    )

    @model_validator(mode="after")
    def validate_unique_artifact_ids(self):
        """Ensure every artifact ID is unique."""

        artifact_ids = [
            artifact.artifact_id
            for artifact in self.artifacts
        ]

        if len(artifact_ids) != len(set(artifact_ids)):
            raise ValueError(
                "Artifact IDs must be unique."
            )

        return self


class ArtifactRecord(StrictBaseModel):
    """One produced or planned artifact record."""

    artifact_id: str
    scene_id: str
    artifact_type: ArtifactType

    source_strategy: ArtifactStrategy
    factual_status: FactualStatus

    status: ArtifactStatus

    required: bool
    approved: bool = False

    local_path: str | None = None
    renderer_path: str | None = None

    mime_type: str | None = None

    width: int | None = Field(
        default=None,
        gt=0,
    )

    height: int | None = Field(
        default=None,
        gt=0,
    )

    file_size_bytes: int | None = Field(
        default=None,
        ge=0,
    )

    alt_text: str
    source_description: str | None = None

    validation_errors: list[str] = Field(
        default_factory=list
    )

    validation_warnings: list[str] = Field(
        default_factory=list
    )

    fallback_strategy: str


class ArtifactManifest(StrictBaseModel):
    """Manifest consumed by future generated components."""

    schema_version: str = "1.0"
    candidate_name: str

    artifacts: list[ArtifactRecord] = Field(
        default_factory=list
    )

    approved_artifact_count: int = Field(
        default=0,
        ge=0,
    )

    pending_review_count: int = Field(
        default=0,
        ge=0,
    )

    failed_artifact_count: int = Field(
        default=0,
        ge=0,
    )

    @model_validator(mode="after")
    def calculate_counts(self):
        """Calculate manifest summary counts."""

        approved_count = sum(
            1
            for artifact in self.artifacts
            if artifact.approved
        )

        pending_count = sum(
            1
            for artifact in self.artifacts
            if artifact.status
            == ArtifactStatus.NEEDS_REVIEW
        )

        failed_count = sum(
            1
            for artifact in self.artifacts
            if artifact.status
            == ArtifactStatus.FAILED
        )

        object.__setattr__(
            self,
            "approved_artifact_count",
            approved_count,
        )

        object.__setattr__(
            self,
            "pending_review_count",
            pending_count,
        )

        object.__setattr__(
            self,
            "failed_artifact_count",
            failed_count,
        )

        return self

class ArtifactValidationReport(StrictBaseModel):
    """Validation summary for the artifact stage."""

    valid: bool

    artifact_count: int = Field(
        ge=0
    )

    approved_count: int = Field(
        ge=0
    )

    pending_review_count: int = Field(
        ge=0
    )

    failed_count: int = Field(
        ge=0
    )

    missing_required_artifacts: list[str] = Field(
        default_factory=list
    )

    errors: list[str] = Field(
        default_factory=list
    )

    warnings: list[str] = Field(
        default_factory=list
    )
