"""Pydantic schemas used throughout the candidate video pipeline."""

from app.schemas.dossier import (
    AdditionalSection,
    Assessment,
    Availability,
    CandidateProfile,
    CareerEntry,
    CareerHighlight,
    Compensation,
    Dossier,
    LeadershipScope,
    MediaAsset,
    OrganisationStructure,
    SensitiveInformation,
    SourceReference,
)

from app.schemas.video_content import (
    CandidateIntroduction,
    SelectedCareerMilestone,
    SelectedHighlight,
    VideoContent,
)

from app.schemas.scene_dsl import (
    ArtifactSpec,
    SceneSpec,
    VideoSpec,
)

__all__ = [
    "AdditionalSection",
    "ArtifactSpec",
    "Assessment",
    "Availability",
    "CandidateIntroduction",
    "CandidateProfile",
    "CareerEntry",
    "CareerHighlight",
    "Compensation",
    "Dossier",
    "LeadershipScope",
    "MediaAsset",
    "OrganisationStructure",
    "SceneSpec",
    "SelectedCareerMilestone",
    "SelectedHighlight",
    "SensitiveInformation",
    "SourceReference",
    "VideoContent",
    "VideoSpec",
]
