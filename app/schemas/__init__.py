"""Pydantic schemas used throughout the candidate video pipeline."""

from app.schemas.dossier import (
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
    Storyboard,
    StoryboardScene,
    VisualElement,
    VoiceoverSegment,
)
from app.schemas.video_content import (
    CandidateIntroduction,
    SelectedCareerMilestone,
    SelectedHighlight,
    VideoContent,
)

__all__ = [
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
