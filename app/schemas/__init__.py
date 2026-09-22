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
from app.schemas.render_spec import (
    AudioTrack,
    RenderScene,
    RenderSpecification,
    RenderVideoSettings,
    ThemeSettings,
)

from app.schemas.storyboard import (
    PronunciationHint,
    Storyboard,
    StoryboardScene,
    VisualElement,
    VisualMetadataItem,
    VoiceoverSegment,
)

from app.schemas.video_content import (
    CandidateIntroduction,
    SelectedCareerMilestone,
    SelectedHighlight,
    VideoContent,
)

__all__ = [
    "PronunciationHint",
    "VisualMetadataItem",
    "AdditionalSection",
    "Assessment",
    "Assessment",
    "AudioTrack",
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
    "RenderScene",
    "RenderSpecification",
    "RenderVideoSettings",
    "SelectedCareerMilestone",
    "SelectedHighlight",
    "SensitiveInformation",
    "SourceReference",
    "Storyboard",
    "StoryboardScene",
    "ThemeSettings",
    "VideoContent",
    "VisualElement",
    "VoiceoverSegment",
]
