"""Pipeline Step 03: Validate the extracted candidate dossier."""

from __future__ import annotations

import argparse
import re
import sys
from copy import deepcopy
from pathlib import Path

from pydantic import ValidationError

from app.schemas.dossier import Dossier, SensitivityLevel
from app.utils.json_utils import load_json, save_json
from app.utils.logging import get_logger, setup_logging
from app.utils.run_manager import RunManager


STEP_NAME = "validate_extraction"
logger = get_logger(__name__)


RESTRICTED_PATTERNS = {
    "email_address": re.compile(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
    ),
    "phone_number": re.compile(
        r"(?<!\d)(?:\+?\d[\d\s().-]{7,}\d)(?!\d)"
    ),
}


def build_argument_parser():
    parser = argparse.ArgumentParser(
        description="Validate an extracted candidate dossier."
    )

    parser.add_argument(
        "--run-dir",
        required=True,
        help="Existing pipeline run directory.",
    )

    return parser


def add_issue(
    collection,
    code,
    message,
    location=None,
):
    collection.append(
        {
            "code": code,
            "message": message,
            "location": location,
        }
    )


def validate_source_references(
    dossier,
    page_count,
    warnings,
):
    source_reference_count = 0

    def inspect(value, location):
        nonlocal source_reference_count

        if isinstance(value, dict):
            if "page_number" in value and "confidence" in value:
                source_reference_count += 1
                page_number = value.get("page_number")

                if page_number is not None:
                    if page_number < 1 or page_number > page_count:
                        add_issue(
                            warnings,
                            "INVALID_SOURCE_PAGE",
                            (
                                f"Source page {page_number} is outside "
                                f"the document range 1 to {page_count}."
                            ),
                            location,
                        )

            for key, child_value in value.items():
                inspect(
                    child_value,
                    f"{location}.{key}",
                )

        elif isinstance(value, list):
            for index, child_value in enumerate(value):
                inspect(
                    child_value,
                    f"{location}[{index}]",
                )

    inspect(
        dossier.model_dump(mode="json"),
        "dossier",
    )

    return source_reference_count


def validate_restricted_information(
    dossier_data,
    warnings,
):
    allowed_sensitive_path = "sensitive_information"

    def inspect(value, location):
        if isinstance(value, dict):
            for key, child_value in value.items():
                inspect(
                    child_value,
                    f"{location}.{key}",
                )

        elif isinstance(value, list):
            for index, child_value in enumerate(value):
                inspect(
                    child_value,
                    f"{location}[{index}]",
                )

        elif isinstance(value, str):
            if allowed_sensitive_path in location:
                return

            for pattern_name, pattern in RESTRICTED_PATTERNS.items():
                if pattern.search(value):
                    add_issue(
                        warnings,
                        "POSSIBLE_RESTRICTED_PII",
                        (
                            f"Possible {pattern_name} found outside "
                            "sensitive_information."
                        ),
                        location,
                    )

    inspect(dossier_data, "dossier")


def validate_dossier(run_directory):
    run_path = Path(run_directory).expanduser().resolve()
    run_manager = RunManager(run_path)

    log_file = (
        run_manager.get_directory("logs")
        / "pipeline.log"
    )

    setup_logging(
        log_level="INFO",
        log_file=log_file,
    )

    extraction_directory = run_manager.get_directory(
        "extraction"
    )
    validation_directory = run_manager.get_directory(
        "validation"
    )

    extracted_path = (
        extraction_directory
        / "dossier_extracted.json"
    )

    if not extracted_path.exists():
        raise FileNotFoundError(
            f"Extracted dossier not found: {extracted_path}"
        )

    run_manager.start_step(STEP_NAME)

    errors = []
    warnings = []

    try:
        extracted_data = load_json(extracted_path)

        try:
            dossier = Dossier.model_validate(
                extracted_data
            )
        except ValidationError as error:
            for item in error.errors():
                add_issue(
                    errors,
                    "SCHEMA_VALIDATION_ERROR",
                    item.get("msg", "Schema validation error"),
                    ".".join(
                        str(part)
                        for part in item.get("loc", [])
                    ),
                )

            dossier = None

        if dossier is not None:
            candidate = dossier.candidate

            if not candidate.full_name.strip():
                add_issue(
                    errors,
                    "MISSING_CANDIDATE_NAME",
                    "Candidate name is required.",
                    "candidate.full_name",
                )

            if not candidate.current_or_last_title:
                add_issue(
                    warnings,
                    "MISSING_CURRENT_TITLE",
                    (
                        "Current or most recent candidate title "
                        "was not extracted."
                    ),
                    "candidate.current_or_last_title",
                )

            if not candidate.current_or_last_company:
                add_issue(
                    warnings,
                    "MISSING_CURRENT_COMPANY",
                    (
                        "Current or most recent candidate company "
                        "was not extracted."
                    ),
                    "candidate.current_or_last_company",
                )

            if not dossier.career_history:
                add_issue(
                    warnings,
                    "NO_CAREER_HISTORY",
                    "No career-history entries were extracted.",
                    "career_history",
                )

            if not dossier.career_highlights:
                add_issue(
                    warnings,
                    "NO_CAREER_HIGHLIGHTS",
                    "No career highlights were extracted.",
                    "career_highlights",
                )

            page_count = (
                dossier.metadata.page_count
                or extracted_data.get(
                    "metadata",
                    {},
                ).get("page_count")
                or 1
            )

            reference_count = validate_source_references(
                dossier=dossier,
                page_count=page_count,
                warnings=warnings,
            )

            if reference_count == 0:
                add_issue(
                    warnings,
                    "NO_SOURCE_REFERENCES",
                    (
                        "No source references were extracted. "
                        "Factual traceability will be limited."
                    ),
                    "dossier",
                )

            if dossier.compensation is not None:
                if dossier.compensation.display_allowed:
                    add_issue(
                        warnings,
                        "COMPENSATION_DISPLAY_ENABLED",
                        (
                            "Compensation is marked as displayable. "
                            "Confirm this is intentional."
                        ),
                        "compensation.display_allowed",
                    )

            for index, item in enumerate(
                dossier.sensitive_information
            ):
                if item.allowed_in_video:
                    add_issue(
                        errors,
                        "SENSITIVE_INFORMATION_VIDEO_ENABLED",
                        (
                            "Sensitive information cannot be "
                            "automatically enabled for video."
                        ),
                        (
                            "sensitive_information"
                            f"[{index}].allowed_in_video"
                        ),
                    )

                if item.category in {
                    SensitivityLevel.RESTRICTED_PII,
                    SensitivityLevel.SENSITIVE_PERSONAL,
                }:
                    item.allowed_in_video = False

            dossier_data = dossier.model_dump(
                mode="json"
            )

            validate_restricted_information(
                dossier_data=dossier_data,
                warnings=warnings,
            )

            validated_path = (
                validation_directory
                / "dossier_validated.json"
            )

            save_json(
                dossier_data,
                validated_path,
            )
        else:
            validated_path = None
            reference_count = 0

        status = (
            "failed"
            if errors
            else "passed_with_warnings"
            if warnings
            else "passed"
        )

        validation_report = {
            "status": status,
            "error_count": len(errors),
            "warning_count": len(warnings),
            "source_reference_count": reference_count,
            "errors": errors,
            "warnings": warnings,
            "validated_output": (
                str(validated_path)
                if validated_path
                else None
            ),
        }

        save_json(
            validation_report,
            validation_directory
            / "validation_report.json",
        )

        save_json(
            warnings,
            validation_directory
            / "warnings.json",
        )

        if errors:
            raise ValueError(
                f"Dossier validation failed with "
                f"{len(errors)} error(s)."
            )

        run_manager.complete_step(
            STEP_NAME,
            outputs={
                "validated_dossier": str(
                    validated_path
                ),
                "validation_report": str(
                    validation_directory
                    / "validation_report.json"
                ),
                "warning_count": len(warnings),
            },
        )

        return validation_report

    except Exception as error:
        run_manager.fail_step(
            STEP_NAME,
            f"{type(error).__name__}: {error}",
        )
        raise


def main():
    parser = build_argument_parser()
    arguments = parser.parse_args()

    try:
        report = validate_dossier(
            arguments.run_dir
        )

        print()
        print("STEP 03 COMPLETED")
        print(
            f"Validation status: {report['status']}"
        )
        print(
            f"Warnings: {report['warning_count']}"
        )
        print()

        return 0

    except Exception as error:
        print()
        print("STEP 03 FAILED")
        print(f"{type(error).__name__}: {error}")
        print()

        return 1


if __name__ == "__main__":
    sys.exit(main())
