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


def test_design_quality_rejects_default_card_stack():
    source = """
    import React from 'react';
    export const WeakScene = () => (
      <div>
        <div><MetricCard /></div>
        <div><MetricCard /></div>
        <div><MetricCard /></div>
        <div><MetricCard /></div>
      </div>
    );
    """
    quality = ComponentReviewService._evaluate_design_quality(source, {})
    assert quality["passed"] is False
    assert quality["score"] < 0.6


def test_design_quality_accepts_composed_scene_structure():
    source = """
    import React from 'react';
    import type {GeneratedSceneProps} from '@/dynamic-sdk';
    export const StrongScene: React.FC<GeneratedSceneProps> = ({context}) => (
      <SceneFrame theme={context.theme}>
        <SafeArea>
          <Stack direction='column' gap={16}>
            <SectionLabel theme={context.theme}>Performance</SectionLabel>
            <SplitLayout>
              <MetricValue value='42%' />
              <BodyCopy>Revenue growth</BodyCopy>
            </SplitLayout>
          </Stack>
        </SafeArea>
      </SceneFrame>
    );
    """
    quality = ComponentReviewService._evaluate_design_quality(source, {})
    assert quality["passed"] is True
    assert quality["score"] >= 0.6


def test_design_quality_action_is_retry_for_borderline_scene():
    score = 0.68
    assert ComponentReviewService._quality_action_for_score(score) == "retry"


def test_design_quality_action_is_reject_for_weak_scene():
    score = 0.4
    assert ComponentReviewService._quality_action_for_score(score) == "reject"
