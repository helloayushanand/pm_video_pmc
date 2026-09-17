"""Tests for the pipeline Pydantic schemas."""

import pytest
from pydantic import ValidationError

from app.schemas.dossier import (
    CandidateProfile,
    CareerHighlight,
    Dossier,
    DossierMetadata,
    SourceReference,
)
from app.schemas.render_spec import (
    AudioTrack,
    RenderScene,
    RenderSpecification,
    RenderVideoSettings,
)
from app.schemas.storyboard import (
    SceneType,
    Storyboard,
    StoryboardScene,
    VisualElement,
    VisualElementType,
    VoiceoverSegment,
)
from app.schemas.video_content import (
    CandidateIntroduction,
    VideoContent,
)


def test_minimum_dossier_is_valid():
    dossier = Dossier(
        metadata=DossierMetadata(
            document_id="doc_test",
            original_filename="candidate.pdf",
            page_count=2,
        ),
        candidate=CandidateProfile(
            full_name="Test Candidate",
        ),
    )

    assert dossier.candidate.full_name == "Test Candidate"
    assert dossier.metadata.page_count == 2
    assert dossier.career_history == []
    assert dossier.career_highlights == []


def test_dossier_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        Dossier(
            candidate=CandidateProfile(
                full_name="Test Candidate",
            ),
            unsupported_field="unsupported",
        )


def test_source_reference_page_must_be_positive():
    with pytest.raises(ValidationError):
        SourceReference(
            page_number=0,
            confidence=0.9,
        )


def test_source_reference_confidence_range():
    with pytest.raises(ValidationError):
        SourceReference(
            page_number=1,
            confidence=1.5,
        )


def test_career_highlight_defaults_to_video_eligible():
    highlight = CareerHighlight(
        statement="Led a major transformation programme.",
        source_references=[
            SourceReference(
                page_number=3,
                confidence=0.95,
            )
        ],
    )

    assert highlight.video_eligible is True


def test_minimum_video_content_is_valid():
    content = VideoContent(
        candidate_intro=CandidateIntroduction(
            name="Test Candidate",
            title="Chief Executive",
            company="Example Company",
        ),
        executive_summary=(
            "An experienced executive with cross-functional "
            "leadership experience."
        ),
    )

    assert content.candidate_intro.name == "Test Candidate"
    assert content.recommended_duration_seconds == 45.0


def test_storyboard_generates_complete_voiceover():
    storyboard = Storyboard(
        title="Candidate Snapshot",
        candidate_name="Test Candidate",
        scenes=[
            StoryboardScene(
                scene_id="scene_01",
                scene_type=SceneType.CANDIDATE_INTRO,
                purpose="Introduce the candidate",
                estimated_duration_seconds=4.0,
                voiceover_segments=[
                    VoiceoverSegment(
                        segment_id="segment_01",
                        text="Meet Test Candidate.",
                    )
                ],
                visual_elements=[
                    VisualElement(
                        element_id="element_01",
                        element_type=VisualElementType.HEADING,
                        content="Test Candidate",
                    )
                ],
            ),
            StoryboardScene(
                scene_id="scene_02",
                scene_type=SceneType.CLOSING,
                purpose="Close the video",
                estimated_duration_seconds=2.0,
                voiceover_segments=[
                    VoiceoverSegment(
                        segment_id="segment_02",
                        text=(
                            "Full candidate dossier shared separately."
                        ),
                    )
                ],
            ),
        ],
    )

    assert storyboard.estimated_total_duration_seconds == 6.0
    assert storyboard.complete_voiceover == (
        "Meet Test Candidate. "
        "Full candidate dossier shared separately."
    )


def test_storyboard_rejects_duplicate_scene_ids():
    with pytest.raises(ValidationError):
        Storyboard(
            title="Candidate Snapshot",
            candidate_name="Test Candidate",
            scenes=[
                StoryboardScene(
                    scene_id="scene_01",
                    scene_type=SceneType.CANDIDATE_INTRO,
                    purpose="Introduction",
                    estimated_duration_seconds=4.0,
                ),
                StoryboardScene(
                    scene_id="scene_01",
                    scene_type=SceneType.CLOSING,
                    purpose="Closing",
                    estimated_duration_seconds=2.0,
                ),
            ],
        )


def test_render_specification_accepts_sequential_scenes():
    specification = RenderSpecification(
        render_id="render_test",
        candidate_name="Test Candidate",
        video=RenderVideoSettings(
            width=1920,
            height=1080,
            fps=30,
            duration_frames=180,
        ),
        audio=AudioTrack(
            source_path="voiceover.mp3",
            duration_seconds=6.0,
        ),
        scenes=[
            RenderScene(
                scene_id="scene_01",
                component="CandidateIntro",
                start_frame=0,
                duration_frames=120,
            ),
            RenderScene(
                scene_id="scene_02",
                component="ClosingScene",
                start_frame=120,
                duration_frames=60,
            ),
        ],
        output_path="candidate_snapshot.mp4",
    )

    assert specification.video.duration_frames == 180
    assert specification.scenes[1].end_frame == 180


def test_render_specification_rejects_overlapping_scenes():
    with pytest.raises(ValidationError):
        RenderSpecification(
            render_id="render_test",
            candidate_name="Test Candidate",
            video=RenderVideoSettings(
                duration_frames=180,
            ),
            audio=AudioTrack(
                source_path="voiceover.mp3",
                duration_seconds=6.0,
            ),
            scenes=[
                RenderScene(
                    scene_id="scene_01",
                    component="CandidateIntro",
                    start_frame=0,
                    duration_frames=120,
                ),
                RenderScene(
                    scene_id="scene_02",
                    component="ClosingScene",
                    start_frame=100,
                    duration_frames=60,
                ),
            ],
            output_path="candidate_snapshot.mp4",
        )
