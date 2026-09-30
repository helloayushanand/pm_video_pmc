"""Storyboard and narration schemas."""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

TARGET_VIDEO_DURATION_SECONDS = 55.0
MAX_VIDEO_DURATION_SECONDS = 65.0
MAX_STORYBOARD_SCENES = 8
MAX_VOICEOVER_WORDS = 145


class StrictBaseModel(BaseModel):
    """Base model that rejects unexpected fields."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )


class SceneType(str, Enum):
    CANDIDATE_INTRO = "candidate_intro"
    EXECUTIVE_SUMMARY = "executive_summary"
    CAREER_TIMELINE = "career_timeline"
    CAREER_MILESTONE = "career_milestone"
    QUANTIFIED_HIGHLIGHTS = "quantified_highlights"
    SINGLE_HIGHLIGHT = "single_highlight"
    LEADERSHIP_SCOPE = "leadership_scope"
    ORGANISATION_STRUCTURE = "organisation_structure"
    STRENGTH_SUMMARY = "strength_summary"
    COMPENSATION_AVAILABILITY = "compensation_availability"
    CLOSING = "closing"


class VisualElementType(str, Enum):
    HEADING = "heading"
    SUBHEADING = "subheading"
    BODY_TEXT = "body_text"
    METRIC = "metric"
    IMAGE = "image"
    LOGO = "logo"
    TIMELINE = "timeline"
    ORGANISATION_CHART = "organisation_chart"
    LABEL = "label"
    CONFIDENTIALITY_MARKER = "confidentiality_marker"


class PronunciationHint(StrictBaseModel):
    text: str
    pronunciation: str


class VisualMetadataItem(StrictBaseModel):
    key: str
    value: str


class VoiceoverSegment(StrictBaseModel):
    segment_id: str
    text: str
    estimated_duration_seconds: float | None = Field(default=None, gt=0)
    pronunciation_hints: list[PronunciationHint] = Field(default_factory=list)
    pause_after_seconds: float = Field(default=0.0, ge=0)


class VisualElement(StrictBaseModel):
    element_id: str
    element_type: VisualElementType
    content: str | None = None
    value: str | None = None
    label: str | None = None
    asset_id: str | None = None
    animation: str | None = None
    display_order: int = Field(default=1, ge=1)
    metadata: list[VisualMetadataItem] = Field(default_factory=list)


class StoryboardScene(StrictBaseModel):
    scene_id: str
    scene_type: SceneType
    purpose: str
    variant: str = "default"
    estimated_duration_seconds: float = Field(gt=0, le=15.0)
    voiceover_segments: list[VoiceoverSegment] = Field(default_factory=list)
    visual_elements: list[VisualElement] = Field(default_factory=list)
    transition_in: str = "fade"
    transition_out: str = "fade"
    background_variant: str = "default"
    notes: list[str] = Field(default_factory=list)

    @property
    def complete_voiceover(self):
        return " ".join(segment.text for segment in self.voiceover_segments).strip()


class Storyboard(StrictBaseModel):
    """Complete editable plan for a concise candidate video."""

    schema_version: str = "1.1"
    title: str
    candidate_name: str
    video_mode: str = "automatic"
    target_duration_seconds: float = Field(
        default=TARGET_VIDEO_DURATION_SECONDS,
        gt=0,
        le=MAX_VIDEO_DURATION_SECONDS,
    )
    scenes: list[StoryboardScene] = Field(min_length=1, max_length=MAX_STORYBOARD_SCENES)
    global_voice: str | None = None
    tone: str = "premium, professional, concise"
    branding_theme: str = "positive_moves_premium_v1"
    confidential: bool = True
    generation_notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_storyboard_budget(self):
        scene_ids = [scene.scene_id for scene in self.scenes]
        if len(scene_ids) != len(set(scene_ids)):
            raise ValueError("Storyboard scene IDs must be unique.")

        if self.estimated_total_duration_seconds > MAX_VIDEO_DURATION_SECONDS:
            raise ValueError(
                "Storyboard exceeds the hard video duration limit: "
                f"{self.estimated_total_duration_seconds:.1f}s > "
                f"{MAX_VIDEO_DURATION_SECONDS:.1f}s."
            )

        word_count = len(self.complete_voiceover.split())
        if word_count > MAX_VOICEOVER_WORDS:
            raise ValueError(
                "Storyboard voiceover exceeds the concise-video word budget: "
                f"{word_count} words > {MAX_VOICEOVER_WORDS} words."
            )
        return self

    @property
    def estimated_total_duration_seconds(self):
        return round(sum(scene.estimated_duration_seconds for scene in self.scenes), 3)

    @property
    def complete_voiceover(self):
        return " ".join(
            scene.complete_voiceover
            for scene in self.scenes
            if scene.complete_voiceover
        ).strip()
