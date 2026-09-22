"""Cost calculation and per-video pricing service."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import APP_DIR
from app.utils.json_utils import load_json, save_json


class CostServiceError(Exception):
    """Base exception for cost calculation errors."""


class CostService:
    """Calculate estimated API and production cost for one run."""

    def __init__(self, pricing_path=None):
        self.pricing_path = Path(
            pricing_path or APP_DIR / "pricing.json"
        ).resolve()

        if not self.pricing_path.exists():
            raise FileNotFoundError(
                f"Pricing configuration not found: "
                f"{self.pricing_path}"
            )

        self.pricing = load_json(
            self.pricing_path
        )

    def calculate_run_costs(
        self,
        run_directory,
        output_directory,
    ):
        """Build an itemized cost report for one pipeline run."""

        run_path = Path(
            run_directory
        ).expanduser().resolve()

        output_path = Path(
            output_directory
        ).expanduser().resolve()

        output_path.mkdir(
            parents=True,
            exist_ok=True,
        )

        run_state_path = run_path / "run.json"

        if not run_state_path.exists():
            raise FileNotFoundError(
                f"run.json not found: {run_state_path}"
            )

        run_state = load_json(
            run_state_path
        )

        warnings = []
        calls = []

        calls.extend(
            self._read_vlm_calls(
                run_path=run_path,
                warnings=warnings,
            )
        )

        tts_call = self._read_tts_call(
            run_path=run_path,
            warnings=warnings,
        )

        if tts_call is not None:
            calls.append(tts_call)

        transcription_call = (
            self._read_transcription_call(
                run_path=run_path,
                warnings=warnings,
            )
        )

        if transcription_call is not None:
            calls.append(transcription_call)

        for call in calls:
            call["estimated_cost_usd"] = (
                self._calculate_call_cost(
                    call=call,
                    warnings=warnings,
                )
            )

        api_cost = round(
            sum(
                call.get(
                    "estimated_cost_usd",
                    0,
                )
                for call in calls
            ),
            8,
        )

        video_duration_seconds = (
            self._get_video_duration(
                run_path
            )
        )

        local_costs = self.pricing.get(
            "local_costs",
            {},
        )

        render_rate = self._number_or_zero(
            local_costs.get(
                "render_cost_per_minute_usd"
            )
        )

        render_cost = round(
            (
                video_duration_seconds / 60
            ) * render_rate,
            8,
        )

        storage_cost = self._number_or_zero(
            local_costs.get(
                "storage_cost_per_video_usd"
            )
        )

        other_cost = self._number_or_zero(
            local_costs.get(
                "other_cost_per_video_usd"
            )
        )

        technical_cost = round(
            api_cost
            + render_cost
            + storage_cost
            + other_cost,
            8,
        )

        commercial = self.pricing.get(
            "commercial_pricing",
            {},
        )

        manual_review_cost = (
            self._number_or_zero(
                commercial.get(
                    "manual_review_cost_usd"
                )
            )
        )

        fully_loaded_cost = round(
            technical_cost
            + manual_review_cost,
            8,
        )

        target_margin = self._number_or_zero(
            commercial.get(
                "target_gross_margin_percentage"
            )
        )

        suggested_price = (
            self._calculate_margin_price(
                cost=fully_loaded_cost,
                margin_percentage=target_margin,
            )
        )

        cost_by_operation = {}

        for call in calls:
            operation = call["operation"]

            cost_by_operation[operation] = round(
                cost_by_operation.get(
                    operation,
                    0,
                )
                + call.get(
                    "estimated_cost_usd",
                    0,
                ),
                8,
            )

        summary = {
            "run_id": run_state.get(
                "run_id"
            ),
            "generated_at": (
                datetime.now()
                .astimezone()
                .isoformat(timespec="seconds")
            ),
            "currency": self.pricing.get(
                "currency",
                "USD",
            ),
            "pricing_effective_date": (
                self.pricing.get(
                    "effective_date"
                )
            ),
            "pricing_file": str(
                self.pricing_path
            ),
            "video_duration_seconds": (
                video_duration_seconds
            ),
            "video_duration_minutes": round(
                video_duration_seconds / 60,
                4,
            ),
            "api_call_count": len(calls),
            "calls": calls,
            "cost_by_operation": (
                cost_by_operation
            ),
            "direct_api_cost_usd": (
                api_cost
            ),
            "render_compute_cost_usd": (
                render_cost
            ),
            "storage_cost_usd": (
                storage_cost
            ),
            "other_technical_cost_usd": (
                other_cost
            ),
            "total_technical_cost_usd": (
                technical_cost
            ),
            "manual_review_cost_usd": (
                manual_review_cost
            ),
            "fully_loaded_cost_usd": (
                fully_loaded_cost
            ),
            "target_gross_margin_percentage": (
                target_margin
            ),
            "suggested_cost_based_price_usd": (
                suggested_price
            ),
            "cost_per_output_minute_usd": (
                round(
                    technical_cost
                    / (
                        video_duration_seconds / 60
                    ),
                    8,
                )
                if video_duration_seconds > 0
                else 0
            ),
            "warnings": warnings,
            "estimate_only": True,
        }

        save_json(
            summary,
            output_path / "cost_summary.json",
        )

        self._write_jsonl(
            calls=calls,
            output_path=(
                output_path
                / "api_calls.jsonl"
            ),
        )

        markdown = self._build_markdown(
            summary
        )

        (
            output_path
            / "cost_summary.md"
        ).write_text(
            markdown,
            encoding="utf-8",
        )

        return summary

    def _read_vlm_calls(
        self,
        run_path,
        warnings,
    ):
        """Read the three Responses API usage records."""

        metadata_files = [
            (
                "dossier_extraction",
                "extract_dossier",
                run_path
                / "02_extraction"
                / "extraction_metadata.json",
            ),
            (
                "video_content_selection",
                "select_video_content",
                run_path
                / "04_video_content"
                / "selection_metadata.json",
            ),
            (
                "storyboard_generation",
                "generate_storyboard",
                run_path
                / "05_storyboard"
                / "storyboard_metadata.json",
            ),
        ]

        calls = []

        for (
            operation,
            pipeline_step,
            metadata_path,
        ) in metadata_files:
            if not metadata_path.exists():
                warnings.append(
                    f"Missing metadata for "
                    f"{operation}: {metadata_path}"
                )
                continue

            metadata = load_json(
                metadata_path
            )

            usage = metadata.get(
                "usage",
                {},
            ) or {}

            input_tokens = self._int_or_zero(
                usage.get(
                    "input_tokens"
                )
            )

            output_tokens = self._int_or_zero(
                usage.get(
                    "output_tokens"
                )
            )

            cached_tokens = self._cached_tokens(
                usage
            )

            calls.append(
                {
                    "provider": "openai",
                    "operation": operation,
                    "pipeline_step": pipeline_step,
                    "model": metadata.get(
                        "model"
                    ),
                    "response_id": metadata.get(
                        "response_id"
                    ),
                    "billing_type": "tokens",
                    "input_tokens": input_tokens,
                    "cached_input_tokens": (
                        cached_tokens
                    ),
                    "output_tokens": (
                        output_tokens
                    ),
                    "total_tokens": (
                        self._int_or_zero(
                            usage.get(
                                "total_tokens"
                            )
                        )
                        or input_tokens
                        + output_tokens
                    ),
                    "metadata_file": str(
                        metadata_path
                    ),
                    "status": metadata.get(
                        "status",
                        "completed",
                    ),
                }
            )

        return calls

    def _read_tts_call(
        self,
        run_path,
        warnings,
    ):
        """Read OpenAI TTS usage from audio metadata."""

        metadata_path = (
            run_path
            / "06_audio"
            / "audio_metadata.json"
        )

        if not metadata_path.exists():
            warnings.append(
                f"Missing TTS metadata: "
                f"{metadata_path}"
            )
            return None

        metadata = load_json(
            metadata_path
        )

        result = metadata.get(
            "result",
            {},
        ) or {}

        return {
            "provider": "openai",
            "operation": (
                "voiceover_generation"
            ),
            "pipeline_step": (
                "generate_audio"
            ),
            "model": (
                metadata.get("model")
                or result.get("model")
            ),
            "voice": (
                metadata.get("voice")
                or result.get("voice")
            ),
            "billing_type": "characters",
            "character_count": (
                self._int_or_zero(
                    result.get(
                        "character_count"
                    )
                )
            ),
            "audio_duration_seconds": (
                self._float_or_zero(
                    result.get(
                        "duration_seconds"
                    )
                )
            ),
            "metadata_file": str(
                metadata_path
            ),
            "status": "completed",
        }

    def _read_transcription_call(
        self,
        run_path,
        warnings,
    ):
        """Read transcription usage from alignment output."""

        metadata_path = (
            run_path
            / "07_alignment"
            / "alignment_metadata.json"
        )

        raw_path = (
            run_path
            / "07_alignment"
            / "alignment_raw_response.json"
        )

        if not metadata_path.exists():
            warnings.append(
                f"Missing alignment metadata: "
                f"{metadata_path}"
            )
            return None

        metadata = load_json(
            metadata_path
        )

        raw = (
            load_json(raw_path)
            if raw_path.exists()
            else {}
        )

        duration = self._float_or_zero(
            raw.get("duration")
        )

        if duration <= 0:
            duration = self._get_video_duration(
                run_path
            )

        return {
            "provider": "openai",
            "operation": (
                "timestamp_extraction"
            ),
            "pipeline_step": (
                "align_audio"
            ),
            "model": (
                metadata.get("model")
                or raw.get("model")
                or "whisper-1"
            ),
            "billing_type": (
                "audio_minutes"
            ),
            "audio_duration_seconds": (
                duration
            ),
            "audio_duration_minutes": round(
                duration / 60,
                6,
            ),
            "word_count": (
                self._int_or_zero(
                    metadata.get(
                        "word_count"
                    )
                )
            ),
            "metadata_file": str(
                metadata_path
            ),
            "status": "completed",
        }

    def _calculate_call_cost(
        self,
        call,
        warnings,
    ):
        """Calculate one call's estimated cost."""

        model = call.get(
            "model"
        )

        model_pricing = (
            self.pricing
            .get("models", {})
            .get(model)
        )

        if model_pricing is None:
            warnings.append(
                f"No pricing configured for "
                f"model: {model}"
            )
            return 0

        billing_type = model_pricing.get(
            "billing_type"
        )

        if billing_type == "tokens":
            return self._token_cost(
                call=call,
                pricing=model_pricing,
                warnings=warnings,
            )

        if billing_type == "characters":
            return self._character_cost(
                call=call,
                pricing=model_pricing,
                warnings=warnings,
            )

        if billing_type == "audio_minutes":
            return self._audio_minute_cost(
                call=call,
                pricing=model_pricing,
                warnings=warnings,
            )

        warnings.append(
            f"Unsupported billing type "
            f"'{billing_type}' for {model}"
        )

        return 0

    def _token_cost(
        self,
        call,
        pricing,
        warnings,
    ):
        input_rate = pricing.get(
            "input_per_million_usd"
        )

        cached_rate = pricing.get(
            "cached_input_per_million_usd"
        )

        output_rate = pricing.get(
            "output_per_million_usd"
        )

        if (
            input_rate is None
            or output_rate is None
        ):
            warnings.append(
                f"Token pricing is incomplete for "
                f"{call.get('model')}"
            )
            return 0

        if cached_rate is None:
            cached_rate = input_rate

        input_tokens = self._int_or_zero(
            call.get("input_tokens")
        )

        cached_tokens = self._int_or_zero(
            call.get(
                "cached_input_tokens"
            )
        )

        output_tokens = self._int_or_zero(
            call.get("output_tokens")
        )

        uncached_tokens = max(
            0,
            input_tokens - cached_tokens,
        )

        cost = (
            (
                uncached_tokens
                * float(input_rate)
            )
            + (
                cached_tokens
                * float(cached_rate)
            )
            + (
                output_tokens
                * float(output_rate)
            )
        ) / 1_000_000

        return round(cost, 8)

    def _character_cost(
        self,
        call,
        pricing,
        warnings,
    ):
        rate = pricing.get(
            "per_million_characters_usd"
        )

        if rate is None:
            warnings.append(
                f"Character pricing is incomplete for "
                f"{call.get('model')}"
            )
            return 0

        characters = self._int_or_zero(
            call.get("character_count")
        )

        return round(
            (
                characters
                * float(rate)
            )
            / 1_000_000,
            8,
        )

    def _audio_minute_cost(
        self,
        call,
        pricing,
        warnings,
    ):
        rate = pricing.get(
            "per_minute_usd"
        )

        if rate is None:
            warnings.append(
                f"Audio pricing is incomplete for "
                f"{call.get('model')}"
            )
            return 0

        seconds = self._float_or_zero(
            call.get(
                "audio_duration_seconds"
            )
        )

        return round(
            (
                seconds / 60
            )
            * float(rate),
            8,
        )

    def _get_video_duration(
        self,
        run_path,
    ):
        metadata_path = (
            run_path
            / "06_audio"
            / "audio_metadata.json"
        )

        if not metadata_path.exists():
            return 0

        metadata = load_json(
            metadata_path
        )

        return self._float_or_zero(
            metadata.get(
                "result",
                {},
            ).get(
                "duration_seconds"
            )
        )

    @staticmethod
    def _cached_tokens(usage):
        details = (
            usage.get(
                "input_tokens_details"
            )
            or {}
        )

        return CostService._int_or_zero(
            details.get(
                "cached_tokens"
            )
        )

    @staticmethod
    def _calculate_margin_price(
        cost,
        margin_percentage,
    ):
        if cost <= 0:
            return 0

        margin_decimal = (
            margin_percentage / 100
        )

        if margin_decimal >= 1:
            return 0

        return round(
            cost / (1 - margin_decimal),
            8,
        )

    @staticmethod
    def _number_or_zero(value):
        if value is None:
            return 0

        return float(value)

    @staticmethod
    def _int_or_zero(value):
        if value is None:
            return 0

        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _float_or_zero(value):
        if value is None:
            return 0.0

        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _write_jsonl(
        calls,
        output_path,
    ):
        with Path(output_path).open(
            "w",
            encoding="utf-8",
        ) as file_handle:
            for call in calls:
                file_handle.write(
                    json.dumps(
                        call,
                        ensure_ascii=False,
                    )
                )
                file_handle.write("\n")

    @staticmethod
    def _build_markdown(summary):
        """Build a readable Markdown cost summary."""

        run_id = summary.get("run_id", "unknown")

        video_duration = summary.get(
            "video_duration_seconds",
            0,
        )

        cost_by_operation = summary.get(
            "cost_by_operation",
            {},
        )

        direct_api_cost = summary.get(
            "direct_api_cost_usd",
            0,
        )

        render_compute_cost = summary.get(
            "render_compute_cost_usd",
            0,
        )

        storage_cost = summary.get(
            "storage_cost_usd",
            0,
        )

        other_technical_cost = summary.get(
            "other_technical_cost_usd",
            0,
        )

        total_technical_cost = summary.get(
            "total_technical_cost_usd",
            0,
        )

        manual_review_cost = summary.get(
            "manual_review_cost_usd",
            0,
        )

        fully_loaded_cost = summary.get(
            "fully_loaded_cost_usd",
            0,
        )

        suggested_price = summary.get(
            "suggested_cost_based_price_usd",
            0,
        )

        cost_per_output_minute = summary.get(
            "cost_per_output_minute_usd",
            0,
        )

        warnings = summary.get(
            "warnings",
            [],
        )

        lines = [
            "# Candidate Video Cost Summary",
            "",
            "Run ID: `{}`".format(run_id),
            "",
            "Video duration: {} seconds".format(
                video_duration
            ),
            "",
            "## Cost by operation",
            "",
        ]

        for operation, cost in cost_by_operation.items():
            lines.append(
                "- {}: ${:.6f}".format(
                    operation,
                    cost,
                )
            )

        lines.extend(
            [
                "",
                "## Totals",
                "",
                "- Direct API cost: ${:.6f}".format(
                    direct_api_cost
                ),
                "- Render compute cost: ${:.6f}".format(
                    render_compute_cost
                ),
                "- Storage cost: ${:.6f}".format(
                    storage_cost
                ),
                "- Other technical cost: ${:.6f}".format(
                    other_technical_cost
                ),
                "- Total technical cost: ${:.6f}".format(
                    total_technical_cost
                ),
                "- Manual review cost: ${:.6f}".format(
                    manual_review_cost
                ),
                "- Fully loaded cost: ${:.6f}".format(
                    fully_loaded_cost
                ),
                "- Suggested cost-based price: ${:.6f}".format(
                    suggested_price
                ),
                "- Cost per output minute: ${:.6f}".format(
                    cost_per_output_minute
                ),
                "",
                "## Important",
                "",
                (
                    "These values are estimates based on "
                    "the configured pricing file."
                ),
            ]
        )

        if warnings:
            lines.extend(
                [
                    "",
                    "## Warnings",
                    "",
                ]
            )

            for warning in warnings:
                lines.append(
                    "- {}".format(warning)
                )

        return "\n".join(lines)