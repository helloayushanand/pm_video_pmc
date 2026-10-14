"""Tests for the demo orchestrator helpers."""
import argparse
import json
import subprocess

import run_demo_pipeline


def test_final_video_qa_is_enabled_by_default_and_can_be_skipped():
    parser = run_demo_pipeline.build_parser()

    defaults = parser.parse_args(["--run-dir", "run"])
    skipped = parser.parse_args(["--run-dir", "run", "--skip-final-qa"])
    preview_skipped = parser.parse_args(
        ["--run-dir", "run", "--skip-preview-qa"]
    )

    assert defaults.final_qa is True
    assert skipped.final_qa is False
    assert defaults.preview_qa is True
    assert preview_skipped.preview_qa is False


def test_resolve_run_prepares_content_without_running_legacy_pipeline(
    monkeypatch, tmp_path
):
    source = tmp_path / "candidate.pdf"
    source.write_bytes(b"pdf")
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    received = {}

    def fake_run(command, **kwargs):
        received["command"] = command
        content_dir = run_dir / "04_video_content"
        content_dir.mkdir(parents=True)
        (content_dir / "video_content.json").write_text(
            "{}",
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(run_demo_pipeline.subprocess, "run", fake_run)
    monkeypatch.setattr(run_demo_pipeline, "newest_run", lambda: run_dir)

    result = run_demo_pipeline.resolve_run(
        argparse.Namespace(input=str(source), run_dir=None)
    )

    assert result == run_dir
    assert received["command"][-2:] == ["--to-step", "select_video_content"]


def test_resolve_existing_run_completes_content_selection_prerequisites(
    monkeypatch,
    tmp_path,
):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    received = {}

    def fake_run(command, **kwargs):
        received["command"] = command
        content_dir = run_dir / "04_video_content"
        content_dir.mkdir(parents=True)
        (content_dir / "video_content.json").write_text(
            "{}",
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(run_demo_pipeline.subprocess, "run", fake_run)

    result = run_demo_pipeline.resolve_run(
        argparse.Namespace(input=None, run_dir=str(run_dir))
    )

    assert result == run_dir
    assert received["command"][-2:] == ["--to-step", "select_video_content"]


def test_resolve_existing_run_skips_completed_content_selection(
    monkeypatch,
    tmp_path,
):
    run_dir = tmp_path / "run"
    content_dir = run_dir / "04_video_content"
    content_dir.mkdir(parents=True)
    (content_dir / "video_content.json").write_text("{}", encoding="utf-8")

    def unexpected_run(*args, **kwargs):
        raise AssertionError("Existing content selection should be reused.")

    monkeypatch.setattr(run_demo_pipeline.subprocess, "run", unexpected_run)

    result = run_demo_pipeline.resolve_run(
        argparse.Namespace(input=None, run_dir=str(run_dir))
    )

    assert result == run_dir


def test_ensure_storyboard_generates_missing_prerequisite(
    monkeypatch,
    tmp_path,
):
    calls = []

    def fake_pipeline_step(run_dir, alias, allowed_codes=(0,)):
        calls.append(alias)
        storyboard_path = run_dir / "05_storyboard" / "storyboard.json"
        storyboard_path.parent.mkdir(parents=True)
        storyboard_path.write_text("{}", encoding="utf-8")
        return 0

    monkeypatch.setattr(
        run_demo_pipeline,
        "pipeline_step",
        fake_pipeline_step,
    )

    run_demo_pipeline.ensure_storyboard(tmp_path)

    assert calls == ["storyboard"]


def test_ensure_storyboard_reuses_existing_output(
    monkeypatch,
    tmp_path,
):
    storyboard_path = tmp_path / "05_storyboard" / "storyboard.json"
    storyboard_path.parent.mkdir(parents=True)
    storyboard_path.write_text("{}", encoding="utf-8")

    def unexpected_step(*args, **kwargs):
        raise AssertionError("Existing storyboard should be reused.")

    monkeypatch.setattr(
        run_demo_pipeline,
        "pipeline_step",
        unexpected_step,
    )

    run_demo_pipeline.ensure_storyboard(tmp_path)


def test_new_demo_run_executes_prerequisites_in_order(
    monkeypatch,
    tmp_path,
):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    calls = []

    def fake_pipeline_step(path, alias, allowed_codes=(0,)):
        calls.append(alias)
        if alias == "storyboard":
            output = path / "05_storyboard"
            output.mkdir(parents=True, exist_ok=True)
            (output / "storyboard.json").write_text("{}", encoding="utf-8")
        elif alias == "creative_plan":
            output = path / "05b_creative_plan"
            output.mkdir(parents=True, exist_ok=True)
            (output / "creative_plan.json").write_text(
                json.dumps({"draft": {"scene_briefs": []}}),
                encoding="utf-8",
            )
        elif alias == "artifacts":
            output = path / "05c_artifacts"
            output.mkdir(parents=True, exist_ok=True)
            (output / "artifact_manifest.json").write_text(
                json.dumps({"artifacts": []}),
                encoding="utf-8",
            )
        return 0

    def fake_run_command(command, allowed_codes=(0,)):
        calls.append("generate_artifacts")
        manifest = run_dir / "05c_artifacts" / "artifact_manifest_final.json"
        manifest.write_text(json.dumps({"artifacts": []}), encoding="utf-8")
        return 0

    monkeypatch.setattr(run_demo_pipeline, "resolve_run", lambda args: run_dir)
    monkeypatch.setattr(run_demo_pipeline, "pipeline_step", fake_pipeline_step)
    monkeypatch.setattr(run_demo_pipeline, "run_command", fake_run_command)
    monkeypatch.setattr(
        run_demo_pipeline,
        "regenerate_components_if_needed",
        lambda path, args: calls.append("components"),
    )
    monkeypatch.setattr(run_demo_pipeline, "selected_scene_count", lambda path: 0)
    monkeypatch.setattr(
        run_demo_pipeline,
        "publish_generated_components",
        lambda path: {"status": "published", "published_count": 0},
    )
    monkeypatch.setattr(run_demo_pipeline, "ensure_audio", lambda path: calls.append("audio"))
    monkeypatch.setattr(
        run_demo_pipeline,
        "compile_master_render_spec",
        lambda path: calls.append("render_spec"),
    )
    monkeypatch.setattr(
        run_demo_pipeline,
        "render_master_video",
        lambda path: run_dir / "09_video" / "candidate_snapshot.mp4",
    )
    monkeypatch.setattr(
        run_demo_pipeline,
        "run_optional_final_qa",
        lambda path, args, video: None,
    )

    args = run_demo_pipeline.build_parser().parse_args(
        ["--run-dir", str(run_dir)]
    )
    result = run_demo_pipeline.run_demo(args)

    assert result == 0
    assert calls[:4] == [
        "storyboard",
        "creative_plan",
        "artifacts",
        "generate_artifacts",
    ]
    assert calls.index("creative_plan") < calls.index("artifacts")
    assert calls.index("audio") < calls.index("render_spec")


def test_ensure_audio_skips_unconsumed_word_alignment(
    monkeypatch,
    tmp_path,
):
    calls = []

    def fake_pipeline_step(path, alias, allowed_codes=(0,)):
        calls.append(alias)
        audio_path = path / "06_audio" / "voiceover.mp3"
        audio_path.parent.mkdir(parents=True, exist_ok=True)
        audio_path.write_bytes(b"audio")
        return 0

    monkeypatch.setattr(
        run_demo_pipeline,
        "pipeline_step",
        fake_pipeline_step,
    )

    audio_path = run_demo_pipeline.ensure_audio(tmp_path)

    assert audio_path.exists()
    assert calls == ["generate_audio"]


def test_artifact_gate_detects_required_pending(tmp_path):
    root = tmp_path
    folder = root / "05c_artifacts"
    folder.mkdir()
    payload = {
        "artifacts": [
            {
                "artifact_id": "portrait",
                "artifact_type": "portrait",
                "required": True,
                "approved": False,
                "status": "needs_review",
                "source_strategy": "extract_from_dossier",
            }
        ]
    }
    (folder / "artifact_manifest_final.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )
    pending = run_demo_pipeline.artifact_gate(root)
    assert pending[0]["artifact_id"] == "portrait"


def test_artifact_gate_ignores_approved(tmp_path):
    folder = tmp_path / "05c_artifacts"
    folder.mkdir()
    payload = {
        "artifacts": [
            {
                "artifact_id": "chart",
                "required": True,
                "approved": True,
                "status": "ready",
            }
        ]
    }
    (folder / "artifact_manifest_final.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )
    assert run_demo_pipeline.artifact_gate(tmp_path) == []


def test_compile_without_approved_scenes_writes_empty_fallback_manifest(tmp_path):
    run_dir = tmp_path / "run"
    components_dir = run_dir / "05d_generated_components"
    components_dir.mkdir(parents=True)
    (components_dir / "component_review_summary.json").write_text(
        json.dumps({"approved_count": 0}), encoding="utf-8"
    )

    assert not run_demo_pipeline.compile_components_once(
        run_dir,
        argparse.Namespace(compile_timeout=120),
    )

    manifest = json.loads(
        (
            run_dir
            / "05e_component_compilation"
            / "approved_compiled_components.json"
        ).read_text(encoding="utf-8")
    )
    assert manifest["compiled_components"] == []


def test_compile_failure_falls_back_without_repair_attempts(
    monkeypatch, tmp_path
):
    run_dir = tmp_path / "run"
    components_dir = run_dir / "05d_generated_components"
    components_dir.mkdir(parents=True)
    (components_dir / "component_review_summary.json").write_text(
        json.dumps({"approved_count": 1}), encoding="utf-8"
    )
    monkeypatch.setattr(
        run_demo_pipeline,
        "run_command",
        lambda *args, **kwargs: 2,
    )

    assert not run_demo_pipeline.compile_components_once(
        run_dir,
        argparse.Namespace(compile_timeout=120),
    )

    manifest = json.loads(
        (
            run_dir
            / "05e_component_compilation"
            / "approved_compiled_components.json"
        ).read_text(encoding="utf-8")
    )
    assert manifest["compiled_components"] == []


def test_partial_compilation_runs_one_automatic_correction_pass(
    monkeypatch,
    tmp_path,
):
    run_dir = tmp_path / "run"
    components_dir = run_dir / "05d_generated_components"
    components_dir.mkdir(parents=True)
    (components_dir / "component_review_summary.json").write_text(
        json.dumps({"approved_count": 5}), encoding="utf-8"
    )
    compilation_dir = run_dir / "05e_component_compilation"
    compilation_dir.mkdir()
    calls = []

    def fake_run_command(arguments, allowed_codes=(0,)):
        calls.append(arguments)
        if any("step_05h_compile_components" in arg for arg in arguments):
            (compilation_dir / "compilation_report.json").write_text(
                json.dumps(
                    {
                        "components": [
                            {
                                "scene_id": "scene_ok",
                                "compile_status": "compiled",
                            },
                            {
                                "scene_id": "scene_fix",
                                "compile_status": "compiler_error",
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (compilation_dir / "approved_compiled_components.json").write_text(
                json.dumps(
                    {
                        "compiled_components": [
                            {"scene_id": "scene_ok"}
                        ]
                    }
                ),
                encoding="utf-8",
            )
        elif any(
            "step_05i_repair_compiler_errors" in arg
            for arg in arguments
        ):
            (compilation_dir / "approved_compiled_components.json").write_text(
                json.dumps(
                    {
                        "compiled_components": [
                            {"scene_id": "scene_ok"},
                            {"scene_id": "scene_fix"},
                        ]
                    }
                ),
                encoding="utf-8",
            )
        return 0

    monkeypatch.setattr(run_demo_pipeline, "run_command", fake_run_command)

    assert run_demo_pipeline.compile_components_once(
        run_dir,
        argparse.Namespace(compile_timeout=120),
    )
    assert sum(
        any("step_05i_repair_compiler_errors" in arg for arg in call)
        for call in calls
    ) == 1


def test_runtime_smoke_failure_excludes_scene_without_recompiling(
    monkeypatch, tmp_path
):
    run_dir = tmp_path / "run"
    components_dir = run_dir / "05d_generated_components"
    components_dir.mkdir(parents=True)
    (components_dir / "component_review_summary.json").write_text(
        json.dumps({"approved_count": 2}), encoding="utf-8"
    )
    compilation_dir = run_dir / "05e_component_compilation"
    compilation_dir.mkdir()
    compiled_path = compilation_dir / "approved_compiled_components.json"
    compiled_path.write_text(
        json.dumps(
            {
                "compiled_components": [
                    {"scene_id": "scene_ok"},
                    {"scene_id": "scene_bad"},
                ],
                "compiled_count": 2,
            }
        ),
        encoding="utf-8",
    )
    preview_dir = run_dir / "05f_component_previews"
    preview_dir.mkdir()
    (preview_dir / "preview_qa_report.json").write_text(
        json.dumps(
            {
                "results": [
                    {
                        "scene_id": "scene_ok",
                        "preview_rendered": True,
                        "visual_approved": True,
                        "status": "visual_approved",
                    },
                    {
                        "scene_id": "scene_bad",
                        "preview_rendered": False,
                        "visual_approved": False,
                        "status": "failed",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        run_demo_pipeline,
        "run_command",
        lambda *args, **kwargs: 2,
    )

    result = run_demo_pipeline.runtime_smoke_check(
        run_dir,
        argparse.Namespace(preview_timeout=180, preview_qa=False),
    )

    assert result["remaining_generated"] == 1
    updated = json.loads(compiled_path.read_text(encoding="utf-8"))
    assert [item["scene_id"] for item in updated["compiled_components"]] == [
        "scene_ok"
    ]


def test_runtime_smoke_uses_one_visual_repair_and_rechecks_scene(
    monkeypatch, tmp_path
):
    run_dir = tmp_path / "run"
    components_dir = run_dir / "05d_generated_components"
    components_dir.mkdir(parents=True)
    (components_dir / "component_review_summary.json").write_text(
        json.dumps({"approved_count": 1}), encoding="utf-8"
    )
    compilation_dir = run_dir / "05e_component_compilation"
    compilation_dir.mkdir()
    compiled_path = compilation_dir / "approved_compiled_components.json"
    compiled_path.write_text(
        json.dumps(
            {
                "compiled_components": [{"scene_id": "scene_repaired"}],
                "compiled_count": 1,
            }
        ),
        encoding="utf-8",
    )
    preview_dir = run_dir / "05f_component_previews"
    preview_dir.mkdir()
    preview_path = preview_dir / "preview_qa_report.json"
    preview_path.write_text(
        json.dumps(
            {
                "results": [
                    {
                        "scene_id": "scene_repaired",
                        "preview_rendered": True,
                        "visual_approved": False,
                        "status": "visual_repair_required",
                        "visual_qa": {"issues": []},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    repair_report_path = components_dir / "visual_repair_report.json"
    calls = []

    def fake_pipeline_step(path, alias, allowed_codes=(0,)):
        calls.append(alias)
        if alias == "visual_repair":
            repair_report_path.write_text(
                json.dumps({"repaired_count": 1}), encoding="utf-8"
            )
        return 0

    def fake_run_command(command, allowed_codes=(0,)):
        calls.append("preview")
        if calls.count("preview") == 2:
            preview_path.write_text(
                json.dumps(
                    {
                        "results": [
                            {
                                "scene_id": "scene_repaired",
                                "preview_rendered": True,
                                "visual_approved": True,
                                "status": "visual_approved",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
        return 0

    monkeypatch.setattr(run_demo_pipeline, "pipeline_step", fake_pipeline_step)
    monkeypatch.setattr(run_demo_pipeline, "auto_approve_components", lambda *args: 1)
    monkeypatch.setattr(
        run_demo_pipeline,
        "compile_components_once",
        lambda *args: True,
    )
    monkeypatch.setattr(run_demo_pipeline, "run_command", fake_run_command)

    result = run_demo_pipeline.runtime_smoke_check(
        run_dir,
        argparse.Namespace(
            preview_timeout=180,
            preview_qa=True,
            compile_timeout=120,
            reviewer="Test",
        ),
    )

    assert result["remaining_generated"] == 1
    assert calls.count("preview") == 2
    assert calls.count("visual_repair") == 1
    assert calls.count("component_review") == 2
