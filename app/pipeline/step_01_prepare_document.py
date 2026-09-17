"""Pipeline Step 01: Prepare a candidate dossier PDF."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from app.config import RUNS_DIR, create_project_directories, settings
from app.services.pdf_service import PDFService
from app.utils.files import copy_file, safe_filename
from app.utils.json_utils import save_json
from app.utils.logging import get_logger, setup_logging
from app.utils.run_manager import RunManager, create_run


STEP_NAME = "prepare_document"
logger = get_logger(__name__)


def build_argument_parser() -> argparse.ArgumentParser:
    """Create the command-line argument parser."""

    parser = argparse.ArgumentParser(
        description=(
            "Prepare a candidate dossier PDF for downstream extraction."
        )
    )

    parser.add_argument(
        "--input",
        required=True,
        help="Path to the source candidate dossier PDF.",
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
        "--video-mode",
        choices=[
            "automatic",
            "snapshot",
            "standard",
            "detailed",
        ],
        default=settings.default_video_mode,
        help="Preferred video length mode.",
    )

    parser.add_argument(
        "--include-compensation",
        action="store_true",
        help="Allow compensation content in later pipeline stages.",
    )

    parser.add_argument(
        "--exclude-availability",
        action="store_true",
        help="Exclude availability content from later pipeline stages.",
    )

    return parser


def build_run_configuration(
    arguments: argparse.Namespace,
) -> dict[str, Any]:
    """Build the configuration stored with a pipeline run."""

    return {
        "video_mode": arguments.video_mode,
        "include_compensation": arguments.include_compensation,
        "include_availability": not arguments.exclude_availability,
        "pdf_render_dpi": arguments.render_dpi,
        "video_width": settings.video_width,
        "video_height": settings.video_height,
        "video_fps": settings.video_fps,
    }


def prepare_document(
    input_file: str | Path,
    render_dpi: int,
    configuration: dict[str, Any],
) -> Path:
    """Create a run and prepare its source PDF."""

    create_project_directories()

    source_path = Path(input_file).expanduser().resolve()

    if not source_path.exists():
        raise FileNotFoundError(
            f"Input PDF was not found: {source_path}"
        )

    if not source_path.is_file():
        raise ValueError(
            f"Input path is not a file: {source_path}"
        )

    run_directory = create_run(
        input_filename=source_path.name,
        configuration=configuration,
        runs_directory=RUNS_DIR,
    )

    run_manager = RunManager(run_directory)

    log_file = run_manager.get_directory("logs") / "pipeline.log"
    setup_logging(
        log_level=settings.log_level,
        log_file=log_file,
    )

    logger.info("Created run directory: %s", run_directory)
    logger.info("Source dossier: %s", source_path)

    run_manager.start_step(STEP_NAME)

    try:
        input_directory = run_manager.get_directory("input")
        document_directory = run_manager.get_directory("document")

        safe_input_name = safe_filename(source_path.name)
        copied_pdf_path = input_directory / safe_input_name

        copy_file(
            source=source_path,
            destination=copied_pdf_path,
            overwrite=False,
        )

        logger.info(
            "Copied source PDF into the run directory: %s",
            copied_pdf_path,
        )

        input_manifest = {
            "original_filename": source_path.name,
            "stored_filename": safe_input_name,
            "original_path": str(source_path),
            "stored_path": str(copied_pdf_path),
            "classification": "restricted_confidential",
        }

        input_manifest_path = input_directory / "input_manifest.json"
        save_json(input_manifest, input_manifest_path)

        pdf_service = PDFService(render_dpi=render_dpi)

        preparation_result = pdf_service.prepare_pdf(
            pdf_path=copied_pdf_path,
            output_directory=document_directory,
        )

        outputs = {
            "run_directory": str(run_directory),
            "input_pdf": str(copied_pdf_path),
            "input_manifest": str(input_manifest_path),
            "document_metadata": str(
                document_directory / "document.json"
            ),
            "native_text": str(
                document_directory / "native_text.json"
            ),
            "full_text": str(
                document_directory / "full_text.txt"
            ),
            "pages_directory": str(
                document_directory / "pages"
            ),
            "page_count": preparation_result.page_count,
        }

        run_manager.complete_step(
            step_name=STEP_NAME,
            outputs=outputs,
        )

        logger.info(
            "Document preparation completed successfully."
        )

        return run_directory

    except Exception as error:
        error_message = f"{type(error).__name__}: {error}"

        run_manager.fail_step(
            step_name=STEP_NAME,
            error_message=error_message,
        )

        logger.exception(
            "Document preparation failed: %s",
            error_message,
        )

        raise


def print_result_summary(run_directory: Path) -> None:
    """Print the locations of generated artifacts."""

    run_manager = RunManager(run_directory)
    document_directory = run_manager.get_directory("document")
    input_directory = run_manager.get_directory("input")

    print()
    print("=" * 68)
    print("STEP 01 COMPLETED")
    print("=" * 68)
    print(f"Run directory:       {run_directory}")
    print(f"Copied input:        {input_directory}")
    print(f"Document metadata:   {document_directory / 'document.json'}")
    print(f"Native text JSON:    {document_directory / 'native_text.json'}")
    print(f"Combined text:       {document_directory / 'full_text.txt'}")
    print(f"Rendered pages:      {document_directory / 'pages'}")
    print(f"Pipeline state:      {run_directory / 'run.json'}")
    print("=" * 68)
    print()


def main() -> int:
    """Run the document-preparation stage from the command line."""

    parser = build_argument_parser()
    arguments = parser.parse_args()

    configuration = build_run_configuration(arguments)

    try:
        run_directory = prepare_document(
            input_file=arguments.input,
            render_dpi=arguments.render_dpi,
            configuration=configuration,
        )

        print_result_summary(run_directory)
        return 0

    except Exception as error:
        print()
        print("STEP 01 FAILED")
        print(f"Error: {type(error).__name__}: {error}")
        print()
        return 1


if __name__ == "__main__":
    sys.exit(main())
