"""Final deterministic specification consumed by the video renderer."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictBaseModel(BaseModel):
    """Base model that rejects unexpected fields."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )


class RenderVideoSettings(StrictBaseModel):
    """Technical output settings for the rendered video."""

    width: int = Field(default=1920, gt=0)
    height: int = Field(default=1080, gt=0)
    fps: int = Field(default=30, gt=0)
    duration_frames: int = Field(gt=0)
    output_format: str = "mp4"
    codec: str = "h264"
    pixel_format: str = "yuv420p"


class ThemeSettings(StrictBaseModel):
    """Brand and visual theme configuration."""

    theme_id: str = "positive_moves_premium_v1"
    primary_colour: str = "#111111"
    secondary_colour: str = "#6B6B6B"
    background_colour: str = "#F5F5F5"
    accent_colour: str = "#B79A5B"
    font_family: str = "Inter"
    logo_asset_path: str | None = None
    confidential: bool = True
    confidentiality_text: str = "Private and Confidential"


class AudioTrack(StrictBaseModel):
    """Narration audio attached to the video timeline."""

    source_path: str
    duration_seconds: float = Field(gt=0)
    start_frame: int = Field(default=0, ge=0)
    volume: float = Field(default=1.0, ge=0.0, le=2.0)


class RenderEvent(StrictBaseModel):
    """A timed animation or content event within a scene."""

    event_id: str
    event_type: str
    start_frame: int = Field(ge=0)
    duration_frames: int = Field(gt=0)
    props: dict[str, Any] = Field(default_factory=dict)


class RenderScene(StrictBaseModel):
    """One fully resolved scene consumed by the renderer."""

    scene_id: str
    component: str
    variant: str = "default"
    start_frame: int = Field(ge=0)
    duration_frames: int = Field(gt=0)
    props: dict[str, Any] = Field(default_factory=dict)
    events: list[RenderEvent] = Field(default_factory=list)

    @property
    def end_frame(self) -> int:
        """Return the exclusive end frame of the scene."""

        return self.start_frame + self.duration_frames


class ResolvedAsset(StrictBaseModel):
    """A local asset resolved for use by the renderer."""

    asset_id: str
    asset_type: str
    source_path: str
    renderer_path: str | None = None
    required: bool = True


class RenderSpecification(StrictBaseModel):
    """Complete frame-level contract for video rendering."""

    schema_version: str = "1.0"
    render_id: str
    candidate_name: str
    video: RenderVideoSettings
    theme: ThemeSettings = Field(default_factory=ThemeSettings)
    audio: AudioTrack
    scenes: list[RenderScene] = Field(min_length=1)
    assets: list[ResolvedAsset] = Field(default_factory=list)
    output_path: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_render_timeline(self) -> "RenderSpecification":
        """Validate unique IDs and ensure scenes fit the video timeline."""

        scene_ids = [scene.scene_id for scene in self.scenes]

        if len(scene_ids) != len(set(scene_ids)):
            raise ValueError("Render scene IDs must be unique.")

        ordered_scenes = sorted(
            self.scenes,
            key=lambda scene: scene.start_frame,
        )

        for index, scene in enumerate(ordered_scenes):
            if scene.end_frame > self.video.duration_frames:
                raise ValueError(
                    f"Scene '{scene.scene_id}' ends after the video."
                )

            if index > 0:
                previous_scene = ordered_scenes[index - 1]

                if scene.start_frame < previous_scene.end_frame:
                    raise ValueError(
                        f"Scene '{scene.scene_id}' overlaps with "
                        f"'{previous_scene.scene_id}'."
                    )

        return self
