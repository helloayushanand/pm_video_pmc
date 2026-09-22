"""Command-line orchestrator for the candidate video pipeline."""

import argparse
import sys
from pathlib import Path

from app.config import create_project_directories, settings
from app.pipeline.step_01_prepare_document import prepare_document
from app.pipeline.step_02_extract_dossier import extract_dossier
from app.pipeline.step_03_validate_extraction import validate_dossier
from app.pipeline.step_04_select_video_content import select_video_content
from app.pipeline.step_05_generate_storyboard import generate_storyboard
from app.pipeline.step_06_generate_audio import generate_audio
from app.pipeline.step_07_align_audio import align_audio
from app.pipeline.step_08_compile_render_spec import compile_render_spec
from app.pipeline.step_09_render_video import render_video
from app.pipeline.step_10_run_quality_checks import run_quality_checks
from app.utils.logging import setup_logging
from app.utils.run_manager import PIPELINE_STEPS, RunManager


STEP_ALIASES = {
    "prepare": "prepare_document",
    "prepare_document": "prepare_document",
    "extract": "extract_dossier",
    "extract_dossier": "extract_dossier",
    "validate": "validate_extraction",
    "validate_extraction": "validate_extraction",
    "content": "select_video_content",
    "select_video_content": "select_video_content",
    "storyboard": "generate_storyboard",
    "generate_storyboard": "generate_storyboard",
    "audio": "generate_audio",
    "generate_audio": "generate_audio",
    "alignment": "align_audio",
    "align_audio": "align_audio",
    "render_spec": "compile_render_spec",
    "compile_render_spec": "compile_render_spec",
    "render": "render_video",
    "render_video": "render_video",
    "quality": "run_quality_checks",
    "run_quality_checks": "run_quality_checks",
}


def build_argument_parser():
    """Create the root pipeline command-line parser."""

    parser = argparse.ArgumentParser(
        description=(
            "Run the local candidate dossier-to-video pipeline."
        )
    )

    source_group = parser.add_mutually_exclusive_group(
        required=True
    )

    source_group.add_argument(
        "--input",
        help=(
            "Path to a candidate dossier PDF. "
            "A new pipeline run will be created."
        ),
    )

    source_group.add_argument(
        "--run-dir",
        help=(
            "Path to an existing pipeline run directory. "
            "Use this to continue or rerun pipeline stages."
        ),
    )

    parser.add_argument(
        "--from-step",
        choices=list(STEP_ALIASES),
        default=None,
        help=(
            "Start from this pipeline step. "
            "Use this with an existing run."
        ),
    )

    parser.add_argument(
        "--to-step",
        choices=list(STEP_ALIASES),
        default=None,
        help=(
            "Stop after this pipeline step. "
            "The default is to run through quality checks."
        ),
    )

    parser.add_argument(
        "--only-step",
        choices=list(STEP_ALIASES),
        default=None,
        help="Run only one pipeline step.",
    )

    parser.add_argument(
        "--model",
        default=settings.openai_model,
        help=(
            "OpenAI model used for dossier extraction, "
            "content selection, and storyboard generation. "
            f"Default: {settings.openai_model}"
        ),
    )

    parser.add_argument(
        "--render-dpi",
        type=int,
        default=settings.pdf_render_dpi,
        help=(
            "Resolution used when rendering PDF pages. "
            f"Default: {settings.pdf_render_dpi}"
        ),
    )

    parser.add_argument(
        "--image-detail",
        choices=[
            "low",
            "high",
            "auto",
        ],
        default="high",
        help=(
            "OpenAI image-detail level used for dossier extraction. "
            "Default: high"
        ),
    )

    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help=(
            "Optional dossier page limit for lower-cost "
            "OpenAI extraction testing."
        ),
    )

    parser.add_argument(
        "--video-mode",
        choices=[
            "automatic",
            "snapshot",
            "standard",
            "detailed",
        ],
        default=settings.default_video_mode,
        help=(
            "Preferred video-duration mode. "
            f"Default: {settings.default_video_mode}"
        ),
    )

    parser.add_argument(
        "--include-compensation",
        action="store_true",
        help=(
            "Permit compensation information in later "
            "internal video-generation stages."
        ),
    )

    parser.add_argument(
        "--exclude-availability",
        action="store_true",
        help=(
            "Exclude candidate availability from video content."
        ),
    )

    parser.add_argument(
        "--voice",
        default=settings.openai_tts_voice,
        help=(
            "OpenAI text-to-speech voice. "
            f"Default: {settings.openai_tts_voice}"
        ),
    )

    parser.add_argument(
        "--tts-model",
        default=settings.openai_tts_model,
        help=(
            "OpenAI text-to-speech model. "
            f"Default: {settings.openai_tts_model}"
        ),
    )

    return parser


def normalise_step_name(step_name):
    """Resolve a short alias to its complete pipeline step name."""

    if step_name is None:
        return None

    return STEP_ALIASES[step_name]


def build_configuration(arguments):
    """Create configuration for a new pipeline run."""

    return {
        "video_mode": arguments.video_mode,
        "include_compensation": (
            arguments.include_compensation
        ),
        "include_availability": (
            not arguments.exclude_availability
        ),
        "pdf_render_dpi": arguments.render_dpi,
        "image_detail": arguments.image_detail,
        "openai_model": arguments.model,
        "openai_tts_model": arguments.tts_model,
        "openai_tts_voice": arguments.voice,
        "video_width": settings.video_width,
        "video_height": settings.video_height,
        "video_fps": settings.video_fps,
    }


def resolve_execution_range(
    arguments,
    existing_run,
):
    """Determine which pipeline stages should execute."""

    if arguments.only_step:
        selected_step = normalise_step_name(
            arguments.only_step
        )

        return [selected_step]

    if existing_run:
        from_step = (
            normalise_step_name(arguments.from_step)
            or "extract_dossier"
        )
    else:
        from_step = "prepare_document"

    to_step = (
        normalise_step_name(arguments.to_step)
        or "run_quality_checks"
    )

    start_index = PIPELINE_STEPS.index(from_step)
    end_index = PIPELINE_STEPS.index(to_step)

    if start_index > end_index:
        raise ValueError(
            "--from-step cannot occur after --to-step."
        )

    return PIPELINE_STEPS[
        start_index : end_index + 1
    ]


def execute_step(
    step_name,
    run_directory,
    arguments,
):
    """Execute one pipeline stage."""

    print()
    print("=" * 72)
    print(f"RUNNING: {step_name}")
    print("=" * 72)
    print()

    if step_name == "prepare_document":
        raise ValueError(
            "The prepare_document step is handled automatically "
            "when a new --input PDF is supplied."
        )

    if step_name == "extract_dossier":
        return extract_dossier(
            run_directory=run_directory,
            model=arguments.model,
            image_detail=arguments.image_detail,
            max_pages=arguments.max_pages,
        )

    if step_name == "validate_extraction":
        return validate_dossier(
            run_directory
        )

    if step_name == "select_video_content":
        return select_video_content(
            run_directory=run_directory,
            model=arguments.model,
        )

    if step_name == "generate_storyboard":
        return generate_storyboard(
            run_directory=run_directory,
            model=arguments.model,
        )

    if step_name == "generate_audio":
        return generate_audio(
            run_directory=run_directory,
            voice=arguments.voice,
            model=arguments.tts_model,
        )

    if step_name == "align_audio":
        return align_audio(
            run_directory
        )

    if step_name == "compile_render_spec":
        return compile_render_spec(
            run_directory
        )

    if step_name == "render_video":
        return render_video(
            run_directory
        )

    if step_name == "run_quality_checks":
        return run_quality_checks(
            run_directory
        )

    raise ValueError(
        f"Unsupported pipeline step: {step_name}"
    )


def print_run_summary(run_directory):
    """Print a safe summary of the current pipeline run."""

    manager = RunManager(run_directory)
    state = manager.state

    print()
    print("=" * 72)
    print("PIPELINE EXECUTION FINISHED")
    print("=" * 72)
    print(f"Run ID:      {state['run_id']}")
    print(f"Run folder:  {run_directory}")
    print(f"Status:      {state['status']}")
    print()
    print("Step statuses:")

    for step_name, step_data in state["steps"].items():
        print(
            f"  {step_name:<28} "
            f"{step_data['status']}"
        )

    print("=" * 72)
    print()


def validate_arguments(
    parser,
    arguments,
):
    """Validate command-line argument combinations."""

    if arguments.max_pages is not None:
        if arguments.max_pages <= 0:
            parser.error(
                "--max-pages must be greater than zero."
            )

    if arguments.render_dpi <= 0:
        parser.error(
            "--render-dpi must be greater than zero."
        )

    if arguments.input and arguments.from_step:
        parser.error(
            "--from-step cannot be used with --input. "
            "A new run always starts with document preparation."
        )

    if arguments.input and arguments.only_step:
        selected_step = normalise_step_name(
            arguments.only_step
        )

        if selected_step != "prepare_document":
            parser.error(
                "When using --input, --only-step must be "
                "'prepare' or 'prepare_document'."
            )

    if arguments.run_dir and arguments.only_step:
        selected_step = normalise_step_name(
            arguments.only_step
        )

        if selected_step == "prepare_document":
            parser.error(
                "The prepare_document step requires --input, "
                "not --run-dir."
            )


def main():
    """Run the local candidate video pipeline."""

    parser = build_argument_parser()
    arguments = parser.parse_args()

    validate_arguments(
        parser=parser,
        arguments=arguments,
    )

    create_project_directories()

    setup_logging(
        log_level=settings.log_level
    )

    existing_run = bool(arguments.run_dir)
    run_directory = None

    try:
        steps_to_run = resolve_execution_range(
            arguments=arguments,
            existing_run=existing_run,
        )

        if arguments.input:
            if "prepare_document" not in steps_to_run:
                raise ValueError(
                    "A new input requires the "
                    "prepare_document step."
                )

            configuration = build_configuration(
                arguments
            )

            run_directory = prepare_document(
                input_file=arguments.input,
                render_dpi=arguments.render_dpi,
                configuration=configuration,
            )

            remaining_steps = [
                step
                for step in steps_to_run
                if step != "prepare_document"
            ]

        else:
            run_directory = Path(
                arguments.run_dir
            ).expanduser().resolve()

            if not run_directory.exists():
                raise FileNotFoundError(
                    f"Run directory not found: "
                    f"{run_directory}"
                )

            if not run_directory.is_dir():
                raise ValueError(
                    f"Run path is not a directory: "
                    f"{run_directory}"
                )

            RunManager(run_directory)

            remaining_steps = steps_to_run

        for step_name in remaining_steps:
            execute_step(
                step_name=step_name,
                run_directory=run_directory,
                arguments=arguments,
            )

        print_run_summary(
            run_directory
        )

        return 0

    except KeyboardInterrupt:
        print()
        print("=" * 72)
        print("PIPELINE INTERRUPTED")
        print("=" * 72)
        print(
            "Pipeline execution was interrupted by the user."
        )

        if run_directory is not None:
            print(f"Run folder: {run_directory}")

        print("=" * 72)
        print()

        return 130

    except Exception as error:
        print()
        print("=" * 72)
        print("PIPELINE FAILED")
        print("=" * 72)
        print(
            f"Error type: {type(error).__name__}"
        )
        print(f"Details:    {error}")

        if run_directory is not None:
            print(f"Run folder: {run_directory}")
            print()
            print(
                "Review run.json and logs/pipeline.log "
                "inside the run directory."
            )

        print("=" * 72)
        print()

        return 1


if __name__ == "__main__":
    sys.exit(main())