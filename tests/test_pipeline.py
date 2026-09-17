"""Tests for local pipeline utilities and state management."""

from pathlib import Path

from app.utils.files import (
    calculate_sha256,
    copy_file,
    safe_filename,
)
from app.utils.json_utils import load_json, save_json
from app.utils.run_manager import (
    RunManager,
    create_run,
)


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
