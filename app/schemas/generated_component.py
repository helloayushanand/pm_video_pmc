"""Schemas for generated Remotion components."""
from __future__ import annotations
from enum import Enum
from pydantic import BaseModel, ConfigDict, Field, model_validator

class StrictBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

class ComponentGenerationStatus(str, Enum):
    PENDING = "pending"
    GENERATED = "generated"
    SOURCE_VALID = "source_valid"
    SOURCE_INVALID = "source_invalid"
    READY_FOR_COMPILATION = "ready_for_compilation"
    FALLBACK = "fallback"
    FAILED = "failed"

class ApprovedArtifactReference(StrictBaseModel):
    artifact_id: str
    artifact_type: str
    renderer_path: str | None = None
    local_path: str | None = None
    approved: bool
    alt_text: str

class SceneGenerationInput(StrictBaseModel):
    run_id: str
    scene_id: str
    scene_type: str
    component_name: str
    fallback_component: str
    duration_hint_seconds: float = Field(gt=0)
    creative_direction: dict
    scene_architecture: dict
    approved_facts: list[str] = Field(default_factory=list)
    available_artifacts: list[ApprovedArtifactReference] = Field(default_factory=list)
    allowed_primitives: list[str] = Field(min_length=1)

class GeneratedComponentOutput(StrictBaseModel):
    scene_id: str
    component_name: str
    source_code: str = Field(min_length=50)
    used_primitives: list[str] = Field(min_length=1)
    used_artifacts: list[str] = Field(default_factory=list)
    generation_rationale: str
    expected_peak_frame_percentage: float = Field(ge=0, le=1)
    fallback_component: str

class SourceValidationIssue(StrictBaseModel):
    code: str
    message: str
    severity: str = "error"

class SourceValidationResult(StrictBaseModel):
    valid: bool
    issues: list[SourceValidationIssue] = Field(default_factory=list)
    discovered_imports: list[str] = Field(default_factory=list)
    discovered_artifacts: list[str] = Field(default_factory=list)

class GeneratedComponentManifest(StrictBaseModel):
    scene_id: str
    component_name: str
    source_file: str
    status: ComponentGenerationStatus
    used_primitives: list[str] = Field(default_factory=list)
    used_artifacts: list[str] = Field(default_factory=list)
    fallback_component: str
    expected_peak_frame_percentage: float = Field(ge=0, le=1)
    generation_attempts: int = Field(default=0, ge=0)
    repair_attempts: int = Field(default=0, ge=0)
    validation: SourceValidationResult | None = None

class ComponentGenerationPlan(StrictBaseModel):
    run_id: str
    scenes: list[SceneGenerationInput] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_scene_ids(self):
        ids = [scene.scene_id for scene in self.scenes]
        if len(ids) != len(set(ids)):
            raise ValueError("Scene IDs must be unique.")
        return self
