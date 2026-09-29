"""Install the resumable one-command demo orchestrator."""
from pathlib import Path

ROOT = Path.cwd()

RUNNER = r'''"""Run the complete AI-assisted candidate-video demo workflow.

This orchestrator is resumable. It pauses only for human-sensitive approval
steps, such as selecting a dossier photograph or accepting a blocking visual
QA result. Run the same command again after completing the requested review.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent


class DemoOrchestratorError(Exception):
    pass


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def save_json(value, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def run_command(arguments, allowed_codes=(0,)):
    print("\n$", " ".join(str(value) for value in arguments), flush=True)
    completed = subprocess.run(arguments, cwd=str(PROJECT_ROOT), check=False)
    if completed.returncode not in allowed_codes:
        raise DemoOrchestratorError(
            f"Command failed with exit code {completed.returncode}: "
            + " ".join(str(value) for value in arguments)
        )
    return completed.returncode


def newest_run():
    runs = PROJECT_ROOT / "runs"
    candidates = [path for path in runs.iterdir() if path.is_dir()]
    if not candidates:
        raise DemoOrchestratorError("No run directory was created.")
    return max(candidates, key=lambda path: path.stat().st_mtime).resolve()


def resolve_run(args):
    if args.run_dir:
        path = Path(args.run_dir).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"Run directory does not exist: {path}")
        return path
    if not args.input:
        raise DemoOrchestratorError("Use --input for a new run or --run-dir to resume.")
    source = Path(args.input).expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(f"Input dossier does not exist: {source}")
    run_command([sys.executable, "run_pipeline.py", "--input", str(source)])
    return newest_run()


def pipeline_step(run_dir, alias):
    run_command([
        sys.executable,
        "run_pipeline.py",
        "--run-dir",
        str(run_dir),
        "--only-step",
        alias,
    ])


def artifact_gate(run_dir):
    path = run_dir / "05c_artifacts" / "artifact_manifest_final.json"
    if not path.exists():
        return []
    manifest = load_json(path)
    pending = []
    for item in manifest.get("artifacts", []):
        if item.get("required") and not item.get("approved"):
            status = item.get("status")
            if status in {"needs_review", "planned", "fallback"}:
                pending.append({
                    "artifact_id": item.get("artifact_id"),
                    "artifact_type": item.get("artifact_type"),
                    "status": status,
                    "source_strategy": item.get("source_strategy"),
                    "local_path": item.get("local_path"),
                })
    return pending


def print_artifact_instructions(run_dir, pending):
    print("\nHUMAN ARTIFACT REVIEW REQUIRED")
    print("Review extracted or generated files before continuing:")
    for item in pending:
        print(" -", json.dumps(item, ensure_ascii=False))
    print("\nExtracted images:")
    print(run_dir / "05c_artifacts" / "extracted")
    print("\nApprove the correct file with:")
    print(
        f'{sys.executable} -m app.pipeline.approve_artifact '
        f'--run-dir "{run_dir}" --artifact-id "ARTIFACT_ID" '
        f'--selected-path "FULL_FILE_PATH" '
        f'--description "Reviewed and approved source artifact."'
    )
    print("\nThen rerun this orchestrator command.")


def auto_approve_components(run_dir, reviewer):
    reviews_path = run_dir / "05d_generated_components" / "review_packages.json"
    if not reviews_path.exists():
        return 0
    reviews = load_json(reviews_path)
    approved = 0
    for item in reviews:
        if not item.get("eligible_for_approval"):
            continue
        if item.get("approval_status") == "approved":
            continue
        validation = item.get("source_validation") or {}
        if not validation.get("valid"):
            continue
        run_command([
            sys.executable,
            "-m",
            "app.pipeline.approve_component",
            "--run-dir",
            str(run_dir),
            "--scene-id",
            item["scene_id"],
            "--decision",
            "approved_for_compilation",
            "--reviewer",
            reviewer,
            "--notes",
            (
                "Demo auto-approval: deterministic source validation passed, "
                "imports and artifact references are approved, and no blocking "
                "source issue was detected."
            ),
        ])
        approved += 1
    return approved


def compile_and_repair(run_dir, args):
    code = run_command([
        sys.executable,
        "-m",
        "app.pipeline.step_05h_compile_components",
        "--run-dir",
        str(run_dir),
        "--timeout-seconds",
        str(args.compile_timeout),
    ], allowed_codes=(0, 2))
    if code == 0:
        return

    run_command([
        sys.executable,
        "-m",
        "app.pipeline.step_05i_repair_compiler_errors",
        "--run-dir",
        str(run_dir),
        "--max-attempts",
        str(args.repair_attempts),
        "--timeout-seconds",
        str(args.compile_timeout),
    ])
    report_path = run_dir / "05e_component_compilation" / "compiler_repair_report.json"
    report = load_json(report_path)
    repaired = [
        item for item in report.get("results", [])
        if item.get("status") == "repaired_compiled_pending_approval"
    ]
    if not repaired:
        raise DemoOrchestratorError(
            "Compiler repair exhausted its attempts. The affected scene must use "
            "its fallback or be reviewed manually."
        )
    for item in repaired:
        run_command([
            sys.executable,
            "-m",
            "app.pipeline.promote_repaired_component",
            "--run-dir",
            str(run_dir),
            "--scene-id",
            item["scene_id"],
        ])
    pipeline_step(run_dir, "component_review")
    if args.auto_approve_safe:
        auto_approve_components(run_dir, args.reviewer)
        pipeline_step(run_dir, "component_review")
    else:
        raise DemoOrchestratorError(
            "Compiler-repaired source requires review. Approve it, then rerun."
        )
    run_command([
        sys.executable,
        "-m",
        "app.pipeline.step_05h_compile_components",
        "--run-dir",
        str(run_dir),
        "--timeout-seconds",
        str(args.compile_timeout),
    ])


def run_demo(args):
    run_dir = resolve_run(args)
    print("\nRUN DIRECTORY:", run_dir)
    state_path = run_dir / "demo_orchestrator_state.json"
    state = {"run_dir": str(run_dir), "status": "running"}
    save_json(state, state_path)

    pipeline_step(run_dir, "creative_plan")
    pipeline_step(run_dir, "artifacts")

    artifact_command = [
        sys.executable,
        "-m",
        "app.pipeline.step_05d_generate_artifacts",
        "--run-dir",
        str(run_dir),
    ]
    if args.generate_images:
        artifact_command.append("--generate-images")
    run_command(artifact_command)

    pending = artifact_gate(run_dir)
    if pending:
        state.update({"status": "awaiting_artifact_review", "pending_artifacts": pending})
        save_json(state, state_path)
        print_artifact_instructions(run_dir, pending)
        return 20

    dynamic_scenes = max(1, args.dynamic_scenes)
    if dynamic_scenes > 1:
        print(
            "\nNOTE: Component generation will create multiple scenes, but the "
            "current Phase 7B demo renderer integrates only the approved 'intro' "
            "scene. Additional components remain available for the future "
            "timeline-aware renderer."
        )
    run_command([
        sys.executable,
        "-m",
        "app.pipeline.step_05e_generate_components",
        "--run-dir",
        str(run_dir),
        "--max-scenes",
        str(dynamic_scenes),
    ])

    pipeline_step(run_dir, "component_review")
    if args.auto_approve_safe:
        auto_approve_components(run_dir, args.reviewer)
        pipeline_step(run_dir, "component_review")
    else:
        state["status"] = "awaiting_component_review"
        save_json(state, state_path)
        print("\nGenerated source requires review. Approve components and rerun.")
        return 21

    review_summary = load_json(
        run_dir / "05d_generated_components" / "component_review_summary.json"
    )
    if not review_summary.get("ready_for_phase_5"):
        raise DemoOrchestratorError(
            "Component review is not ready for compilation."
        )

    compile_and_repair(run_dir, args)

    run_command([
        sys.executable,
        "-m",
        "app.pipeline.step_05j_preview_components",
        "--run-dir",
        str(run_dir),
        "--timeout-seconds",
        str(args.preview_timeout),
    ], allowed_codes=(0, 2))
    preview = load_json(
        run_dir / "05f_component_previews" / "preview_qa_report.json"
    )
    if not preview.get("ready_for_phase_7"):
        state["status"] = "awaiting_visual_review"
        save_json(state, state_path)
        print("\nVisual QA found a blocking issue. Review:")
        print(run_dir / "05f_component_previews" / "preview_qa_report.json")
        return 22

    pipeline_step(run_dir, "publish_dynamic")
    run_command([
        sys.executable,
        "-m",
        "app.pipeline.step_09b_render_dynamic_video",
        "--run-dir",
        str(run_dir),
        "--timeout-seconds",
        str(args.render_timeout),
    ])
    run_command([
        sys.executable,
        "-m",
        "app.pipeline.step_10b_final_dynamic_video_qa",
        "--run-dir",
        str(run_dir),
        "--timeout-seconds",
        str(args.final_qa_timeout),
    ], allowed_codes=(0, 2))

    final_report = load_json(
        run_dir
        / "10_dynamic_render"
        / "final_qa"
        / "final_video_qa_report.json"
    )
    if not final_report.get("ready_for_final_approval"):
        state["status"] = "awaiting_final_video_review"
        save_json(state, state_path)
        print("\nFinal QA did not approve automatic release. Review the report:")
        print(
            run_dir
            / "10_dynamic_render"
            / "final_qa"
            / "final_video_qa_report.json"
        )
        return 23

    if args.auto_approve_final:
        run_command([
            sys.executable,
            "-m",
            "app.pipeline.approve_final_video",
            "--run-dir",
            str(run_dir),
            "--reviewer",
            args.reviewer,
            "--decision",
            "approved_for_demo",
            "--notes",
            "Demo auto-approval after technical and cohesion QA passed.",
        ])
        state["status"] = "completed"
    else:
        state["status"] = "awaiting_final_human_approval"
        print("\nThe video passed QA. Approve it with:")
        print(
            f'{sys.executable} -m app.pipeline.approve_final_video '
            f'--run-dir "{run_dir}" --reviewer "{args.reviewer}" '
            f'--decision approved_for_demo '
            f'--notes "Reviewed final demo video."'
        )
    state["output_video"] = str(
        run_dir / "10_dynamic_render" / "candidate_video_dynamic.mp4"
    )
    save_json(state, state_path)
    print("\nDEMO VIDEO:", state["output_video"])
    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        description="Run the resumable AI-assisted candidate-video demo pipeline."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input")
    source.add_argument("--run-dir")
    parser.add_argument("--generate-images", action="store_true")
    parser.add_argument("--dynamic-scenes", type=int, default=1)
    parser.add_argument("--auto-approve-safe", action="store_true")
    parser.add_argument("--auto-approve-final", action="store_true")
    parser.add_argument("--reviewer", default="Demo Reviewer")
    parser.add_argument("--repair-attempts", type=int, default=2)
    parser.add_argument("--compile-timeout", type=int, default=120)
    parser.add_argument("--preview-timeout", type=int, default=180)
    parser.add_argument("--render-timeout", type=int, default=900)
    parser.add_argument("--final-qa-timeout", type=int, default=300)
    return parser


def main():
    args = build_parser().parse_args()
    try:
        return run_demo(args)
    except Exception as error:
        print("\nDEMO ORCHESTRATOR FAILED")
        print(f"{type(error).__name__}: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
'''

TEST = r'''"""Tests for the demo orchestrator helpers."""
import json
from pathlib import Path
import run_demo_pipeline


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
'''

(ROOT / "run_demo_pipeline.py").write_text(RUNNER, encoding="utf-8")
(ROOT / "tests" / "test_demo_orchestrator.py").write_text(TEST, encoding="utf-8")
print("Wrote run_demo_pipeline.py")
print("Wrote tests/test_demo_orchestrator.py")
print("Demo orchestrator installation complete.")
