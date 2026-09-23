"""Tests for Phase 3B artifact generation helpers."""

from app.services.artifact_generation_service import ArtifactGenerationService


def test_image_prompt_forbids_documentary_content():
    prompt = ArtifactGenerationService._build_image_prompt(
        {
            "visual_brief": "Abstract transformation visual.",
            "generation_constraints": [],
        }
    )
    assert "identifiable real person" in prompt
    assert "Do not include logos" in prompt


def test_recalculate_manifest():
    manifest = {
        "artifacts": [
            {"approved": True, "status": "approved"},
            {"approved": False, "status": "needs_review"},
            {"approved": False, "status": "failed"},
        ]
    }
    summary = ArtifactGenerationService._recalculate_manifest(manifest)
    assert summary["approved_count"] == 1
    assert summary["pending_review_count"] == 1
    assert summary["failed_count"] == 1
