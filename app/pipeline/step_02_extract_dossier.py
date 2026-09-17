"""Pipeline Step 02: Extract structured dossier data using OpenAI."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.config import settings
from app.services.vlm_service import OpenAIVLMService
from app.utils.logging import get_logger, setup_logging
from app.utils.run_manager import RunManager


STEP_NAME = "extract_dossier"
logger = get_logger(__name__)


def build_argument_parser():
    """Create the command-line argument parser."""

    parser = argparse.ArgumentParser(
        description=(
            "Extract structured candidate information from a prepared "
            "dossier using OpenAI vision."
        )
    )

    parser.add_argument(
        "--run-dir",
        required=True,
        help=(
            "Path to an existing pipeline run directory created "
            "by Step 01."
        ),
    )

    parser.add_argument(
        "--model",
        default=settings.openai_model,
        help=(
            "OpenAI model used for extraction. "
            f"Default: {settings.openai_model}"
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
            "Image detail level sent to OpenAI. "
            "Default: high."
        ),
    )

    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help=(
            "Optional maximum number of dossier pages to process. "
            "Useful for low-cost testing."
        ),
    )

    return parser


def validate_run_for_extraction(run_manager):
    """Validate that Step 01 artifacts exist."""

    document_directory = run_manager.get_directory("document")

    required_files = [
        document_directory / "document.json",
        document_directory / "native_text.json",
    ]

    missing_files = [
        path
        for path in required_files
        if not path.exists()
    ]

    pages_directory = document_directory / "pages"

    if not pages_directory.exists():
        missing_files.append(pages_directory)

    if pages_directory.exists():
        page_images = list(
            pages_directory.glob("page_*.png")
        )

        if not page_images:
            missing_files.append(
                pages_directory / "page_*.png"
            )

    if missing_files:
        formatted_files = "\n".join(
            f"  - {path}"
            for path in missing_files
        )

        raise FileNotFoundError(
            "The run is missing required Step 01 artifacts:\n"
            f"{formatted_files}\n\n"
            "Run Step 01 before running dossier extraction."
        )

    run_state = run_manager.state
    prepare_status = (
        run_state
        .get("steps", {})
        .get("prepare_document", {})
        .get("status")
    )

    if prepare_status != "completed":
        raise ValueError(
            "Step 01 is not marked as completed in run.json. "
            f"Current status: {prepare_status}"
        )


def extract_dossier(
    run_directory,
    model,
    image_detail,
    max_pages=None,
):
    """Execute structured dossier extraction for one run."""

    run_path = Path(run_directory).expanduser().resolve()

    if not run_path.exists():
        raise FileNotFoundError(
            f"Run directory not found: {run_path}"
        )

    if not run_path.is_dir():
        raise ValueError(
            f"Run path is not a directory: {run_path}"
        )

    run_manager = RunManager(run_path)

    log_file = (
        run_manager.get_directory("logs")
        / "pipeline.log"
    )

    setup_logging(
        log_level=settings.log_level,
        log_file=log_file,
    )

    validate_run_for_extraction(run_manager)

    document_directory = run_manager.get_directory(
        "document"
    )
    extraction_directory = run_manager.get_directory(
        "extraction"
    )

    logger.info(
        "Starting structured dossier extraction."
    )
    logger.info(
        "Run directory: %s",
        run_path,
    )
    logger.info(
        "OpenAI model: %s",
        model,
    )
    logger.info(
        "Image detail: %s",
        image_detail,
    )

    if max_pages is not None:
        logger.warning(
            "Page limit enabled. Only the first %s pages "
            "will be processed.",
            max_pages,
        )

    run_manager.start_step(STEP_NAME)

    try:
        vlm_service = OpenAIVLMService(
            model=model,
            image_detail=image_detail,
            max_pages=max_pages,
        )

        dossier = vlm_service.extract_dossier(
            document_directory=document_directory,
            output_directory=extraction_directory,
        )

        output_files = {
            "dossier_extracted": str(
                extraction_directory
                / "dossier_extracted.json"
            ),
            "raw_response": str(
                extraction_directory
                / "dossier_raw_response.json"
            ),
            "request_manifest": str(
                extraction_directory
                / "extraction_request.json"
            ),
            "extraction_metadata": str(
                extraction_directory
                / "extraction_metadata.json"
            ),
            "candidate_name": (
                dossier.candidate.full_name
            ),
            "career_entry_count": len(
                dossier.career_history
            ),
            "career_highlight_count": len(
                dossier.career_highlights
            ),
            "media_asset_count": len(
                dossier.media_assets
            ),
        }

        run_manager.complete_step(
            step_name=STEP_NAME,
            outputs=output_files,
        )

        logger.info(
            "Step 02 completed successfully."
        )

        return dossier

    except Exception as error:
        error_message = (
            f"{type(error).__name__}: {error}"
        )

        run_manager.fail_step(
            step_name=STEP_NAME,
            error_message=error_message,
        )

        logger.exception(
            "Step 02 failed: %s",
            error_message,
        )

        raise


def print_result_summary(
    run_directory,
    dossier,
):
    """Print a safe extraction summary without sensitive details."""

    run_manager = RunManager(run_directory)
    extraction_directory = (
        run_manager.get_directory("extraction")
    )

    print()
    print("=" * 72)
    print("STEP 02 COMPLETED")
    print("=" * 72)
    print(
        f"Candidate:              "
        f"{dossier.candidate.full_name}"
    )
    print(
        f"Career entries:         "
        f"{len(dossier.career_history)}"
    )
    print(
        f"Career highlights:      "
        f"{len(dossier.career_highlights)}"
    )
    print(
        f"Media assets detected:  "
        f"{len(dossier.media_assets)}"
    )
    print(
        f"Sensitive items flagged:"
        f"  {len(dossier.sensitive_information)}"
    )
    print()
    print(
        f"Structured dossier:     "
        f"{extraction_directory / 'dossier_extracted.json'}"
    )
    print(
        f"Extraction metadata:    "
        f"{extraction_directory / 'extraction_metadata.json'}"
    )
    print(
        f"Request manifest:       "
        f"{extraction_directory / 'extraction_request.json'}"
    )
    print(
        f"Raw response:           "
        f"{extraction_directory / 'dossier_raw_response.json'}"
    )
    print("=" * 72)
    print()
    print(
        "Important: Review dossier_extracted.json before "
        "continuing to the next stage."
    )
    print()


def main():
    """Run Step 02 from the command line."""

    parser = build_argument_parser()
    arguments = parser.parse_args()

    if arguments.max_pages is not None:
        if arguments.max_pages <= 0:
            parser.error(
                "--max-pages must be greater than zero."
            )

    try:
        dossier = extract_dossier(
            run_directory=arguments.run_dir,
            model=arguments.model,
            image_detail=arguments.image_detail,
            max_pages=arguments.max_pages,
        )

        print_result_summary(
            run_directory=Path(
                arguments.run_dir
            ).expanduser().resolve(),
            dossier=dossier,
        )

        return 0

    except Exception as error:
        print()
        print("=" * 72)
        print("STEP 02 FAILED")
        print("=" * 72)
        print(
            f"Error type: {type(error).__name__}"
        )
        print(
            f"Details:    {error}"
        )
        print()
        print(
            "Check the pipeline log inside the run's "
            "logs directory for more information."
        )
        print("=" * 72)
        print()

        return 1


if __name__ == "__main__":
    sys.exit(main())
