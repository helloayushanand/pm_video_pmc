"""Final deterministic specification consumed by the video renderer."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)


class StrictBaseModel(BaseModel):
    """Base model that rejects unexpected fields."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )


class RenderVideoSettings(StrictBaseModel):
    """Technical output settings for the rendered video."""

    width: int = Field(
        default=1920,
        gt=0,
    )

    height: int = Field(
        default=1080,
        gt=0,
    )

    fps: int = Field(
        default=30,
        gt=0,
    )

    duration_frames: int = Field(
        gt=0,
    )

    output_format: str = "mp4"

    codec: str = "h264"

    pixel_format: str = "yuv420p"


class ThemeSettings(StrictBaseModel):
    """Brand and visual theme configuration."""

    theme_id: str = (
        "positive_moves_premium_v2"
    )

    primary_colour: str = (
        "#111318"
    )

    secondary_colour: str = (
        "#5F6872"
    )

    background_colour: str = (
        "#F5F4F1"
    )

    accent_colour: str = (
        "#B79A5B"
    )

    accent_secondary_colour: str = (
        "#315D78"
    )

    accent_tertiary_colour: str = (
        "#00A79D"
    )

    surface_colour: str = (
        "#FFFFFF"
    )

    surface_secondary_colour: str = (
        "#E9E4DA"
    )

    font_family: str = (
        "Inter, Arial, sans-serif"
    )

    display_font_family: str = (
        "Inter, Arial, sans-serif"
    )

    logo_asset_path: str | None = None

    confidential: bool = True

    confidentiality_text: str = (
        "Private and Confidential"
    )


class AudioTrack(StrictBaseModel):
    """Narration audio attached to the video timeline."""

    source_path: str

    duration_seconds: float = Field(
        gt=0,
    )

    start_frame: int = Field(
        default=0,
        ge=0,
    )

    volume: float = Field(
        default=1.0,
        ge=0.0,
        le=2.0,
    )


class RenderEvent(StrictBaseModel):
    """A timed event within a scene."""

    event_id: str

    event_type: str

    start_frame: int = Field(
        ge=0,
    )

    duration_frames: int = Field(
        gt=0,
    )

    props: dict[str, Any] = Field(
        default_factory=dict,
    )


class RenderScene(StrictBaseModel):
    """
    One fully resolved scene consumed by the renderer.

    renderer_strategy controls the scene-resolution path.

    generated_component_key identifies the generated scene
    inside the stable generated component registry.
    """

    scene_id: str

    component: str

    renderer_strategy: Literal[
        "generated_component",
        "library_component",
        "generic_fallback",
    ] = "library_component"

    generated_component_key: (
        str | None
    ) = None

    variant: str = "default"

    start_frame: int = Field(
        ge=0,
    )

    duration_frames: int = Field(
        gt=0,
    )

    props: dict[str, Any] = Field(
        default_factory=dict,
    )

    events: list[RenderEvent] = Field(
        default_factory=list,
    )

    @property
    def end_frame(self) -> int:
        """Return the exclusive end frame."""

        return (
            self.start_frame
            + self.duration_frames
        )

    @model_validator(mode="after")
    def validate_renderer_strategy(
        self,
    ) -> "RenderScene":
        """
        Validate the generated-component contract.

        A generated scene must expose a registry key.
        """

        if (
            self.renderer_strategy
            == "generated_component"
            and not self.generated_component_key
        ):
            raise ValueError(
                "Scene "
                f"'{self.scene_id}' uses "
                "'generated_component' but does "
                "not define generated_component_key."
            )

        return self


class ResolvedAsset(StrictBaseModel):
    """Asset resolved for renderer consumption."""

    asset_id: str

    asset_type: str

    source_path: str

    renderer_path: str | None = None

    required: bool = True

    approved: bool = False

    alt_text: str | None = None


class RenderSpecification(StrictBaseModel):
    """Complete frame-level contract for video rendering."""

    schema_version: str = "2.0"

    render_id: str

    candidate_name: str

    video: RenderVideoSettings

    theme: ThemeSettings = Field(
        default_factory=ThemeSettings,
    )

    audio: AudioTrack

    scenes: list[RenderScene] = Field(
        min_length=1,
    )

    assets: list[ResolvedAsset] = Field(
        default_factory=list,
    )

    output_path: str

    metadata: dict[str, Any] = Field(
        default_factory=dict,
    )

    @model_validator(mode="after")
    def validate_render_timeline(
        self,
    ) -> "RenderSpecification":
        """
        Validate scene IDs, timeline boundaries,
        overlaps and generated component keys.
        """

        scene_ids = [
            scene.scene_id
            for scene in self.scenes
        ]

        if (
            len(scene_ids)
            != len(set(scene_ids))
        ):
            raise ValueError(
                "Render scene IDs must be unique."
            )

        generated_keys = [
            scene.generated_component_key
            for scene in self.scenes
            if (
                scene.renderer_strategy
                == "generated_component"
                and scene.generated_component_key
            )
        ]

        if (
            len(generated_keys)
            != len(set(generated_keys))
        ):
            raise ValueError(
                "Generated component keys "
                "must be unique."
            )

        ordered_scenes = sorted(
            self.scenes,
            key=lambda scene:
                scene.start_frame,
        )

        for index, scene in enumerate(
            ordered_scenes
        ):
            if (
                scene.end_frame
                > self.video.duration_frames
            ):
                raise ValueError(
                    f"Scene '{scene.scene_id}' "
                    "ends after the video."
                )

            if index > 0:
                previous_scene = (
                    ordered_scenes[
                        index - 1
                    ]
                )

                if (
                    scene.start_frame
                    < previous_scene.end_frame
                ):
                    raise ValueError(
                        f"Scene '{scene.scene_id}' "
                        "overlaps with "
                        f"'{previous_scene.scene_id}'."
                    )

        return self