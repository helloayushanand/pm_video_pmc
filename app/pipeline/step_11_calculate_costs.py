"""Pipeline Step 11: Calculate estimated cost per video."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.config import settings
from app.services.cost_service import CostService
from app.utils.logging import setup_logging
from app.utils.run_manager import RunManager


STEP_NAME = "calculate_costs"


def build_argument_parser():
    """Create the command-line argument parser."""

    parser = argparse.ArgumentParser(
        description=(
            "Calculate estimated API and production "
            "cost for one candidate video."
        )
    )

    parser.add_argument(
        "--run-dir",
        required=True,
        help="Existing pipeline run directory.",
    )

    return parser


def calculate_costs(run_directory):
    """Generate cost outputs for one run."""

    run_manager = RunManager(
        Path(run_directory).expanduser().resolve()
    )

    setup_logging(
        settings.log_level,
        run_manager.get_directory("logs")
        / "pipeline.log",
    )

    output_directory = (
        run_manager.get_directory("costs")
    )

    run_manager.start_step(
        STEP_NAME
    )

    try:
        service = CostService()

        summary = service.calculate_run_costs(
            run_directory=(
                run_manager.run_directory
            ),
            output_directory=(
                output_directory
            ),
        )

        run_manager.complete_step(
            STEP_NAME,
            outputs={
                "cost_summary": str(
                    output_directory
                    / "cost_summary.json"
                ),
                "cost_summary_markdown": str(
                    output_directory
                    / "cost_summary.md"
                ),
                "api_calls": str(
                    output_directory
                    / "api_calls.jsonl"
                ),
                "direct_api_cost_usd": (
                    summary[
                        "direct_api_cost_usd"
                    ]
                ),
                "total_technical_cost_usd": (
                    summary[
                        "total_technical_cost_usd"
                    ]
                ),
                "suggested_price_usd": (
                    summary[
                        "suggested_cost_based_price_usd"
                    ]
                ),
            },
        )

        return summary

    except Exception as error:
        run_manager.fail_step(
            STEP_NAME,
            f"{type(error).__name__}: {error}",
        )

        raise


def main():
    """Run Step 11 from the command line."""

    arguments = (
        build_argument_parser()
        .parse_args()
    )

    try:
        summary = calculate_costs(
            arguments.run_dir
        )

        print()
        print("=" * 72)
        print("STEP 11 COMPLETED")
        print("=" * 72)
        print(
            "Direct API cost:       "
            f"${summary['direct_api_cost_usd']:.6f}"
        )
        print(
            "Technical cost:        "
            f"${summary['total_technical_cost_usd']:.6f}"
        )
        print(
            "Fully loaded cost:     "
            f"${summary['fully_loaded_cost_usd']:.6f}"
        )
        print(
            "Suggested price:       "
            f"${summary['suggested_cost_based_price_usd']:.6f}"
        )
        print("=" * 72)
        print()

        return 0

    except Exception as error:
        print()
        print("STEP 11 FAILED")
        print(
            f"{type(error).__name__}: {error}"
        )
        print()

        return 1


if __name__ == "__main__":
    sys.exit(main())