"""Tests for local pipeline utilities and state management."""

import run_pipeline
from app.pipeline.step_05d_generate_artifacts import build_argument_parser
from app.utils.files import (
    calculate_sha256,
    copy_file,
    safe_filename,
)
from app.utils.json_utils import load_json, save_json
from app.utils.run_manager import (
    PIPELINE_STEPS,
    RunManager,
    create_run,
)


def test_pipeline_uses_the_dedicated_visual_repair_model(monkeypatch, tmp_path):
    captured = {}

    def fake_repair_visual_components(**kwargs):
        captured.update(kwargs)
        return {"repaired_count": 0}

    monkeypatch.setattr(
        run_pipeline,
        "repair_visual_components",
        fake_repair_visual_components,
    )

    arguments = run_pipeline.build_argument_parser().parse_args(
        ["--input", "candidate.pdf"]
    )
    assert arguments.visual_repair_model == run_pipeline.settings.openai_visual_repair_model

    arguments.visual_repair_model = "gpt-5.3-codex"
    run_pipeline.execute_step(
        "repair_visual_components",
        tmp_path,
        arguments,
    )

    assert captured["model"] == "gpt-5.3-codex"


def test_standard_pipeline_generates_up_to_five_dynamic_scenes(monkeypatch, tmp_path):
    captured = {}

    def fake_generate_components(**kwargs):
        captured.update(kwargs)
        return {}

    monkeypatch.setattr(
        run_pipeline,
        "generate_components",
        fake_generate_components,
    )
    arguments = run_pipeline.build_argument_parser().parse_args(
        ["--input", "candidate.pdf"]
    )

    run_pipeline.execute_step("generate_components", tmp_path, arguments)

    assert captured["max_scenes"] == 5


def test_dynamic_render_runs_after_static_master_render():
    assert PIPELINE_STEPS.index("render_video") < PIPELINE_STEPS.index(
        "render_dynamic_video"
    )
    assert PIPELINE_STEPS.index("render_dynamic_video") < PIPELINE_STEPS.index(
        "final_dynamic_video_qa"
    )


def test_visual_repair_pass_revalidates_changed_sources_once(
    monkeypatch, tmp_path
):
    preview_path = (
        tmp_path / "05f_component_previews" / "preview_qa_report.json"
    )
    preview_path.parent.mkdir(parents=True)
    save_json(
        {"ready_for_phase_7": False, "results": [{"scene_id": "scene_01"}]},
        preview_path,
    )
    calls = []
    def fake_execute_step(step_name, run_directory, arguments):
        calls.append(step_name)
        if step_name == "repair_visual_components":
            return {"repaired_count": 1}
        if step_name == "preview_components":
            ready = True
            save_json(
                {
                    "ready_for_phase_7": ready,
                    "results": [
                        {
                            "scene_id": "scene_01",
                            "visual_approved": ready,
                        }
                    ],
                },
                preview_path,
            )
            return {"ready_for_phase_7": ready}
        return {}

    monkeypatch.setattr(run_pipeline, "execute_step", fake_execute_step)
    arguments = run_pipeline.build_argument_parser().parse_args(
        ["--run-dir", str(tmp_path)]
    )

    report = run_pipeline.run_visual_repair_pass(tmp_path, arguments)

    assert report == {"repair_passes": 1, "ready_for_phase_7": True}
    assert calls == [
        "repair_visual_components",
        "review_components",
        "compile_components",
        "repair_compiler_errors",
        "preview_components",
    ]


def test_visual_repair_pass_stops_when_no_source_was_repaired(
    monkeypatch, tmp_path
):
    preview_path = (
        tmp_path / "05f_component_previews" / "preview_qa_report.json"
    )
    preview_path.parent.mkdir(parents=True)
    save_json(
        {"ready_for_phase_7": False, "results": [{"scene_id": "scene_01"}]},
        preview_path,
    )
    calls = []

    def fake_execute_step(step_name, run_directory, arguments):
        calls.append(step_name)
        return {
            "repaired_count": 0,
            "skipped": [
                {
                    "scene_id": "scene_01",
                    "reason": "visual_repair_attempt_limit_reached",
                }
            ],
            "failed": [],
        }

    monkeypatch.setattr(run_pipeline, "execute_step", fake_execute_step)
    arguments = run_pipeline.build_argument_parser().parse_args(
        ["--run-dir", str(tmp_path)]
    )

    try:
        run_pipeline.run_visual_repair_pass(tmp_path, arguments)
    except RuntimeError as error:
        assert "visual_repair_attempt_limit_reached" in str(error)
    else:
        raise AssertionError("The repair loop should stop when no source changes.")

    assert calls == ["repair_visual_components"]


def test_artifact_cli_generates_images_by_default_and_can_skip():
    parser = build_argument_parser()

    defaults = parser.parse_args(["--run-dir", "run"])
    skipped = parser.parse_args(
        ["--run-dir", "run", "--skip-image-generation"]
    )

    assert defaults.generate_images is True
    assert skipped.generate_images is False


def test_save_and_load_json(tmp_path):
    source_data = {
        "candidate": "Test Candidate",
        "status": "created",
    }

    output_path = tmp_path / "test.json"

    save_json(
        source_data,
        output_path,
    )

    loaded_data = load_json(output_path)

    assert loaded_data == source_data


def test_safe_filename_removes_unsafe_characters():
    filename = safe_filename(
        "Candidate Dossier - Test Person (Final).PDF"
    )

    assert filename == (
        "Candidate_Dossier_-_Test_Person_Final.pdf"
    )


def test_calculate_sha256_is_repeatable(tmp_path):
    test_file = tmp_path / "sample.txt"

    test_file.write_text(
        "candidate pipeline",
        encoding="utf-8",
    )

    first_hash = calculate_sha256(test_file)
    second_hash = calculate_sha256(test_file)

    assert first_hash == second_hash
    assert len(first_hash) == 64


def test_copy_file_preserves_content(tmp_path):
    source = tmp_path / "source.txt"
    destination = tmp_path / "nested" / "destination.txt"

    source.write_text(
        "confidential candidate data",
        encoding="utf-8",
    )

    copied_path = copy_file(
        source=source,
        destination=destination,
    )

    assert copied_path.exists()
    assert copied_path.read_text(
        encoding="utf-8"
    ) == "confidential candidate data"


def test_create_run_creates_expected_directories(tmp_path):
    run_directory = create_run(
        input_filename="candidate.pdf",
        configuration={
            "video_mode": "automatic",
            "include_compensation": False,
        },
        runs_directory=tmp_path,
    )

    expected_directories = [
        "00_input",
        "01_document",
        "02_extraction",
        "03_validation",
        "04_video_content",
        "05_storyboard",
        "06_audio",
        "07_alignment",
        "08_render_spec",
        "09_video",
        "10_quality",
        "logs",
    ]

    for directory_name in expected_directories:
        assert (
            run_directory / directory_name
        ).is_dir()

    state = load_json(
        run_directory / "run.json"
    )

    assert state["input_file"] == "candidate.pdf"
    assert state["status"] == "CREATED"
    assert state["configuration"]["video_mode"] == (
        "automatic"
    )


def test_run_manager_updates_step_status(tmp_path):
    run_directory = create_run(
        input_filename="candidate.pdf",
        runs_directory=tmp_path,
    )

    manager = RunManager(run_directory)

    manager.start_step("prepare_document")

    running_state = manager.state

    assert running_state["status"] == "RUNNING"
    assert running_state["current_step"] == (
        "prepare_document"
    )
    assert (
        running_state["steps"]["prepare_document"]["status"]
        == "running"
    )

    manager.complete_step(
        "prepare_document",
        outputs={
            "page_count": 4,
        },
    )

    completed_state = manager.state

    assert (
        completed_state["steps"]["prepare_document"]["status"]
        == "completed"
    )

    assert (
        completed_state["steps"]["prepare_document"]["outputs"]
        ["page_count"]
        == 4
    )


def test_run_manager_records_failure(tmp_path):
    run_directory = create_run(
        input_filename="candidate.pdf",
        runs_directory=tmp_path,
    )

    manager = RunManager(run_directory)

    manager.start_step("extract_dossier")

    manager.fail_step(
        "extract_dossier",
        "Test extraction error",
    )

    state = manager.state

    assert (
        state["steps"]["extract_dossier"]["status"]
        == "failed"
    )

    assert (
        state["steps"]["extract_dossier"]["error"]
        == "Test extraction error"
    )
