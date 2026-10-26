"""Run the complete AI-assisted candidate-video demo workflow.

Architecture v2:

dossier
-> content selection
-> storyboard
-> creative plan
-> artifacts
-> generated components
-> deterministic source validation
-> isolated TypeScript compilation per generated scene
-> one compiler-guided correction for each failed scene
-> mandatory Remotion runtime smoke render
-> publish surviving generated components
-> audio
-> master render specification
-> one CandidateVideo render

Failed visual assets and generated scenes use per-item safe fallbacks; one
generated scene's compile failure does not discard another scene's success.
Each generated scene gets at most one compiler-guided correction attempt.
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


def ensure_storyboard(run_dir):
    storyboard_path = (
        run_dir
        / "05_storyboard"
        / "storyboard.json"
    )
    if storyboard_path.exists():
        return

    pipeline_step(run_dir, "storyboard")

    if not storyboard_path.exists():
        raise DemoOrchestratorError(
            "Storyboard generation completed without producing "
            f"the expected file: {storyboard_path}"
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

        content_path = (
            path
            / "04_video_content"
            / "video_content.json"
        )
        if not content_path.exists():
            completed = subprocess.run(
                [
                    sys.executable,
                    "run_pipeline.py",
                    "--run-dir",
                    str(path),
                    "--to-step",
                    "select_video_content",
                ],
                cwd=str(PROJECT_ROOT),
                check=False,
            )
            if completed.returncode != 0:
                raise DemoOrchestratorError(
                    "Dossier extraction, validation, or content selection "
                    "failed. Review: "
                    f"{path / 'run.json'}"
                )

        if not content_path.exists():
            raise DemoOrchestratorError(
                "Content selection completed without producing "
                f"the expected file: {content_path}"
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

    completed = subprocess.run(
        [
            sys.executable,
            "run_pipeline.py",
            "--input",
            str(source),
            "--to-step",
            "select_video_content",
        ],
        cwd=str(PROJECT_ROOT),
        check=False,
    )

    run_dir = newest_run()

    if completed.returncode == 0:
        content_path = (
            run_dir
            / "04_video_content"
            / "video_content.json"
        )
        if not content_path.exists():
            raise DemoOrchestratorError(
                "Content selection completed without producing "
                f"the expected file: {content_path}"
            )
        return run_dir

    raise DemoOrchestratorError(
        "Dossier preparation or content selection failed. Review: "
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


def write_empty_compiled_manifest(run_dir):
    compilation_dir = run_dir / "05e_component_compilation"
    compilation_dir.mkdir(parents=True, exist_ok=True)
    save_json(
        {
            "schema_version": "1.0",
            "compiled_components": [],
            "compiled_count": 0,
            "workspace_registry": None,
        },
        compilation_dir / "approved_compiled_components.json",
    )


def compile_components_once(
    run_dir,
    args,
):
    if (
        approved_generated_scene_count(
            run_dir
        )
        == 0
    ):
        print(
            "\nNo validated generated components; "
            "using library fallbacks."
        )
        write_empty_compiled_manifest(run_dir)
        return False

    print("\nCompiling generated components once.")
    write_empty_compiled_manifest(run_dir)
    run_command(
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
    compilation_report_path = (
        run_dir
        / "05e_component_compilation"
        / "compilation_report.json"
    )
    if not compilation_report_path.exists():
        print(
            "\nCompilation produced no report; generated scenes will use "
            "their fallbacks."
        )
        return False

    compilation_report = load_json(compilation_report_path)
    failed_scene_count = sum(
        1
        for item in compilation_report.get("components", [])
        if item.get("compile_status") == "compiler_error"
    )
    if failed_scene_count:
        print(
            f"\nRunning one compiler-guided correction pass for "
            f"{failed_scene_count} failed scene(s)."
        )
        run_command(
            [
                sys.executable,
                "-m",
                "app.pipeline.step_05i_repair_compiler_errors",
                "--run-dir",
                str(run_dir),
                "--timeout-seconds",
                str(args.compile_timeout),
            ],
            allowed_codes=(0,),
        )

    compiled_manifest_path = (
        run_dir
        / "05e_component_compilation"
        / "approved_compiled_components.json"
    )
    compiled_count = (
        len(
            load_json(compiled_manifest_path).get(
                "compiled_components",
                [],
            )
        )
        if compiled_manifest_path.exists()
        else 0
    )
    print(
        f"\nGenerated scenes available after compilation and correction: "
        f"{compiled_count}."
    )
    return compiled_count > 0


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

    if getattr(args, "preview_qa", True):
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
        or not item.get("visual_approved")
        or item.get("status") != "visual_approved"
    ]


def runtime_smoke_check(
    run_dir,
    args,
):
    """Visually assess generated scenes, repair once, and retain verified scenes."""

    approved_before = (
        approved_generated_scene_count(
            run_dir
        )
    )

    if approved_before == 0:
        write_empty_compiled_manifest(run_dir)
        return {
            "publish_generated":
                False,

            "all_fell_back":
                True,

            "remaining_generated":
                0,
        }

    print(
        "\nRunning generated-component "
        "visual quality checks."
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

    repairable = [
        item
        for item in preview.get("results", [])
        if item.get("status") == "visual_repair_required"
        and item.get("visual_qa")
    ]
    if repairable:
        save_json(
            preview,
            run_dir
            / "05f_component_previews"
            / "preview_qa_report_initial.json",
        )
        print(
            "\nVisual QA rejected "
            f"{len(repairable)} scene(s); attempting one targeted correction "
            "per scene using the rendered frames."
        )
        pipeline_step(run_dir, "visual_repair")
        repair_report_path = (
            run_dir
            / "05d_generated_components"
            / "visual_repair_report.json"
        )
        repair_report = (
            load_json(repair_report_path)
            if repair_report_path.exists()
            else {"repaired_count": 0}
        )
        if repair_report.get("repaired_count", 0):
            pipeline_step(run_dir, "component_review")
            auto_approve_components(
                run_dir,
                getattr(args, "reviewer", "Demo Reviewer"),
            )
            pipeline_step(run_dir, "component_review")
            if compile_components_once(run_dir, args):
                print("\nRechecking scenes after visual correction.")
                run_command(
                    runtime_smoke_command(run_dir, args),
                    allowed_codes=(0, 2),
                )
                if not preview_path.exists():
                    raise DemoOrchestratorError(
                        "Visual recheck report missing after component correction: "
                        f"{preview_path}"
                    )
                preview = load_json(preview_path)

    approved_scene_ids = {
        item.get("scene_id")
        for item in preview.get("results", [])
        if item.get("preview_rendered")
        and item.get("visual_approved")
        and item.get("status") == "visual_approved"
    }
    compiled_path = (
        run_dir
        / "05e_component_compilation"
        / "approved_compiled_components.json"
    )
    compiled_manifest = load_json(compiled_path)
    compiled_components = compiled_manifest.get("compiled_components", [])
    surviving = [
        item
        for item in compiled_components
        if item.get("scene_id") in approved_scene_ids
    ]
    compiled_manifest["compiled_components"] = surviving
    compiled_manifest["compiled_count"] = len(surviving)
    save_json(compiled_manifest, compiled_path)

    failed = runtime_smoke_failures(preview)
    if not failed:
        print(
            "\nAll generated components passed visual QA and runtime checks."
        )

        return {
            "publish_generated":
                True,

            "all_fell_back":
                False,

            "remaining_generated": len(surviving),

            "preview":
                preview,
        }

    rejected_count = len(compiled_components) - len(surviving)
    if rejected_count:
        print(
            "\nVisual assessment or runtime checks rejected "
            f"{rejected_count} scene(s); those scenes will use fallbacks."
        )
    final_count = len(surviving)

    return {
        "publish_generated":
            final_count > 0,

        "all_fell_back":
            final_count == 0,

        "remaining_generated":
            final_count,

        "preview":
            preview,
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

    qa_code = run_command(
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
            1,
        ),
    )

    if qa_code == 1:
        print(
            "\nFinal QA could not complete. "
            "The rendered video remains available:"
        )
        print(output_video)
        return None

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

    ensure_storyboard(run_dir)

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
    if not creative_plan_path.exists():
        raise DemoOrchestratorError(
            "Creative-plan generation completed without producing "
            f"the expected file: {creative_plan_path}"
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

        command.append(
            "--generate-images"
            if args.generate_images
            else "--skip-image-generation"
        )

        run_command(
            command
        )
    if not artifact_manifest.exists():
        raise DemoOrchestratorError(
            "Artifact generation completed without producing "
            f"the expected manifest: {artifact_manifest}"
        )

    pending = (
        artifact_gate(
            run_dir
        )
    )

    if pending:
        print(
            f"\n{len(pending)} artifact(s) need review. "
            "Continuing without them; scene fallbacks will be used."
        )
        state["omitted_unapproved_artifacts"] = [
            item.get("artifact_id")
            for item in pending
        ]

    regenerate_components_if_needed(
        run_dir,
        args,
    )

    generated_count = (
        selected_scene_count(
            run_dir
        )
    )

    publish_report = {"status": "not_required", "published_count": 0}

    if generated_count > 0:
        pipeline_step(
            run_dir,
            "component_review",
        )
        auto_approve_components(
            run_dir,
            args.reviewer,
        )
        pipeline_step(
            run_dir,
            "component_review",
        )

        compiled = compile_components_once(run_dir, args)

        if compiled:
            runtime_smoke_check(
                run_dir,
                args,
            )
    else:
        print(
            "\nNo generated scenes planned; using library fallbacks."
        )
        write_empty_compiled_manifest(run_dir)

    # Always publish the run's registry, including an empty one, so a prior
    # run's generated components can never leak into this video's render.
    publish_report = publish_generated_components(run_dir)

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

        if final_report.get("quality_concerns_found"):
            print(
                "\nFinal QA found quality concerns; "
                "the video is still available at:",
                output_video,
            )
        state["final_qa_status"] = final_report.get("status")

    state["status"] = "completed"

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

    image_generation = parser.add_mutually_exclusive_group()
    image_generation.add_argument(
        "--generate-images",
        dest="generate_images",
        action="store_true",
        help="Generate planned decorative image assets (enabled by default).",
    )
    image_generation.add_argument(
        "--skip-image-generation",
        dest="generate_images",
        action="store_false",
        help="Skip decorative image generation for a lower-cost run.",
    )
    parser.set_defaults(generate_images=True)

    parser.add_argument(
        "--dynamic-scenes",
        type=int,
        default=5,
    )

    parser.add_argument(
        "--auto-approve-safe",
        action="store_true",
        help="Retained for compatibility; safe validated components are auto-approved.",
    )

    parser.add_argument(
        "--auto-approve-final",
        action="store_true",
        help="Retained for compatibility; final video approval is not required.",
    )

    parser.add_argument(
        "--reviewer",
        default="Demo Reviewer",
    )

    parser.add_argument(
        "--repair-attempts",
        type=int,
        default=2,
        help="Retained for compatibility; this flow does not repair/retry generated code.",
    )

    parser.add_argument(
        "--compile-timeout",
        type=int,
        default=120,
    )

    # Generated components require visual assessment before publication.
    parser.add_argument(
        "--preview-qa",
        action="store_true",
        default=True,
        help=argparse.SUPPRESS,
    )

    parser.add_argument(
        "--skip-preview-qa",
        dest="preview_qa",
        action="store_false",
        help=(
            "Skip multimodal preview assessment. Generated components will "
            "use fallbacks because unassessed scenes are not publishable."
        ),
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
        default=True,
        help="Run final video visual QA (enabled by default).",
    )

    parser.add_argument(
        "--skip-final-qa",
        dest="final_qa",
        action="store_false",
        help="Skip the final visual-quality assessment.",
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