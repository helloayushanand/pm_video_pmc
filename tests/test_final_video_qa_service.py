"""Tests for final-video QA policy and sampling."""
from app.schemas.final_video_qa import FullVideoCohesionResult, FullVideoIssue
from app.services.final_video_qa_service import FinalVideoQAService


def test_medium_aesthetic_issue_is_warning():
    result = FullVideoCohesionResult(
        approved=False,
        overall_score=0.82,
        typography_consistency_score=0.8,
        palette_consistency_score=0.8,
        transition_cohesion_score=0.78,
        pacing_score=0.75,
        confidentiality_consistency_score=0.8,
        summary="Good demo with a minor spacing concern.",
        issues=[FullVideoIssue(issue_id="spacing", category="layout", severity="medium", blocking=False, description="Minor spacing issue.", recommended_change="Polish spacing.")],
    )
    updated = FinalVideoQAService._apply_policy(result)
    assert updated.approved
    assert updated.approved_with_warnings
    assert updated.blocking_issue_count == 0


def test_high_issue_blocks():
    result = FullVideoCohesionResult(
        approved=True,
        overall_score=0.9,
        typography_consistency_score=0.9,
        palette_consistency_score=0.9,
        transition_cohesion_score=0.9,
        pacing_score=0.9,
        confidentiality_consistency_score=0.9,
        summary="Contains a factual issue.",
        issues=[FullVideoIssue(issue_id="fact", category="factual integrity", severity="high", description="Wrong title.", recommended_change="Correct title.")],
    )
    assert not FinalVideoQAService._apply_policy(result).approved


def test_sample_points_include_boundary():
    manifest = {"scene_resolution": [{"end_seconds": 6.0}]}
    labels = {item["label"] for item in FinalVideoQAService._sample_points(30.0, manifest)}
    assert "before_intro_boundary" in labels
    assert "after_intro_boundary" in labels
