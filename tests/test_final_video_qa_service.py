"""Tests for final-video QA policy and sampling."""
import json

from app.schemas.final_video_qa import FullVideoCohesionResult, FullVideoIssue
from app.pipeline.step_10b_final_dynamic_video_qa import _qa_output_directory
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
    manifest = {
        "scene_resolution": [
            {
                "scene_id": "scene_1",
                "start_seconds": 0.0,
                "end_seconds": 6.0,
                "resolved_strategy": "static_segment",
            },
            {
                "scene_id": "scene_2",
                "start_seconds": 6.0,
                "end_seconds": 30.0,
                "resolved_strategy": "generated_component",
            },
        ]
    }
    points = FinalVideoQAService._sample_points(30.0, manifest)

    assert len(points) == 4
    assert {item["scene_id"] for item in points} == {"scene_1", "scene_2"}
    assert {item["sample_role"] for item in points} == {
        "opening",
        "midpoint",
    }
    assert all(item["timestamp_seconds"] < 30.0 for item in points)


def test_scene_context_joins_planned_intent_and_render_resolution():
    context = FinalVideoQAService._scene_context(
        {
            "scene_resolution": [
                {
                    "scene_id": "scene_1",
                    "start_seconds": 0.0,
                    "end_seconds": 8.0,
                    "resolved_strategy": "generated_component",
                    "component_name": "ImpactScene",
                }
            ]
        },
        {
            "scenes": [
                {
                    "scene_id": "scene_1",
                    "approved_facts": ["Revenue grew 42%"],
                    "scene_architecture": {
                        "scene_purpose": "Show business impact",
                        "visual_story": "A metric transforms into a result",
                        "layout_intent": "An oversized central figure",
                        "focal_element": "Revenue growth",
                    },
                }
            ]
        },
    )

    assert context[0]["resolved_strategy"] == "generated_component"
    assert context[0]["scene_purpose"] == "Show business impact"
    assert context[0]["approved_facts"] == ["Revenue grew 42%"]


def test_low_aesthetic_score_fails_assessment_without_blocking_delivery():
    result = FullVideoCohesionResult(
        approved=False,
        overall_score=0.42,
        typography_consistency_score=0.5,
        palette_consistency_score=0.5,
        transition_cohesion_score=0.5,
        pacing_score=0.4,
        confidentiality_consistency_score=0.8,
        summary="Some subjective polish opportunities remain.",
    )

    updated = FinalVideoQAService._apply_policy(result)

    assert not updated.approved
    assert not updated.approved_with_warnings


def test_master_render_inputs_and_scene_boundaries(tmp_path):
    run_dir = tmp_path / "run"
    video_dir = run_dir / "09_video"
    spec_dir = run_dir / "08_render_spec"
    video_dir.mkdir(parents=True)
    spec_dir.mkdir()
    video_path = video_dir / "candidate_snapshot.mp4"
    video_path.write_bytes(b"video")
    (video_dir / "render_metadata.json").write_text(
        json.dumps(
            {
                "output_path": str(video_path),
                "result": {"return_code": 0},
            }
        ),
        encoding="utf-8",
    )
    render_spec = {
        "schema_version": "2.0",
        "video": {"fps": 30},
        "scenes": [
            {
                "scene_id": "scene_1",
                "component": "ImpactScene",
                "renderer_strategy": "generated_component",
                "generated_component_key": "scene_1",
                "start_frame": 0,
                "duration_frames": 120,
                "props": {
                    "approved_facts": ["Revenue grew 42%"],
                    "renderer_instructions": {
                        "scene_purpose": "Show commercial impact",
                        "visual_story": "A metric becomes a result",
                    },
                },
            }
        ],
    }
    (spec_dir / "render_spec.json").write_text(
        json.dumps(render_spec),
        encoding="utf-8",
    )

    resolved_video, manifest = FinalVideoQAService._resolve_render_inputs(
        run_dir
    )
    scene = manifest["scene_resolution"][0]
    context = FinalVideoQAService._scene_context(manifest, {})

    assert resolved_video == video_path
    assert scene["start_seconds"] == 0
    assert scene["end_seconds"] == 4
    assert scene["resolved_strategy"] == "generated_component"
    assert context[0]["scene_purpose"] == "Show commercial impact"
    assert context[0]["approved_facts"] == ["Revenue grew 42%"]


def test_master_render_qa_report_is_saved_with_master_video(tmp_path):
    master_metadata = tmp_path / "09_video" / "render_metadata.json"
    master_metadata.parent.mkdir(parents=True)
    master_metadata.write_text("{}", encoding="utf-8")

    assert _qa_output_directory(tmp_path) == (
        tmp_path / "09_video" / "final_qa"
    )


def test_dynamic_render_qa_report_uses_dynamic_video_directory(tmp_path):
    assert _qa_output_directory(tmp_path) == (
        tmp_path / "10_dynamic_render" / "final_qa"
    )


def test_visual_findings_are_reported_without_blocking_delivery(
    monkeypatch,
    tmp_path,
):
    run_dir = tmp_path / "run"
    render_dir = run_dir / "10_dynamic_render"
    render_dir.mkdir(parents=True)
    (render_dir / "candidate_video_dynamic.mp4").write_bytes(b"video")
    (render_dir / "render_summary.json").write_text(
        json.dumps({"ready_for_phase_7c": True}),
        encoding="utf-8",
    )
    manifest = {
        "scene_resolution": [
            {
                "scene_id": "scene_1",
                "start_seconds": 0.0,
                "end_seconds": 4.0,
                "resolved_strategy": "generated_component",
            }
        ]
    }
    (render_dir / "renderer_manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        FinalVideoQAService,
        "_probe",
        staticmethod(
            lambda path: {
                "format": {"duration": "4.0"},
                "streams": [
                    {"codec_type": "video"},
                    {"codec_type": "audio"},
                ],
            }
        ),
    )
    monkeypatch.setattr(
        FinalVideoQAService,
        "_extract_frames",
        staticmethod(
            lambda video, output, points, timeout: (
                [
                    {
                        **point,
                        "path": str(output / f"{point['label']}.png"),
                    }
                    for point in points
                ],
                [],
            )
        ),
    )
    monkeypatch.setattr(
        FinalVideoQAService,
        "_deterministic_checks",
        staticmethod(
            lambda video, probe, frames, errors, points, renderer: {
                "passed": True,
                "sampled_frame_count": len(frames),
                "scene_coverage": [
                    {
                        "scene_id": "scene_1",
                        "sampled_frame_count": len(frames),
                    }
                ],
            }
        ),
    )
    monkeypatch.setattr(
        FinalVideoQAService,
        "_run_cohesion_qa",
        lambda self, frames, technical, context: FullVideoCohesionResult(
            approved=True,
            overall_score=0.8,
            typography_consistency_score=0.8,
            palette_consistency_score=0.8,
            transition_cohesion_score=0.8,
            pacing_score=0.8,
            confidentiality_consistency_score=0.8,
            summary="A severe visual defect was found.",
            issues=[
                FullVideoIssue(
                    issue_id="missing-content",
                    category="render_failure",
                    severity="high",
                    description="The central scene content is missing.",
                    recommended_change="Correct the rendered scene.",
                )
            ],
        ),
    )

    report = FinalVideoQAService(api_key=None).review(
        run_dir,
        run_dir / "qa",
    )

    assert report["quality_concerns_found"]
    assert not report["ready_for_final_approval"]
    assert not report["delivery_blocked"]
    assert report["status"] == "visual_qa_complete_with_concerns"
