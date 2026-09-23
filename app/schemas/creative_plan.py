"""Schemas for creative direction and dynamic scene planning."""

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


class VisualTone(str, Enum):
    """Supported high-level visual tones."""

    PREMIUM_EDITORIAL = "premium_editorial"
    EXECUTIVE_MINIMAL = "executive_minimal"
    BUSINESS_NEWS = "business_news"
    STRATEGIC_CONSULTING = "strategic_consulting"
    DATA_LED = "data_led"


class MotionCharacter(str, Enum):
    """Supported motion systems."""

    RESTRAINED = "restrained"
    MEASURED = "measured"
    CINEMATIC = "cinematic"
    DATA_DRIVEN = "data_driven"
    EDITORIAL = "editorial"


class ContentDensity(str, Enum):
    """Visual content-density levels."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ComponentStrategy(str, Enum):
    """How a scene should eventually be rendered."""

    EXISTING_COMPONENT = "existing_component"

    EXISTING_COMPONENT_VARIANT = (
        "existing_component_variant"
    )

    GENERATED_COMPONENT = "generated_component"


class ArtifactStrategy(str, Enum):
    """How a visual artifact should be produced."""

    EXTRACT_FROM_DOSSIER = "extract_from_dossier"
    APPROVED_LOCAL_ASSET = "approved_local_asset"
    DETERMINISTIC_CHART = "deterministic_chart"
    DETERMINISTIC_DIAGRAM = "deterministic_diagram"
    IMAGE_GENERATION = "image_generation"
    REMOTION_NATIVE = "remotion_native"
    TYPOGRAPHY_ONLY = "typography_only"


class FactualStatus(str, Enum):
    """Whether an artifact communicates factual information."""

    FACTUAL = "factual"
    DECORATIVE = "decorative"
    MIXED = "mixed"


class CreativeDirection(StrictBaseModel):
    """One coherent design system for a complete video."""

    creative_concept: str

    visual_tone: VisualTone = (
        VisualTone.PREMIUM_EDITORIAL
    )

    motion_character: MotionCharacter = (
        MotionCharacter.MEASURED
    )

    content_density: ContentDensity = (
        ContentDensity.MEDIUM
    )

    palette_variant: str
    typography_variant: str
    transition_family: str
    image_treatment: str
    metric_treatment: str
    chart_treatment: str
    background_treatment: str

    visual_motifs: list[str] = Field(
        default_factory=list
    )

    prohibited_treatments: list[str] = Field(
        default_factory=list
    )

    creative_rationale: str

    brand_considerations: list[str] = Field(
        default_factory=list
    )

    confidentiality_treatment: str


class ArtifactRequirement(StrictBaseModel):
    """One requested visual artifact for a scene."""

    artifact_id: str
    artifact_type: str

    source_strategy: ArtifactStrategy
    factual_status: FactualStatus

    purpose: str
    required: bool = True

    data_reference: str | None = None

    source_reference_ids: list[str] = Field(
        default_factory=list
    )

    visual_brief: str
    fallback_strategy: str

    preferred_width: int | None = Field(
        default=None,
        gt=0,
    )

    preferred_height: int | None = Field(
        default=None,
        gt=0,
    )

    transparent_background: bool = False

    generation_constraints: list[str] = Field(
        default_factory=list
    )


class SceneArchitectureBrief(StrictBaseModel):
    """A custom component brief for one video scene."""

    scene_id: str
    scene_type: str
    scene_purpose: str

    component_strategy: ComponentStrategy
    component_name_suggestion: str
    fallback_component: str

    visual_story: str
    layout_intent: str

    visual_hierarchy: list[str] = Field(
        min_length=1
    )

    focal_element: str

    supporting_elements: list[str] = Field(
        default_factory=list
    )

    content_density: ContentDensity

    animation_intent: str
    transition_in: str
    transition_out: str

    background_treatment: str
    typography_treatment: str
    color_emphasis: str

    artifact_requirements: list[
        ArtifactRequirement
    ] = Field(
        default_factory=list
    )

    approved_facts: list[str] = Field(
        default_factory=list
    )

    prohibited_inferences: list[str] = Field(
        default_factory=list
    )

    accessibility_notes: list[str] = Field(
        default_factory=list
    )

    expected_visual_peak_percentage: float = Field(
        default=0.65,
        ge=0,
        le=1,
    )

    custom_component_required: bool = True

    @model_validator(mode="after")
    def validate_component_strategy(self):
        """Keep strategy and custom-component flag consistent."""

        if (
            self.component_strategy
            == ComponentStrategy.GENERATED_COMPONENT
            and not self.custom_component_required
        ):
            raise ValueError(
                "A generated_component scene must set "
                "custom_component_required to true."
            )

        if (
            self.component_strategy
            != ComponentStrategy.GENERATED_COMPONENT
            and self.custom_component_required
        ):
            self.custom_component_required = False

        return self

    @model_validator(mode="after")
    def validate_artifact_ids(self):
        """Ensure artifact IDs are unique inside the scene."""

        artifact_ids = [
            artifact.artifact_id
            for artifact in self.artifact_requirements
        ]

        if len(artifact_ids) != len(set(artifact_ids)):
            raise ValueError(
                "Artifact IDs must be unique within a scene."
            )

        return self


class CreativePlanDraft(StrictBaseModel):
    """Creative plan before cross-scene review."""

    schema_version: str = "1.0"

    candidate_name: str
    video_title: str

    narrative_thesis: str
    opening_hook: str
    closing_message: str

    creative_direction: CreativeDirection

    scene_briefs: list[
        SceneArchitectureBrief
    ] = Field(
        min_length=1
    )

    global_artifact_notes: list[str] = Field(
        default_factory=list
    )

    global_safety_notes: list[str] = Field(
        default_factory=list
    )

    generation_notes: list[str] = Field(
        default_factory=list
    )

    @model_validator(mode="after")
    def validate_unique_scene_ids(self):
        """Ensure each planned scene ID is unique."""

        scene_ids = [
            scene.scene_id
            for scene in self.scene_briefs
        ]

        if len(scene_ids) != len(set(scene_ids)):
            raise ValueError(
                "Creative-plan scene IDs must be unique."
            )

        return self

    @model_validator(mode="after")
    def validate_unique_artifact_ids(self):
        """Ensure artifact IDs are unique across the video."""

        artifact_ids = [
            artifact.artifact_id
            for scene in self.scene_briefs
            for artifact in scene.artifact_requirements
        ]

        if len(artifact_ids) != len(set(artifact_ids)):
            raise ValueError(
                "Artifact IDs must be unique across "
                "the complete creative plan."
            )

        return self


class CohesionIssue(StrictBaseModel):
    """One cross-scene design issue."""

    issue_id: str
    category: str
    severity: str

    affected_scene_ids: list[str] = Field(
        default_factory=list
    )

    description: str
    recommended_change: str


class CohesionReview(StrictBaseModel):
    """Cross-scene review of a creative plan."""

    approved: bool

    overall_cohesion_score: float = Field(
        ge=0,
        le=1,
    )

    design_consistency_score: float = Field(
        ge=0,
        le=1,
    )

    scene_variety_score: float = Field(
        ge=0,
        le=1,
    )

    narrative_visual_alignment_score: float = Field(
        ge=0,
        le=1,
    )

    brand_consistency_score: float = Field(
        ge=0,
        le=1,
    )

    summary: str

    strengths: list[str] = Field(
        default_factory=list
    )

    issues: list[CohesionIssue] = Field(
        default_factory=list
    )

    required_changes: list[str] = Field(
        default_factory=list
    )

    approval_notes: list[str] = Field(
        default_factory=list
    )

    @model_validator(mode="after")
    def validate_approval(self):
        """Prevent approval when high-severity issues remain."""

        high_severity_issues = [
            issue
            for issue in self.issues
            if issue.severity.lower() == "high"
        ]

        if self.approved and high_severity_issues:
            raise ValueError(
                "A cohesion review cannot be approved "
                "while high-severity issues remain."
            )

        return self


class CreativePlan(StrictBaseModel):
    """Final creative plan with cohesion review."""

    draft: CreativePlanDraft
    cohesion_review: CohesionReview
