"""Tests for generated-component review decisions."""

from app.services.component_review_service import ComponentReviewService


def test_pending_without_approval():
    assert (
        ComponentReviewService._evaluate_approval(
            approval=None,
            source_hash="abc",
            validation_passed=True,
            source_exists=True,
        )
        == "pending_review"
    )


def test_stale_approval():
    assert (
        ComponentReviewService._evaluate_approval(
            approval={
                "approved": True,
                "decision": "approved_for_compilation",
                "source_sha256": "old",
            },
            source_hash="new",
            validation_passed=True,
            source_exists=True,
        )
        == "stale_approval"
    )


def test_valid_approval():
    assert (
        ComponentReviewService._evaluate_approval(
            approval={
                "approved": True,
                "decision": "approved_for_compilation",
                "source_sha256": "same",
            },
            source_hash="same",
            validation_passed=True,
            source_exists=True,
        )
        == "approved"
    )
