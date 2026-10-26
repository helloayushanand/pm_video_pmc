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
    frames_dir = preview_dir / "frames"
    frames_dir.mkdir()
    frames = []
    for label, frame in (
        ("early", 18),
        ("middle", 81),
        ("peak", 108),
        ("late", 162),
    ):
        frame_path = frames_dir / f"{label}.png"
        frame_path.write_bytes(f"preview-{label}".encode("ascii"))
        frames.append(
            {
                "label": label,
                "frame": frame,
                "path": str(frame_path),
            }
        )
    preview_report = json.loads(
        (preview_dir / "preview_qa_report.json").read_text(
            encoding="utf-8"
        )
    )
    preview_report["results"][0]["frames"] = frames
    (preview_dir / "preview_qa_report.json").write_text(
        json.dumps(preview_report),
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
                        "category": "text_clipping",
                    }
                ],
                "required_changes": ["Show the milestone labels."],
            },
        },
    )
    calls = []

    class FakeAgent:
        def repair(self, scene_input, component, validation, visual_frames=None):
            calls.append((scene_input, validation, visual_frames))
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
    assert calls[0][0].scene_architecture["visual_repair_guidance"][
        "approved_artifact_ids"
    ] == []
    assert calls[0][0].scene_architecture["visual_repair_guidance"][
        "fallback_strategy"
    ] == "FallbackScene"
    assert "complete essential text is visible" in calls[0][0].scene_architecture[
        "visual_repair_guidance"
    ]["issue_specific_repair_actions"][0]
    assert len(calls[0][2]) == 4
    assert calls[0][2][0]["label"] == "early"
    assert calls[0][2][0]["image_url"].startswith(
        "data:image/png;base64,"
    )
    assert report["repaired_count"] == 1
    assert report["failed_count"] == 0
    assert "fixed timeline labels" in source_path.read_text(encoding="utf-8")


def test_visual_repair_fails_closed_when_qa_frames_are_missing(
    tmp_path,
):
    source_path = _make_repair_inputs(
        tmp_path,
        {
            "scene_id": "scene_01",
            "status": "visual_repair_required",
            "visual_approved": False,
            "visual_qa": {
                "issues": [{"description": "Title overlaps the metric."}],
            },
        },
    )
    preview_path = (
        tmp_path
        / "05f_component_previews"
        / "preview_qa_report.json"
    )
    preview = json.loads(preview_path.read_text(encoding="utf-8"))
    preview["results"][0]["frames"] = []
    preview_path.write_text(json.dumps(preview), encoding="utf-8")

    class FakeAgent:
        def repair(self, *args, **kwargs):
            raise AssertionError("Repair must not run without rendered frames.")

    service = VisualComponentRepairService.__new__(
        VisualComponentRepairService
    )
    service.agent = FakeAgent()

    report = service.repair(tmp_path)

    assert report["repaired_count"] == 0
    assert report["failed"][0]["reason"] == "visual_qa_frames_missing"
    assert "before visual repair test output" in source_path.read_text(
        encoding="utf-8"
    )


def test_visual_repair_rejects_unapproved_artifact_references(tmp_path):
    source_path = _make_repair_inputs(
        tmp_path,
        {
            "scene_id": "scene_01",
            "status": "visual_repair_required",
            "visual_approved": False,
            "visual_qa": {
                "issues": [
                    {
                        "description": "A regional map visual is missing.",
                        "recommended_change": "Add the map.",
                    }
                ],
            },
        },
    )
    original_source = source_path.read_text(encoding="utf-8")

    class FakeAgent:
        def repair(self, scene_input, component, validation, visual_frames=None):
            repaired = component.model_copy(
                update={
                    "source_code": (
                        component.source_code
                        + '\nconst rejectedAsset = { artifactId: "S5_A2" };'
                    ),
                    "used_artifacts": ["S5_A2"],
                }
            )
            return repaired, {"attempt": 1}

    service = VisualComponentRepairService.__new__(
        VisualComponentRepairService
    )
    service.agent = FakeAgent()

    report = service.repair(tmp_path)

    assert report["repaired_count"] == 0
    assert report["failed_count"] == 1
    assert "Unapproved artifact: S5_A2" in report["failed"][0]["issues"]
    assert source_path.read_text(encoding="utf-8") == original_source


def test_visual_repair_uses_dedicated_model_setting(monkeypatch):
    captured = {}

    class FakeAgent:
        def __init__(self, model):
            captured["model"] = model

    monkeypatch.setattr(
        repair_module,
        "settings",
        type("Settings", (), {"openai_visual_repair_model": "gpt-5"})(),
    )
    monkeypatch.setattr(
        repair_module,
        "ComponentGenerationAgent",
        FakeAgent,
    )

    VisualComponentRepairService()

    assert captured["model"] == "gpt-5"


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


def test_visual_repair_stops_at_attempt_limit(tmp_path):
    _make_repair_inputs(
        tmp_path,
        {
            "scene_id": "scene_01",
            "status": "visual_repair_required",
            "visual_approved": False,
            "visual_qa": {
                "summary": "The scene still has layout issues.",
                "issues": [],
                "required_changes": ["Fix the layout."],
            },
        },
    )
    generation_results_path = (
        tmp_path
        / "05d_generated_components"
        / "generation_results.json"
    )
    generation_results = json.loads(
        generation_results_path.read_text(encoding="utf-8")
    )
    generation_results[0]["visual_repair_attempts"] = (
        VisualComponentRepairService.MAX_REPAIR_ATTEMPTS
    )
    generation_results_path.write_text(
        json.dumps(generation_results),
        encoding="utf-8",
    )

    service = VisualComponentRepairService()
    service.agent = None

    report = service.repair(tmp_path)

    assert report["repaired_count"] == 0
    assert report["skipped"][0]["reason"] == (
        "visual_repair_attempt_limit_reached"
    )


def test_visual_repair_guidance_targets_low_contrast_reveal(
    monkeypatch, tmp_path
):
    _make_repair_inputs(
        tmp_path,
        {
            "scene_id": "scene_01",
            "status": "visual_repair_required",
            "visual_approved": False,
            "visual_qa": {
                "issues": [
                    {
                        "category": "contrast_failure",
                        "severity": "low",
                        "description": "Caption appears faint during reveal.",
                        "recommended_change": "Keep caption readable throughout.",
                    }
                ],
            },
        },
    )
    captured = {}

    class FakeAgent:
        def repair(self, scene_input, component, validation, visual_frames=None):
            captured.update(scene_input.scene_architecture["visual_repair_guidance"])
            return component.model_copy(
                update={"source_code": component.source_code + "\n// fixed"}
            ), {}

    monkeypatch.setattr(
        repair_module,
        "validate_generated_source",
        lambda *args: SourceValidationResult(valid=True),
    )
    service = VisualComponentRepairService.__new__(VisualComponentRepairService)
    service.agent = FakeAgent()

    report = service.repair(tmp_path)

    assert report["repaired_count"] == 1
    assert "FadeReveal" in captured["issue_specific_repair_actions"][0]


def test_visual_repair_rejects_unchanged_source_and_consumes_attempt(
    tmp_path,
):
    source_path = _make_repair_inputs(
        tmp_path,
        {
            "scene_id": "scene_01",
            "status": "visual_repair_required",
            "visual_approved": False,
            "visual_qa": {
                "issues": [
                    {
                        "category": "contrast_failure",
                        "severity": "high",
                        "description": "Supporting text is faint.",
                    }
                ],
            },
        },
    )
    original_source = source_path.read_text(encoding="utf-8")

    class FakeAgent:
        def repair(self, scene_input, component, validation, visual_frames=None):
            return component, {}

    service = VisualComponentRepairService.__new__(VisualComponentRepairService)
    service.agent = FakeAgent()

    report = service.repair(tmp_path)
    results_path = (
        tmp_path
        / "05d_generated_components"
        / "generation_results.json"
    )
    results = json.loads(results_path.read_text(encoding="utf-8"))

    assert report["repaired_count"] == 0
    assert report["failed"][0]["reason"] == "visual_repair_unchanged_source"
    assert results[0]["visual_repair_attempts"] == 1
    assert source_path.read_text(encoding="utf-8") == original_source
