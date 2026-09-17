"""Pipeline Step 10: Run deterministic video quality checks."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from app.config import settings
from app.utils.json_utils import load_json, save_json
from app.utils.logging import setup_logging
from app.utils.run_manager import RunManager


STEP_NAME = "run_quality_checks"


def build_argument_parser():
    parser = argparse.ArgumentParser(
        description="Run final deterministic quality checks."
    )

    parser.add_argument(
        "--run-dir",
        required=True,
    )

    return parser


def probe_video(video_path):
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        (
            "format=duration:"
            "stream=index,codec_type,codec_name,width,height"
        ),
        "-of",
        "json",
        str(video_path),
    ]

    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )

    if completed.returncode != 0:
        raise RuntimeError(
            "ffprobe failed: "
            f"{completed.stderr.strip()}"
        )

    return json.loads(completed.stdout)


def run_quality_checks(run_directory):
    run_manager = RunManager(
        Path(run_directory).resolve()
    )

    setup_logging(
        settings.log_level,
        run_manager.get_directory("logs")
        / "pipeline.log",
    )

    video_path = (
        run_manager.get_directory("video")
        / "candidate_snapshot.mp4"
    )

    render_spec_path = (
        run_manager.get_directory("render_spec")
        / "render_spec.json"
    )

    quality_directory = run_manager.get_directory(
        "quality"
    )

    run_manager.start_step(STEP_NAME)

    errors = []
    warnings = []

    try:
        if not video_path.exists():
            errors.append(
                {
                    "code": "VIDEO_NOT_FOUND",
                    "message": str(video_path),
                }
            )

        elif video_path.stat().st_size == 0:
            errors.append(
                {
                    "code": "VIDEO_EMPTY",
                    "message": "Rendered MP4 is empty.",
                }
            )

        if not render_spec_path.exists():
            errors.append(
                {
                    "code": "RENDER_SPEC_NOT_FOUND",
                    "message": str(render_spec_path),
                }
            )

        probe = None

        if not errors:
            try:
                probe = probe_video(video_path)
            except FileNotFoundError:
                warnings.append(
                    {
                        "code": "FFPROBE_NOT_INSTALLED",
                        "message": (
                            "FFprobe is not installed. "
                            "Media-stream checks were skipped."
                        ),
                    }
                )
            except Exception as error:
                errors.append(
                    {
                        "code": "VIDEO_PROBE_FAILED",
                        "message": str(error),
                    }
                )

        if probe is not None:
            streams = probe.get("streams", [])

            video_streams = [
                stream
                for stream in streams
                if stream.get("codec_type") == "video"
            ]

            audio_streams = [
                stream
                for stream in streams
                if stream.get("codec_type") == "audio"
            ]

            if not video_streams:
                errors.append(
                    {
                        "code": "VIDEO_STREAM_MISSING",
                        "message": "No video stream found.",
                    }
                )

            if not audio_streams:
                errors.append(
                    {
                        "code": "AUDIO_STREAM_MISSING",
                        "message": "No audio stream found.",
                    }
                )

            if video_streams:
                stream = video_streams[0]

                if stream.get("width") != settings.video_width:
                    errors.append(
                        {
                            "code": "INVALID_VIDEO_WIDTH",
                            "message": (
                                f"Expected {settings.video_width}, "
                                f"received {stream.get('width')}."
                            ),
                        }
                    )

                if stream.get("height") != settings.video_height:
                    errors.append(
                        {
                            "code": "INVALID_VIDEO_HEIGHT",
                            "message": (
                                f"Expected {settings.video_height}, "
                                f"received {stream.get('height')}."
                            ),
                        }
                    )

        status = (
            "failed"
            if errors
            else "passed_with_warnings"
            if warnings
            else "passed"
        )

        report = {
            "status": status,
            "video_path": str(video_path),
            "file_size_bytes": (
                video_path.stat().st_size
                if video_path.exists()
                else 0
            ),
            "errors": errors,
            "warnings": warnings,
            "probe": probe,
        }

        report_path = (
            quality_directory
            / "quality_report.json"
        )

        save_json(report, report_path)

        if errors:
            raise ValueError(
                f"Quality checks failed with "
                f"{len(errors)} error(s)."
            )

        approval_path = (
            quality_directory
            / "approved_for_review.txt"
        )

        approval_path.write_text(
            (
                "Automated checks completed.\n"
                f"Status: {status}\n"
                "Human review is still required.\n"
            ),
            encoding="utf-8",
        )

        run_manager.complete_step(
            STEP_NAME,
            outputs={
                "quality_report": str(report_path),
                "status": status,
                "warning_count": len(warnings),
            },
        )

        return report

    except Exception as error:
        run_manager.fail_step(
            STEP_NAME,
            f"{type(error).__name__}: {error}",
        )
        raise


def main():
    arguments = build_argument_parser().parse_args()

    try:
        report = run_quality_checks(
            arguments.run_dir
        )

        print()
        print("STEP 10 COMPLETED")
        print(f"Status: {report['status']}")
        print()

        return 0

    except Exception as error:
        print()
        print("STEP 10 FAILED")
        print(f"{type(error).__name__}: {error}")
        print()

        return 1


if __name__ == "__main__":
    sys.exit(main())
