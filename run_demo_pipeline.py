"""Run the complete AI-assisted candidate-video demo workflow.

Goal: one command in, final video out.

The orchestrator is resumable. Source-sensitive dossier/local assets may pause
for human review. Decorative AI-generated artifacts and generated-code compiler
repair are handled automatically where configured.

Architecture v2 renders the final CandidateVideo composition once. Generated
components are published into the stable generated-current registry before the
master render specification is compiled. The legacy base-video segment
replacement path is not used.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent


class DemoOrchestratorError(Exception):
    """Raised when the demo orchestrator cannot complete safely."""


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def save_json(value, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def run_command(arguments, allowed_codes=(0,)):
    print("\n$", " ".join(str(value) for value in arguments), flush=True)
    completed = subprocess.run(
        arguments,
        cwd=str(PROJECT_ROOT),
        check=False,
    )
    if completed.returncode not in allowed_codes:
        raise DemoOrchestratorError(
            f"Command failed with exit code {completed.returncode}: "
            + " ".join(str(value) for value in arguments)
        )
    return completed.returncode


def newest_run():
    runs = PROJECT_ROOT / "runs"
    if not runs.exists():
        raise DemoOrchestratorError("Runs directory does not exist.")
    candidates = [path for path in runs.iterdir() if path.is_dir()]
    if not candidates:
        raise DemoOrchestratorError("No run directory was created.")
    return max(candidates, key=lambda path: path.stat().st_mtime).resolve()


def run_state(run_dir):
    path = run_dir / "run.json"
    return load_json(path) if path.exists() else {}


def pipeline_step(run_dir, alias, allowed_codes=(0,)):
    return run_command(
        [
            sys.executable,
            "run_pipeline.py",
            "--run-dir",
            str(run_dir),
            "--only-step",
            alias,
        ],
        allowed_codes=allowed_codes,
    )


def resolve_run(args):
    if args.run_dir:
        path = Path(args.run_dir).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"Run directory does not exist: {path}")
        return path

    source = Path(args.input).expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(f"Input dossier does not exist: {source}")

    print("\n$", sys.executable, "run_pipeline.py", "--input", str(source), flush=True)
    completed = subprocess.run(
        [sys.executable, "run_pipeline.py", "--input", str(source)],
        cwd=str(PROJECT_ROOT),
        check=False,
    )

    run_dir = newest_run()
    state = run_state(run_dir)

    if completed.returncode == 0:
        return run_dir

    compile_step = state.get("steps", {}).get("compile_components", {})
    compile_error = str(compile_step.get("error", ""))
    expected_approval_gate = (
        compile_step.get("status") == "failed"
        and "No generated components are approved" in compile_error
        and (run_dir / "05d_generated_components" / "generation_results.json").exists()
    )

    if expected_approval_gate:
        print("\nThe base pipeline reached the expected component-approval gate.")
        print(
            "The demo orchestrator is taking control of generated-scene "
            "selection and downstream execution."
        )
        return run_dir

    raise DemoOrchestratorError(
        f"The base pipeline failed unexpectedly. Review: {run_dir / 'run.json'}"
    )


def artifact_gate(run_dir):
    """Return only source-sensitive artifacts that need human review."""
    path = run_dir / "05c_artifacts" / "artifact_manifest_final.json"
    if not path.exists():
        return []

    manifest = load_json(path)
    pending = []
    human_strategies = {"extract_from_dossier", "approved_local_asset"}
    human_types = {"portrait", "logo", "candidate_photo", "candidate_portrait"}

    for item in manifest.get("artifacts", []):
        if not item.get("required") or item.get("approved"):
            continue

        strategy = str(item.get("source_strategy") or "").lower()
        artifact_type = str(item.get("artifact_type") or "").lower()
        status = str(item.get("status") or "").lower()

        if strategy == "image_generation":
            continue

        needs_human = (
            strategy in human_strategies
            or artifact_type in human_types
            or status == "needs_review"
        )

        if needs_human:
            pending.append(
                {
                    "artifact_id": item.get("artifact_id"),
                    "artifact_type": item.get("artifact_type"),
                    "status": item.get("status"),
                    "source_strategy": item.get("source_strategy"),
                    "local_path": item.get("local_path"),
                }
            )

    return pending


def print_artifact_instructions(run_dir, pending):
    print("\nHUMAN ARTIFACT REVIEW REQUIRED")
    for item in pending:
        print(" -", json.dumps(item, ensure_ascii=False))

    print("\nReview extracted/local assets here:")
    print(run_dir / "05c_artifacts" / "extracted")

    print("\nApprove the selected file with:")
    print(
        f'{sys.executable} -m app.pipeline.approve_artifact '
        f'--run-dir "{run_dir}" --artifact-id "ARTIFACT_ID" '
        f'--selected-path "FULL_FILE_PATH" '
        f'--description "Reviewed and approved source artifact."'
    )


def selected_scene_count(run_dir):
    path = run_dir / "05d_generated_components" / "generation_plan.json"
    if not path.exists():
        return 0
    return len(load_json(path).get("scenes", []))


def regenerate_components_if_needed(run_dir, args):
    """Ensure the generated-scene capacity cap matches the demo CLI."""
    desired = max(1, int(args.dynamic_scenes))
    creative_path = run_dir / "05b_creative_plan" / "creative_plan.json"
    creative = load_json(creative_path)
    draft = creative.get("draft", creative)

    eligible = [
        item
        for item in draft.get("scene_briefs", [])
        if (
            item.get("component_strategy") == "generated_component"
            or bool(item.get("custom_component_required"))
        )
    ]

    target = min(desired, len(eligible))
    existing_count = selected_scene_count(run_dir)

    if target == 0:
        print("\nCreative Director selected no custom generated scenes.")
        return

    if existing_count == target:
        print(
            f"\nReusing generated component plan with {existing_count} scene(s); "
            f"requested cap is {desired}."
        )
        return

    print(
        f"\nRegenerating component plan because bootstrap selected "
        f"{existing_count} scene(s), while the creative plan permits {target} "
        f"within --dynamic-scenes {desired}."
    )

    run_command(
        [
            sys.executable,
            "-m",
            "app.pipeline.step_05e_generate_components",
            "--run-dir",
            str(run_dir),
            "--max-scenes",
            str(desired),
        ]
    )


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

        run_command(
            [
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
                    "Demo auto-approval after deterministic generated-source "
                    "validation passed."
                ),
            ]
        )
        approved += 1

    return approved


def reject_scene_to_fallback(run_dir, scene_id, reviewer, reason):
    run_command(
        [
            sys.executable,
            "-m",
            "app.pipeline.approve_component",
            "--run-dir",
            str(run_dir),
            "--scene-id",
            scene_id,
            "--decision",
            "rejected_use_fallback",
            "--reviewer",
            reviewer,
            "--notes",
            reason,
        ]
    )


def compile_and_repair(run_dir, args):
    for cycle in range(1, 4):
        print(f"\nCOMPILATION CYCLE {cycle} OF 3")

        code = run_command(
            [
                sys.executable,
                "-m",
                "app.pipeline.step_05h_compile_components",
                "--run-dir",
                str(run_dir),
                "--timeout-seconds",
                str(args.compile_timeout),
            ],
            allowed_codes=(0, 2),
        )

        if code == 0:
            return

        run_command(
            [
                sys.executable,
                "-m",
                "app.pipeline.step_05i_repair_compiler_errors",
                "--run-dir",
                str(run_dir),
                "--max-attempts",
                str(args.repair_attempts),
                "--timeout-seconds",
                str(args.compile_timeout),
            ]
        )

        report = load_json(
            run_dir
            / "05e_component_compilation"
            / "compiler_repair_report.json"
        )

        repaired = [
            item
            for item in report.get("results", [])
            if item.get("status") == "repaired_compiled_pending_approval"
        ]
        fallbacks = [
            item
            for item in report.get("results", [])
            if item.get("status") == "fallback"
        ]

        if not repaired and not fallbacks:
            raise DemoOrchestratorError(
                "Compiler repair produced neither repaired components nor "
                "fallback decisions."
            )

        for item in repaired:
            run_command(
                [
                    sys.executable,
                    "-m",
                    "app.pipeline.promote_repaired_component",
                    "--run-dir",
                    str(run_dir),
                    "--scene-id",
                    item["scene_id"],
                ]
            )

        for item in fallbacks:
            reject_scene_to_fallback(
                run_dir,
                item["scene_id"],
                args.reviewer,
                "Generated source exhausted compiler repair attempts; use fallback.",
            )

        pipeline_step(run_dir, "component_review")

        if repaired:
            if not args.auto_approve_safe:
                raise DemoOrchestratorError(
                    "Compiler-repaired source requires review. Approve it and resume."
                )
            auto_approve_components(run_dir, args.reviewer)
            pipeline_step(run_dir, "component_review")

    raise DemoOrchestratorError("Compiler errors remain after three repair cycles.")


def optional_preview_qa(run_dir, args):
    """Run per-component preview QA only when explicitly requested."""
    if not args.preview_qa:
        print("\nSkipping per-component Visual QA in single-composition demo mode.")
        return

    run_command(
        [
            sys.executable,
            "-m",
            "app.pipeline.step_05j_preview_components",
            "--run-dir",
            str(run_dir),
            "--timeout-seconds",
            str(args.preview_timeout),
        ],
        allowed_codes=(0, 2),
    )

    preview_path = run_dir / "05f_component_previews" / "preview_qa_report.json"
    if not preview_path.exists():
        raise DemoOrchestratorError(
            f"Preview QA did not produce its report: {preview_path}"
        )

    preview = load_json(preview_path)
    if preview.get("ready_for_phase_7"):
        return

    failed = [
        item
        for item in preview.get("results", [])
        if not item.get("visual_approved")
    ]

    for item in failed:
        reject_scene_to_fallback(
            run_dir,
            item["scene_id"],
            args.reviewer,
            "Generated component did not pass optional Visual QA; use fallback.",
        )

    pipeline_step(run_dir, "component_review")

    # Recompile after fallback decisions so the approved compiled manifest
    # reflects the final generated-component set before publication.
    compile_and_repair(run_dir, args)


def ensure_audio(run_dir):
    audio_path = run_dir / "06_audio" / "voiceover.mp3"
    if not audio_path.exists() or audio_path.stat().st_size == 0:
        pipeline_step(run_dir, "generate_audio")

    # Preserve the existing alignment stage where available in the pipeline.
    pipeline_step(run_dir, "align_audio")

    if not audio_path.exists() or audio_path.stat().st_size == 0:
        raise DemoOrchestratorError(
            f"Audio generation created no usable voiceover: {audio_path}"
        )

    return audio_path


def publish_generated_components(run_dir):
    """Publish compiled generated components into generated-current."""
    pipeline_step(run_dir, "publish_dynamic")

    report_path = (
        run_dir
        / "05g_dynamic_integration"
        / "dynamic_publish_report.json"
    )

    if not report_path.exists():
        raise DemoOrchestratorError(
            f"Component publisher produced no report: {report_path}"
        )

    report = load_json(report_path)
    if report.get("status") != "published":
        raise DemoOrchestratorError(
            f"Generated component publication did not succeed: {report_path}"
        )

    return report


def compile_master_render_spec(run_dir):
    """Compile Step 08 after generated-current has been published."""
    pipeline_step(run_dir, "compile_render_spec")

    render_spec = run_dir / "08_render_spec" / "render_spec.json"
    validation = run_dir / "08_render_spec" / "render_validation.json"

    if not render_spec.exists():
        raise DemoOrchestratorError(
            f"Master render specification is missing: {render_spec}"
        )

    if validation.exists():
        report = load_json(validation)
        if not report.get("single_composition"):
            raise DemoOrchestratorError(
                "Render specification is not marked as single-composition."
            )

    return render_spec


def render_master_video(run_dir):
    """Render CandidateVideo once using the master render specification."""
    pipeline_step(run_dir, "render_video")

    expected = run_dir / "09_video" / "candidate_video.mp4"
    if expected.exists() and expected.stat().st_size > 0:
        return expected

    video_dir = run_dir / "09_video"
    candidates = (
        [
            path
            for path in video_dir.glob("*.mp4")
            if path.exists() and path.stat().st_size > 0
        ]
        if video_dir.exists()
        else []
    )

    if not candidates:
        raise DemoOrchestratorError(
            f"Master renderer produced no MP4 in {video_dir}."
        )

    return max(candidates, key=lambda path: path.stat().st_mtime)


def run_optional_final_qa(run_dir, args, output_video):
    """Run the existing final QA only when requested.

    This is kept optional because the legacy final-dynamic QA stage may still
    be coupled to 10_dynamic_render in older installations.
    """
    if not args.final_qa:
        return None

    qa_module = "app.pipeline.step_10b_final_dynamic_video_qa"
    run_command(
        [
            sys.executable,
            "-m",
            qa_module,
            "--run-dir",
            str(run_dir),
            "--timeout-seconds",
            str(args.final_qa_timeout),
        ],
        allowed_codes=(0, 2),
    )

    candidate_reports = [
        run_dir / "09_video" / "final_qa" / "final_video_qa_report.json",
        run_dir / "10_dynamic_render" / "final_qa" / "final_video_qa_report.json",
    ]

    report_path = next(
        (path for path in candidate_reports if path.exists()),
        None,
    )

    if report_path is None:
        print(
            "\nFinal QA command completed but no known QA report path was found. "
            "The master video remains available at:"
        )
        print(output_video)
        return None

    return report_path, load_json(report_path)


def run_demo(args):
    run_dir = resolve_run(args)
    print("\nRUN DIRECTORY:", run_dir)

    state_path = run_dir / "demo_orchestrator_state.json"
    state = {
        "run_dir": str(run_dir),
        "status": "running",
        "render_architecture": "single_master_composition_v2",
    }
    save_json(state, state_path)

    creative_plan_path = run_dir / "05b_creative_plan" / "creative_plan.json"
    if not creative_plan_path.exists():
        pipeline_step(run_dir, "creative_plan")

    artifact_manifest_path = (
        run_dir / "05c_artifacts" / "artifact_manifest_final.json"
    )
    if not artifact_manifest_path.exists():
        pipeline_step(run_dir, "artifacts")
        command = [
            sys.executable,
            "-m",
            "app.pipeline.step_05d_generate_artifacts",
            "--run-dir",
            str(run_dir),
        ]
        if args.generate_images:
            command.append("--generate-images")
        run_command(command)

    pending = artifact_gate(run_dir)
    if pending:
        state.update(
            {
                "status": "awaiting_artifact_review",
                "pending_artifacts": pending,
            }
        )
        save_json(state, state_path)
        print_artifact_instructions(run_dir, pending)
        return 20

    regenerate_components_if_needed(run_dir, args)

    generation_plan = run_dir / "05d_generated_components" / "generation_plan.json"
    generated_scene_count = selected_scene_count(run_dir)

    if generated_scene_count > 0:
        pipeline_step(run_dir, "component_review")

        if args.auto_approve_safe:
            auto_approve_components(run_dir, args.reviewer)
            pipeline_step(run_dir, "component_review")
        else:
            state["status"] = "awaiting_component_review"
            save_json(state, state_path)
            return 21

        review_path = (
            run_dir
            / "05d_generated_components"
            / "component_review_summary.json"
        )
        if not review_path.exists():
            raise DemoOrchestratorError(
                f"Component review summary is missing: {review_path}"
            )

        review = load_json(review_path)
        if not review.get("ready_for_phase_5"):
            raise DemoOrchestratorError(
                "Component review is not ready for compilation."
            )

        compile_and_repair(run_dir, args)
        optional_preview_qa(run_dir, args)
        publish_report = publish_generated_components(run_dir)
    else:
        print("\nNo generated scenes are planned; using library renderers only.")
        publish_report = {
            "status": "not_required",
            "published_count": 0,
        }

    # Audio must exist before Step 08 because the master timeline duration is
    # derived from the final voiceover file.
    ensure_audio(run_dir)

    # IMPORTANT ORDER:
    # generated-current is published first, then Step 08 resolves which
    # published generated components can participate in CandidateVideo.
    compile_master_render_spec(run_dir)

    # The final video is rendered exactly once. No base MP4 extraction,
    # generated-segment rendering, concatenation, or audio re-muxing occurs.
    output_video = render_master_video(run_dir)

    state["output_video"] = str(output_video)
    state["published_generated_components"] = publish_report.get(
        "published_count",
        0,
    )

    qa_result = run_optional_final_qa(
        run_dir,
        args,
        output_video,
    )

    if qa_result is not None:
        report_path, final_report = qa_result
        state["final_qa_report"] = str(report_path)

        if not final_report.get("ready_for_final_approval"):
            state["status"] = "final_video_created_qa_warning"
            save_json(state, state_path)
            print("\nFINAL VIDEO CREATED:", output_video)
            print("Final QA requires review:", report_path)
            return 23

    if args.auto_approve_final:
        # Keep the existing approval action available, but only after the
        # single master video has been produced and optional QA has passed.
        run_command(
            [
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
                "Demo approval for the single master-composition render.",
            ]
        )
        state["status"] = "completed"
    else:
        state["status"] = "final_video_created"

    save_json(state, state_path)
    print("\nDEMO VIDEO:", state["output_video"])
    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        description=(
            "Run the resumable AI-assisted candidate-video demo pipeline "
            "using one final Remotion composition."
        )
    )

    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input")
    source.add_argument("--run-dir")

    parser.add_argument("--generate-images", action="store_true")
    parser.add_argument("--dynamic-scenes", type=int, default=5)
    parser.add_argument("--auto-approve-safe", action="store_true")
    parser.add_argument("--auto-approve-final", action="store_true")
    parser.add_argument("--reviewer", default="Demo Reviewer")
    parser.add_argument("--repair-attempts", type=int, default=2)
    parser.add_argument("--compile-timeout", type=int, default=120)

    # Visual QA is optional in v2. Generated source compilation is the normal
    # deterministic publishing gate for the POC.
    parser.add_argument("--preview-qa", action="store_true")
    parser.add_argument("--preview-timeout", type=int, default=180)

    # Retained for CLI compatibility. The legacy dynamic segment renderer is
    # intentionally not used by architecture v2.
    parser.add_argument("--render-timeout", type=int, default=900)

    # Final QA is advisory/optional for the POC because older QA scripts may
    # still expect the legacy 10_dynamic_render output structure.
    parser.add_argument("--final-qa", action="store_true")
    parser.add_argument("--final-qa-timeout", type=int, default=300)

    return parser


def main():
    args = build_parser().parse_args()

    try:
        return run_demo(args)

    except KeyboardInterrupt:
        print("\nDEMO ORCHESTRATOR INTERRUPTED")
        return 130

    except Exception as error:
        print("\nDEMO ORCHESTRATOR FAILED")
        print(f"{type(error).__name__}: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
