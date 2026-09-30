"""Run the complete AI-assisted candidate-video demo workflow.

Architecture v2:

dossier
-> content selection
-> storyboard
-> creative plan
-> artifacts
-> generated components
-> deterministic source validation
-> TypeScript compilation / repair
-> mandatory Remotion runtime smoke render
-> publish surviving generated components
-> audio
-> master render specification
-> one CandidateVideo render

AI Visual QA remains optional.
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
    return json.loads(
        path.read_text(
            encoding="utf-8-sig"
        )
    )


def save_json(value, path: Path):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        json.dumps(
            value,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def run_command(
    arguments,
    allowed_codes=(0,),
):
    print(
        "\n$",
        " ".join(
            str(value)
            for value in arguments
        ),
        flush=True,
    )

    completed = subprocess.run(
        arguments,
        cwd=str(PROJECT_ROOT),
        check=False,
    )

    if (
        completed.returncode
        not in allowed_codes
    ):
        raise DemoOrchestratorError(
            "Command failed with exit code "
            f"{completed.returncode}: "
            + " ".join(
                str(value)
                for value in arguments
            )
        )

    return completed.returncode


def newest_run():
    runs = (
        PROJECT_ROOT
        / "runs"
    )

    if not runs.exists():
        raise DemoOrchestratorError(
            "Runs directory does not exist."
        )

    candidates = [
        path
        for path in runs.iterdir()
        if path.is_dir()
    ]

    if not candidates:
        raise DemoOrchestratorError(
            "No run directory was created."
        )

    return max(
        candidates,
        key=lambda path:
            path.stat().st_mtime,
    ).resolve()


def run_state(run_dir):
    path = (
        run_dir
        / "run.json"
    )

    if not path.exists():
        return {}

    return load_json(path)


def pipeline_step(
    run_dir,
    alias,
    allowed_codes=(0,),
):
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
        path = (
            Path(args.run_dir)
            .expanduser()
            .resolve()
        )

        if not path.exists():
            raise FileNotFoundError(
                "Run directory does "
                f"not exist: {path}"
            )

        return path

    source = (
        Path(args.input)
        .expanduser()
        .resolve()
    )

    if not source.exists():
        raise FileNotFoundError(
            "Input dossier does "
            f"not exist: {source}"
        )

    print(
        "\n$",
        sys.executable,
        "run_pipeline.py",
        "--input",
        str(source),
        flush=True,
    )

    completed = subprocess.run(
        [
            sys.executable,
            "run_pipeline.py",
            "--input",
            str(source),
        ],
        cwd=str(PROJECT_ROOT),
        check=False,
    )

    run_dir = newest_run()

    if completed.returncode == 0:
        return run_dir

    state = run_state(run_dir)

    compile_step = (
        state
        .get("steps", {})
        .get(
            "compile_components",
            {},
        )
    )

    compile_error = str(
        compile_step.get(
            "error",
            "",
        )
    )

    expected_gate = (
        compile_step.get("status")
        == "failed"
        and (
            "No generated components "
            "are approved"
            in compile_error
        )
        and (
            run_dir
            / "05d_generated_components"
            / "generation_results.json"
        ).exists()
    )

    if expected_gate:
        print(
            "\nBase pipeline reached "
            "the expected generated-"
            "component approval gate."
        )

        return run_dir

    raise DemoOrchestratorError(
        "Base pipeline failed "
        "unexpectedly. Review: "
        f"{run_dir / 'run.json'}"
    )


def artifact_gate(run_dir):
    """
    Return unresolved artifacts that
    genuinely require manual review.

    approved_local_asset is expected
    to be automatically resolved by the
    P0 artifact service.
    """

    path = (
        run_dir
        / "05c_artifacts"
        / "artifact_manifest_final.json"
    )

    if not path.exists():
        return []

    manifest = load_json(path)

    pending = []

    for item in manifest.get(
        "artifacts",
        [],
    ):
        if (
            not item.get("required")
            or item.get("approved")
        ):
            continue

        strategy = str(
            item.get(
                "source_strategy"
            )
            or ""
        ).lower()

        status = str(
            item.get("status")
            or ""
        ).lower()

        # These are not human gates
        # in the P0 demo architecture.
        if strategy in {
            "image_generation",
            "approved_local_asset",
        }:
            continue

        if (
            strategy
            == "extract_from_dossier"
            or status
            == "needs_review"
        ):
            pending.append(
                {
                    "artifact_id":
                        item.get(
                            "artifact_id"
                        ),

                    "artifact_type":
                        item.get(
                            "artifact_type"
                        ),

                    "status":
                        item.get(
                            "status"
                        ),

                    "source_strategy":
                        item.get(
                            "source_strategy"
                        ),

                    "local_path":
                        item.get(
                            "local_path"
                        ),
                }
            )

    return pending


def print_artifact_instructions(
    run_dir,
    pending,
):
    print(
        "\nHUMAN ARTIFACT "
        "REVIEW REQUIRED"
    )

    for item in pending:
        print(
            " -",
            json.dumps(
                item,
                ensure_ascii=False,
            ),
        )

    print(
        "\nReview extracted assets:"
    )

    print(
        run_dir
        / "05c_artifacts"
        / "extracted"
    )


def selected_scene_count(run_dir):
    path = (
        run_dir
        / "05d_generated_components"
        / "generation_plan.json"
    )

    if not path.exists():
        return 0

    return len(
        load_json(path).get(
            "scenes",
            [],
        )
    )


def approved_generated_scene_count(
    run_dir,
):
    """
    Return the number of generated
    scenes currently approved for
    compilation.
    """

    path = (
        run_dir
        / "05d_generated_components"
        / "component_review_summary.json"
    )

    if not path.exists():
        return 0

    review = load_json(path)

    return int(
        review.get(
            "approved_count",
            0,
        )
        or 0
    )


def regenerate_components_if_needed(
    run_dir,
    args,
):
    desired = max(
        1,
        int(args.dynamic_scenes),
    )

    creative_path = (
        run_dir
        / "05b_creative_plan"
        / "creative_plan.json"
    )

    creative = load_json(
        creative_path
    )

    draft = creative.get(
        "draft",
        creative,
    )

    eligible = [
        item
        for item in draft.get(
            "scene_briefs",
            [],
        )
        if (
            item.get(
                "component_strategy"
            )
            == "generated_component"
            or bool(
                item.get(
                    "custom_component_required"
                )
            )
        )
    ]

    target = min(
        desired,
        len(eligible),
    )

    existing = (
        selected_scene_count(
            run_dir
        )
    )

    if target == 0:
        print(
            "\nCreative Director selected "
            "no generated scenes."
        )
        return

    if existing == target:
        print(
            "\nReusing generated component "
            f"plan with {existing} scene(s)."
        )
        return

    print(
        "\nGenerating "
        f"{target} custom scene(s) "
        f"within cap {desired}."
    )

    run_command(
        [
            sys.executable,
            "-m",
            (
                "app.pipeline."
                "step_05e_generate_components"
            ),
            "--run-dir",
            str(run_dir),
            "--max-scenes",
            str(desired),
        ]
    )


def auto_approve_components(
    run_dir,
    reviewer,
):
    path = (
        run_dir
        / "05d_generated_components"
        / "review_packages.json"
    )

    if not path.exists():
        return 0

    reviews = load_json(path)

    count = 0

    for item in reviews:
        if not item.get(
            "eligible_for_approval"
        ):
            continue

        status = str(
            item.get(
                "approval_status"
            )
            or ""
        ).lower()

        # Never resurrect explicit
        # fallback decisions.
        if status in {
            "approved",
            "approved_for_compilation",
            "rejected",
            "rejected_use_fallback",
        }:
            continue

        validation = (
            item.get(
                "source_validation"
            )
            or {}
        )

        if not validation.get(
            "valid"
        ):
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
                (
                    "approved_for_"
                    "compilation"
                ),
                "--reviewer",
                reviewer,
                "--notes",
                (
                    "Automatic demo approval "
                    "after deterministic source "
                    "validation passed."
                ),
            ]
        )

        count += 1

    return count


def reject_scene_to_fallback(
    run_dir,
    scene_id,
    reviewer,
    reason,
):
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


def compile_and_repair(
    run_dir,
    args,
):
    """
    Compile generated components and
    attempt automatic compiler repair.

    This function must only be called
    when at least one generated component
    is approved.
    """

    if (
        approved_generated_scene_count(
            run_dir
        )
        == 0
    ):
        print(
            "\nNo generated components "
            "are approved for compilation."
        )

        return False

    for cycle in range(
        1,
        4,
    ):
        print(
            "\nCOMPILATION CYCLE "
            f"{cycle} OF 3"
        )

        code = run_command(
            [
                sys.executable,
                "-m",
                (
                    "app.pipeline."
                    "step_05h_compile_components"
                ),
                "--run-dir",
                str(run_dir),
                "--timeout-seconds",
                str(
                    args.compile_timeout
                ),
            ],
            allowed_codes=(
                0,
                2,
            ),
        )

        if code == 0:
            return True

        run_command(
            [
                sys.executable,
                "-m",
                (
                    "app.pipeline."
                    "step_05i_repair_"
                    "compiler_errors"
                ),
                "--run-dir",
                str(run_dir),
                "--max-attempts",
                str(
                    args.repair_attempts
                ),
                "--timeout-seconds",
                str(
                    args.compile_timeout
                ),
            ]
        )

        report_path = (
            run_dir
            / "05e_component_compilation"
            / "compiler_repair_report.json"
        )

        if not report_path.exists():
            raise DemoOrchestratorError(
                "Compiler repair report missing."
            )

        report = load_json(
            report_path
        )

        repaired = [
            item
            for item in report.get(
                "results",
                [],
            )
            if item.get("status")
            == (
                "repaired_compiled_"
                "pending_approval"
            )
        ]

        fallbacks = [
            item
            for item in report.get(
                "results",
                [],
            )
            if item.get("status")
            == "fallback"
        ]

        if (
            not repaired
            and not fallbacks
        ):
            raise DemoOrchestratorError(
                "Compiler repair produced "
                "no actionable result."
            )

        for item in repaired:
            run_command(
                [
                    sys.executable,
                    "-m",
                    (
                        "app.pipeline."
                        "promote_repaired_component"
                    ),
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
                (
                    "Generated source exhausted "
                    "compiler repair attempts."
                ),
            )

        pipeline_step(
            run_dir,
            "component_review",
        )

        if repaired:
            if not args.auto_approve_safe:
                raise DemoOrchestratorError(
                    "Repaired components require "
                    "review before compilation."
                )

            auto_approve_components(
                run_dir,
                args.reviewer,
            )

            pipeline_step(
                run_dir,
                "component_review",
            )

        if (
            approved_generated_scene_count(
                run_dir
            )
            == 0
        ):
            print(
                "\nAll generated scenes were "
                "routed to library fallbacks "
                "during compiler repair."
            )

            return False

    raise DemoOrchestratorError(
        "Compiler errors remain after "
        "three repair cycles."
    )


def runtime_smoke_command(
    run_dir,
    args,
):
    command = [
        sys.executable,
        "-m",
        (
            "app.pipeline."
            "step_05j_preview_components"
        ),
        "--run-dir",
        str(run_dir),
        "--timeout-seconds",
        str(
            args.preview_timeout
        ),
    ]

    if args.preview_qa:
        command.append(
            "--visual-qa"
        )

    return command


def runtime_smoke_failures(
    preview,
):
    return [
        item
        for item in preview.get(
            "results",
            [],
        )
        if not item.get(
            "preview_rendered"
        )
    ]


def runtime_smoke_check(
    run_dir,
    args,
):
    """
    Mandatory generated-component
    runtime gate.

    Returns a dictionary containing
    whether any generated components
    remain available for publication.
    """

    approved_before = (
        approved_generated_scene_count(
            run_dir
        )
    )

    if approved_before == 0:
        return {
            "publish_generated":
                False,

            "all_fell_back":
                True,

            "remaining_generated":
                0,
        }

    print(
        "\nRunning mandatory generated-"
        "component runtime smoke check."
    )

    command = (
        runtime_smoke_command(
            run_dir,
            args,
        )
    )

    run_command(
        command,
        allowed_codes=(
            0,
            2,
        ),
    )

    preview_path = (
        run_dir
        / "05f_component_previews"
        / "preview_qa_report.json"
    )

    if not preview_path.exists():
        raise DemoOrchestratorError(
            "Runtime smoke report missing: "
            f"{preview_path}"
        )

    preview = load_json(
        preview_path
    )

    failed = (
        runtime_smoke_failures(
            preview
        )
    )

    if not failed:
        print(
            "\nAll generated components "
            "passed runtime smoke rendering."
        )

        return {
            "publish_generated":
                True,

            "all_fell_back":
                False,

            "remaining_generated":
                approved_before,

            "preview":
                preview,
        }

    print(
        "\nRuntime smoke failures detected."
    )

    for item in failed:
        scene_id = item.get(
            "scene_id"
        )

        if not scene_id:
            continue

        reason = (
            "Generated component failed "
            "mandatory runtime smoke render."
        )

        render_errors = (
            item.get(
                "render_errors"
            )
            or []
        )

        if render_errors:
            first_error = (
                render_errors[0]
            )

            diagnostic = str(
                first_error.get(
                    "stderr"
                )
                or first_error.get(
                    "stdout"
                )
                or ""
            ).strip()

            if diagnostic:
                reason += (
                    " Runtime diagnostic: "
                    + diagnostic[:800]
                )

        reject_scene_to_fallback(
            run_dir,
            scene_id,
            args.reviewer,
            reason,
        )

    pipeline_step(
        run_dir,
        "component_review",
    )

    remaining = (
        approved_generated_scene_count(
            run_dir
        )
    )

    # CRITICAL ALL-FALLBACK CASE
    if remaining == 0:
        print(
            "\nAll generated components "
            "were routed to library fallbacks."
        )

        print(
            "Skipping generated-component "
            "recompilation and publication."
        )

        return {
            "publish_generated":
                False,

            "all_fell_back":
                True,

            "remaining_generated":
                0,
        }

    print(
        "\nRecompiling "
        f"{remaining} surviving "
        "generated component(s)."
    )

    compiled = (
        compile_and_repair(
            run_dir,
            args,
        )
    )

    if not compiled:
        return {
            "publish_generated":
                False,

            "all_fell_back":
                True,

            "remaining_generated":
                0,
        }

    print(
        "\nRe-running runtime smoke "
        "check after fallback resolution."
    )

    run_command(
        command,
        allowed_codes=(
            0,
            2,
        ),
    )

    second_preview = load_json(
        preview_path
    )

    remaining_failures = (
        runtime_smoke_failures(
            second_preview
        )
    )

    if remaining_failures:
        failed_ids = [
            str(
                item.get(
                    "scene_id"
                )
            )
            for item
            in remaining_failures
        ]

        raise DemoOrchestratorError(
            "Generated components still "
            "fail runtime smoke rendering: "
            + ", ".join(
                failed_ids
            )
        )

    final_count = (
        approved_generated_scene_count(
            run_dir
        )
    )

    print(
        "\nSurviving generated components "
        "passed runtime smoke rendering."
    )

    return {
        "publish_generated":
            final_count > 0,

        "all_fell_back":
            final_count == 0,

        "remaining_generated":
            final_count,

        "preview":
            second_preview,
    }


def ensure_audio(run_dir):
    audio_path = (
        run_dir
        / "06_audio"
        / "voiceover.mp3"
    )

    if (
        not audio_path.exists()
        or audio_path.stat().st_size
        == 0
    ):
        pipeline_step(
            run_dir,
            "generate_audio",
        )

    pipeline_step(
        run_dir,
        "align_audio",
    )

    if (
        not audio_path.exists()
        or audio_path.stat().st_size
        == 0
    ):
        raise DemoOrchestratorError(
            "No usable voiceover was created."
        )

    return audio_path


def publish_generated_components(
    run_dir,
):
    pipeline_step(
        run_dir,
        "publish_dynamic",
    )

    report_path = (
        run_dir
        / "05g_dynamic_integration"
        / "dynamic_publish_report.json"
    )

    if not report_path.exists():
        raise DemoOrchestratorError(
            "Generated-component publish "
            "report is missing."
        )

    report = load_json(
        report_path
    )

    if report.get(
        "status"
    ) != "published":
        raise DemoOrchestratorError(
            "Generated component publication "
            "did not succeed."
        )

    return report


def compile_master_render_spec(
    run_dir,
):
    pipeline_step(
        run_dir,
        "compile_render_spec",
    )

    render_spec = (
        run_dir
        / "08_render_spec"
        / "render_spec.json"
    )

    validation = (
        run_dir
        / "08_render_spec"
        / "render_validation.json"
    )

    if not render_spec.exists():
        raise DemoOrchestratorError(
            "Master render specification "
            "is missing."
        )

    if validation.exists():
        report = load_json(
            validation
        )

        if not report.get(
            "single_composition"
        ):
            raise DemoOrchestratorError(
                "Render specification is not "
                "single-composition."
            )

    return render_spec


def render_master_video(
    run_dir,
):
    pipeline_step(
        run_dir,
        "render_video",
    )

    expected = (
        run_dir
        / "09_video"
        / "candidate_video.mp4"
    )

    if (
        expected.exists()
        and expected.stat().st_size
        > 0
    ):
        return expected

    video_dir = (
        run_dir
        / "09_video"
    )

    candidates = (
        [
            path
            for path
            in video_dir.glob(
                "*.mp4"
            )
            if (
                path.exists()
                and path.stat().st_size
                > 0
            )
        ]
        if video_dir.exists()
        else []
    )

    if not candidates:
        raise DemoOrchestratorError(
            "Master renderer produced "
            f"no MP4 in {video_dir}."
        )

    return max(
        candidates,
        key=lambda path:
            path.stat().st_mtime,
    )


def run_optional_final_qa(
    run_dir,
    args,
    output_video,
):
    if not args.final_qa:
        return None

    run_command(
        [
            sys.executable,
            "-m",
            (
                "app.pipeline."
                "step_10b_final_dynamic_video_qa"
            ),
            "--run-dir",
            str(run_dir),
            "--timeout-seconds",
            str(
                args.final_qa_timeout
            ),
        ],
        allowed_codes=(
            0,
            2,
        ),
    )

    candidates = [
        (
            run_dir
            / "09_video"
            / "final_qa"
            / "final_video_qa_report.json"
        ),
        (
            run_dir
            / "10_dynamic_render"
            / "final_qa"
            / "final_video_qa_report.json"
        ),
    ]

    report_path = next(
        (
            path
            for path in candidates
            if path.exists()
        ),
        None,
    )

    if report_path is None:
        print(
            "\nFinal QA report not found. "
            "Video remains available:"
        )

        print(
            output_video
        )

        return None

    return (
        report_path,
        load_json(
            report_path
        ),
    )


def run_demo(args):
    run_dir = (
        resolve_run(
            args
        )
    )

    print(
        "\nRUN DIRECTORY:",
        run_dir,
    )

    state_path = (
        run_dir
        / "demo_orchestrator_state.json"
    )

    state = {
        "run_dir":
            str(run_dir),

        "status":
            "running",

        "render_architecture":
            "single_master_composition_v2",
    }

    save_json(
        state,
        state_path,
    )

    creative_plan_path = (
        run_dir
        / "05b_creative_plan"
        / "creative_plan.json"
    )

    if not creative_plan_path.exists():
        pipeline_step(
            run_dir,
            "creative_plan",
        )

    artifact_manifest = (
        run_dir
        / "05c_artifacts"
        / "artifact_manifest_final.json"
    )

    if not artifact_manifest.exists():
        pipeline_step(
            run_dir,
            "artifacts",
        )

        command = [
            sys.executable,
            "-m",
            (
                "app.pipeline."
                "step_05d_generate_artifacts"
            ),
            "--run-dir",
            str(run_dir),
        ]

        if args.generate_images:
            command.append(
                "--generate-images"
            )

        run_command(
            command
        )

    pending = (
        artifact_gate(
            run_dir
        )
    )

    if pending:
        state.update(
            {
                "status":
                    "awaiting_artifact_review",

                "pending_artifacts":
                    pending,
            }
        )

        save_json(
            state,
            state_path,
        )

        print_artifact_instructions(
            run_dir,
            pending,
        )

        return 20

    regenerate_components_if_needed(
        run_dir,
        args,
    )

    generated_count = (
        selected_scene_count(
            run_dir
        )
    )

    publish_report = {
        "status":
            "not_required",

        "published_count":
            0,
    }

    if generated_count > 0:
        pipeline_step(
            run_dir,
            "component_review",
        )

        if args.auto_approve_safe:
            auto_approve_components(
                run_dir,
                args.reviewer,
            )

            pipeline_step(
                run_dir,
                "component_review",
            )

        else:
            state[
                "status"
            ] = (
                "awaiting_component_review"
            )

            save_json(
                state,
                state_path,
            )

            return 21

        review_path = (
            run_dir
            / "05d_generated_components"
            / "component_review_summary.json"
        )

        if not review_path.exists():
            raise DemoOrchestratorError(
                "Component review summary "
                "is missing."
            )

        review = load_json(
            review_path
        )

        if not review.get(
            "ready_for_phase_5"
        ):
            raise DemoOrchestratorError(
                "Component review is not "
                "ready for compilation."
            )

        compiled = (
            compile_and_repair(
                run_dir,
                args,
            )
        )

        if compiled:
            smoke_result = (
                runtime_smoke_check(
                    run_dir,
                    args,
                )
            )

            if smoke_result.get(
                "publish_generated"
            ):
                publish_report = (
                    publish_generated_components(
                        run_dir
                    )
                )

            else:
                print(
                    "\nNo generated components "
                    "survived the runtime gate."
                )

                print(
                    "Continuing with library "
                    "renderers."
                )

        else:
            print(
                "\nNo generated components "
                "survived compilation."
            )

            print(
                "Continuing with library "
                "renderers."
            )

    else:
        print(
            "\nNo generated scenes planned. "
            "Using library renderers."
        )

    ensure_audio(
        run_dir
    )

    compile_master_render_spec(
        run_dir
    )

    output_video = (
        render_master_video(
            run_dir
        )
    )

    state[
        "output_video"
    ] = str(
        output_video
    )

    state[
        "published_generated_components"
    ] = publish_report.get(
        "published_count",
        0,
    )

    qa_result = (
        run_optional_final_qa(
            run_dir,
            args,
            output_video,
        )
    )

    if qa_result is not None:
        (
            report_path,
            final_report,
        ) = qa_result

        state[
            "final_qa_report"
        ] = str(
            report_path
        )

        if not final_report.get(
            "ready_for_final_approval"
        ):
            state[
                "status"
            ] = (
                "final_video_created_"
                "qa_warning"
            )

            save_json(
                state,
                state_path,
            )

            print(
                "\nFINAL VIDEO CREATED:",
                output_video,
            )

            return 23

    if args.auto_approve_final:
        run_command(
            [
                sys.executable,
                "-m",
                (
                    "app.pipeline."
                    "approve_final_video"
                ),
                "--run-dir",
                str(run_dir),
                "--reviewer",
                args.reviewer,
                "--decision",
                "approved_for_demo",
                "--notes",
                (
                    "Demo approval for "
                    "single-composition render."
                ),
            ]
        )

        state[
            "status"
        ] = "completed"

    else:
        state[
            "status"
        ] = (
            "final_video_created"
        )

    save_json(
        state,
        state_path,
    )

    print(
        "\nDEMO VIDEO:",
        output_video,
    )

    return 0


def build_parser():
    parser = (
        argparse.ArgumentParser(
            description=(
                "Run the resumable "
                "AI-assisted candidate-video "
                "demo pipeline."
            )
        )
    )

    source = (
        parser
        .add_mutually_exclusive_group(
            required=True
        )
    )

    source.add_argument(
        "--input"
    )

    source.add_argument(
        "--run-dir"
    )

    parser.add_argument(
        "--generate-images",
        action="store_true",
    )

    parser.add_argument(
        "--dynamic-scenes",
        type=int,
        default=5,
    )

    parser.add_argument(
        "--auto-approve-safe",
        action="store_true",
    )

    parser.add_argument(
        "--auto-approve-final",
        action="store_true",
    )

    parser.add_argument(
        "--reviewer",
        default="Demo Reviewer",
    )

    parser.add_argument(
        "--repair-attempts",
        type=int,
        default=2,
    )

    parser.add_argument(
        "--compile-timeout",
        type=int,
        default=120,
    )

    # Smoke rendering is mandatory.
    # This flag adds optional AI Visual QA.
    parser.add_argument(
        "--preview-qa",
        action="store_true",
    )

    parser.add_argument(
        "--preview-timeout",
        type=int,
        default=180,
    )

    # Retained for CLI compatibility.
    parser.add_argument(
        "--render-timeout",
        type=int,
        default=900,
    )

    parser.add_argument(
        "--final-qa",
        action="store_true",
    )

    parser.add_argument(
        "--final-qa-timeout",
        type=int,
        default=300,
    )

    return parser


def main():
    args = (
        build_parser()
        .parse_args()
    )

    try:
        return run_demo(
            args
        )

    except KeyboardInterrupt:
        print(
            "\nDEMO ORCHESTRATOR INTERRUPTED"
        )

        return 130

    except Exception as error:
        print(
            "\nDEMO ORCHESTRATOR FAILED"
        )

        print(
            f"{type(error).__name__}: "
            f"{error}"
        )

        return 1


if __name__ == "__main__":
    raise SystemExit(
        main()
    )