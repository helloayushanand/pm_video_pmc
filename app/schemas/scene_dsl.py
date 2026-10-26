"""Scene DSL schema — the contract between LLM output and the Remotion renderer.

The LLM returns a VideoSpec. The pipeline validates it, runs deterministic
checks (contrast, overlap), and passes the JSON to the Remotion DSLScene
renderer. No generated TSX is needed.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictBase(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )


# ── Backgrounds ───────────────────────────────────────────────────────

class SolidBackground(StrictBase):
    type: Literal["solid"] = "solid"
    color: str

class GradientBackground(StrictBase):
    type: Literal["gradient"] = "gradient"
    from_color: str = Field(alias="from")
    to_color: str = Field(alias="to")
    angle: int = 135

class RadialBackground(StrictBase):
    type: Literal["radial"] = "radial"
    base: str
    highlight: str
    position: str = "50% 30%"

BackgroundSpec = SolidBackground | GradientBackground | RadialBackground


# ── Theme overrides ───────────────────────────────────────────────────

class ThemeOverrides(StrictBase):
    model_config = ConfigDict(extra="forbid")

    background: str | None = None
    surface: str | None = None
    surface_secondary: str | None = None
    foreground: str | None = None
    foreground_muted: str | None = None
    accent: str | None = None
    accent_secondary: str | None = None
    border: str | None = None


# ── Entrance animations ──────────────────────────────────────────────

class EntranceType(str, Enum):
    NONE = "none"
    FADE = "fade"
    SLIDE_UP = "slide_up"
    SLIDE_DOWN = "slide_down"
    SLIDE_LEFT = "slide_left"
    SLIDE_RIGHT = "slide_right"
    SCALE = "scale"

class EntranceSpec(StrictBase):
    type: EntranceType = EntranceType.FADE
    delay: float = 0.0
    duration: float = 0.6


# ── Element types ─────────────────────────────────────────────────────

class TextElement(StrictBase):
    type: Literal["text"] = "text"
    content: str
    role: Literal["display", "heading", "subheading", "body", "label", "caption"]
    align: Literal["left", "center", "right"] = "left"
    color: str | None = None
    max_width: int | None = None
    entrance: EntranceSpec | None = None

class AutoFitTextElement(StrictBase):
    type: Literal["autofit_text"] = "autofit_text"
    text: str
    max_font_size: int | None = None
    min_font_size: int | None = None
    align: Literal["left", "center", "right"] = "left"
    entrance: EntranceSpec | None = None

class MetricElement(StrictBase):
    type: Literal["metric"] = "metric"
    value: str
    label: str | None = None
    emphasis: Literal["hero", "primary", "supporting"] = "primary"
    entrance: EntranceSpec | None = None

class MetricRowItem(StrictBase):
    value: str
    label: str | None = None
    emphasis: Literal["hero", "primary", "supporting"] = "primary"

class MetricRowElement(StrictBase):
    type: Literal["metric_row"] = "metric_row"
    items: list[MetricRowItem] = Field(min_length=1, max_length=6)
    card_style: bool = False
    entrance: EntranceSpec | None = None
    stagger: float = 0.15

class TimelineNode(StrictBase):
    year: str
    title: str
    subtitle: str | None = None
    accent: str | None = None

class TimelineElement(StrictBase):
    type: Literal["timeline"] = "timeline"
    orientation: Literal["horizontal", "vertical"] = "horizontal"
    nodes: list[TimelineNode] = Field(min_length=2, max_length=8)
    connector_style: Literal["solid", "dashed", "dotted"] = "solid"
    entrance: EntranceSpec | None = None
    stagger: float = 0.2

class BulletItem(StrictBase):
    text: str
    icon: str | None = None
    subtext: str | None = None

class BulletListElement(StrictBase):
    type: Literal["bullet_list"] = "bullet_list"
    items: list[BulletItem] = Field(min_length=1, max_length=8)
    columns: Literal[1, 2] = 1
    entrance: EntranceSpec | None = None
    stagger: float = 0.12

class PortraitElement(StrictBase):
    type: Literal["portrait"] = "portrait"
    artifact_id: str
    border_color: str | None = None
    border_radius: int = 24
    shadow: bool = True
    entrance: EntranceSpec | None = None

class ImageElement(StrictBase):
    type: Literal["image"] = "image"
    artifact_id: str
    fit: Literal["cover", "contain"] = "cover"
    border_radius: int = 0
    entrance: EntranceSpec | None = None

class QuoteElement(StrictBase):
    type: Literal["quote"] = "quote"
    text: str
    attribution: str | None = None
    style: Literal["editorial", "callout", "minimal"] = "editorial"
    entrance: EntranceSpec | None = None

class OrgNode(StrictBase):
    label: str
    sublabel: str | None = None

class OrgTreeElement(StrictBase):
    type: Literal["org_tree"] = "org_tree"
    center_node: OrgNode
    children: list[OrgNode] = Field(min_length=1, max_length=8)
    style: Literal["radial", "top_down"] = "radial"
    entrance: EntranceSpec | None = None

class BadgeItem(StrictBase):
    label: str
    icon: str | None = None

class BadgeRowElement(StrictBase):
    type: Literal["badge_row"] = "badge_row"
    items: list[BadgeItem] = Field(min_length=1, max_length=12)
    entrance: EntranceSpec | None = None
    stagger: float = 0.08

class DividerElement(StrictBase):
    type: Literal["divider"] = "divider"
    color: str | None = None
    thickness: int = 1

class SpacerElement(StrictBase):
    type: Literal["spacer"] = "spacer"
    height: int

class ProgressBarElement(StrictBase):
    type: Literal["progress_bar"] = "progress_bar"
    value: float = Field(ge=0, le=100)
    label: str | None = None
    color: str | None = None
    entrance: EntranceSpec | None = None

ElementSpec = (
    TextElement
    | AutoFitTextElement
    | MetricElement
    | MetricRowElement
    | TimelineElement
    | BulletListElement
    | PortraitElement
    | ImageElement
    | QuoteElement
    | OrgTreeElement
    | BadgeRowElement
    | DividerElement
    | SpacerElement
    | ProgressBarElement
)


# ── Layouts ───────────────────────────────────────────────────────────

class StackLayout(StrictBase):
    type: Literal["stack"] = "stack"
    direction: Literal["column", "row"] = "column"
    gap: int = 24
    align: Literal["left", "center", "right"] = "left"
    justify: Literal["start", "center", "end", "between"] = "start"
    elements: list[ElementSpec] = Field(min_length=1)

class SplitLayout(StrictBase):
    type: Literal["split"] = "split"
    left_ratio: float = Field(default=0.5, ge=0.25, le=0.75)
    gap: int = 64
    left: list[ElementSpec] = Field(min_length=1)
    right: list[ElementSpec] = Field(min_length=1)

class GridLayout(StrictBase):
    type: Literal["grid"] = "grid"
    columns: int = Field(ge=2, le=4)
    gap: int = 24
    elements: list[ElementSpec] = Field(min_length=1)

LayoutSpec = StackLayout | SplitLayout | GridLayout


# ── Scene spec ────────────────────────────────────────────────────────

class SceneSpec(StrictBase):
    scene_id: str
    title: str
    duration_seconds: float = Field(ge=3.0, le=20.0)
    background: BackgroundSpec
    theme_overrides: ThemeOverrides | None = None
    layout: LayoutSpec
    narration: str | None = None


# ── Artifact specs (images the pipeline should generate) ─────────────

class ArtifactSpec(StrictBase):
    artifact_id: str = Field(description="Unique ID referenced by image elements in scenes")
    prompt: str = Field(default="", description="Detailed description for DALL-E generation; empty when source is 'extracted_headshot'")
    orientation: Literal["landscape", "square", "portrait"] = "landscape"
    source: Literal["generate", "extracted_headshot"] = Field(
        default="generate",
        description="'generate' = call DALL-E; 'extracted_headshot' = use photo extracted from the source document",
    )


# ── Video spec (full output from LLM) ────────────────────────────────

class VideoSpec(StrictBase):
    candidate_name: str
    confidentiality_text: str = "Private and Confidential"
    scenes: list[SceneSpec] = Field(min_length=1, max_length=12)
    global_theme: ThemeOverrides | None = None
    artifacts: list[ArtifactSpec] = Field(default_factory=list)
