import json

from app.schemas.generated_component import (
    GeneratedComponentOutput,
    SourceValidationResult,
)
from app.services import visual_component_repair_service as repair_module
from app.services.visual_component_repair_service import (
    VisualComponentRepairService,
)


def _make_repair_inputs(run_dir, preview_result):
    generation_dir = run_dir / "05d_generated_components"
    preview_dir = run_dir / "05f_component_previews"
    generation_dir.mkdir(parents=True)
    preview_dir.mkdir(parents=True)
    source_path = generation_dir / "scene.tsx"
    source_path.write_text(
        "export const Scene = () => <div>before visual repair test output</div>;",
        encoding="utf-8",
    )
    component = GeneratedComponentOutput(
        scene_id="scene_01",
        component_name="Scene",
        source_code=source_path.read_text(encoding="utf-8"),
        used_primitives=["SceneFrame"],
        generation_rationale="Test component",
        expected_peak_frame_percentage=0.65,
        fallback_component="FallbackScene",
    )
    (generation_dir / "generation_plan.json").write_text(
        json.dumps(
            {
                "scenes": [
                    {
                        "run_id": "run",
                        "scene_id": "scene_01",
                        "scene_type": "timeline",
                        "component_name": "Scene",
                        "fallback_component": "FallbackScene",
                        "duration_hint_seconds": 8,
                        "creative_direction": {},
                        "scene_architecture": {},
                        "approved_facts": [],
                        "allowed_primitives": ["SceneFrame"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (generation_dir / "generation_results.json").write_text(
        json.dumps(
            [
                {
                    "scene_id": "scene_01",
                    "source_file": str(source_path),
                    "generated_component": component.model_dump(mode="json"),
                }
            ]
        ),
        encoding="utf-8",
    )
    (preview_dir / "preview_qa_report.json").write_text(
        json.dumps({"results": [preview_result]}),
        encoding="utf-8",
    )
    return source_path


def test_visual_repair_calls_generator_once_and_updates_source(
    monkeypatch, tmp_path
):
    source_path = _make_repair_inputs(
        tmp_path,
        {
            "scene_id": "scene_01",
            "status": "visual_repair_required",
            "visual_approved": False,
            "visual_qa": {
                "summary": "Timeline labels are missing.",
                "issues": [
                    {
                        "description": "Milestone labels are not visible.",
                        "recommended_change": "Render labels.",
                        "severity": "high",
                    }
                ],
                "required_changes": ["Show the milestone labels."],
            },
        },
    )
    calls = []

    class FakeAgent:
        def repair(self, scene_input, component, validation):
            calls.append(validation)
            repaired = component.model_copy(
                update={
                    "source_code": (
                        "export const Scene = () => <div>fixed timeline labels</div>;"
                    )
                }
            )
            return repaired, {"attempt": len(calls)}

    monkeypatch.setattr(
        repair_module,
        "validate_generated_source",
        lambda *args: SourceValidationResult(valid=True),
    )
    service = VisualComponentRepairService()
    service.agent = FakeAgent()

    report = service.repair(tmp_path)

    assert len(calls) == 1
    assert report["repaired_count"] == 1
    assert report["failed_count"] == 0
    assert "fixed timeline labels" in source_path.read_text(encoding="utf-8")


def test_visual_repair_skips_unassessed_scene(tmp_path):
    _make_repair_inputs(
        tmp_path,
        {
            "scene_id": "scene_01",
            "status": "runtime_smoke_passed_unassessed",
            "visual_approved": False,
            "visual_qa": None,
        },
    )
    service = VisualComponentRepairService()

    report = service.repair(tmp_path)

    assert report["repaired_count"] == 0
    assert report["skipped"][0]["reason"] == "visual_assessment_unavailable"
