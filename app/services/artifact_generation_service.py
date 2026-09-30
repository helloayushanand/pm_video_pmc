"""Generate, validate, approve, and publish Phase 3B artifacts."""

from __future__ import annotations

import base64
import mimetypes
import os
import shutil
from pathlib import Path

from openai import OpenAI
from PIL import Image

from app.schemas.artifact_plan import ArtifactStatus, ArtifactStrategy
from app.utils.json_utils import load_json, save_json
from app.utils.logging import get_logger

logger = get_logger(__name__)


class ArtifactGenerationError(Exception):
    """Raised when Phase 3B artifact processing fails."""


class ArtifactGenerationService:
    """Generate and publish renderer-ready artifacts."""

    def __init__(self, image_model=None, api_key=None):
        self.image_model = image_model or os.getenv(
            "OPENAI_IMAGE_MODEL", "gpt-image-2.5-flare"
        )
        self.image_quality = os.getenv("OPENAI_IMAGE_QUALITY", "high")
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.client = OpenAI(api_key=self.api_key) if self.api_key else None

    def generate_artifacts(self, run_directory, renderer_directory, generate_images=False):
        run_path = Path(run_directory).expanduser().resolve()
        renderer_path = Path(renderer_directory).expanduser().resolve()
        artifact_root = run_path / "05c_artifacts"
        plan_path = artifact_root / "artifact_plan.json"
        manifest_path = artifact_root / "artifact_manifest.json"

        if not plan_path.exists() or not manifest_path.exists():
            raise FileNotFoundError(
                "Phase 3A outputs are missing. Run prepare_artifacts first."
            )

        plan = load_json(plan_path)
        manifest = load_json(manifest_path)
        generated_dir = artifact_root / "generated"
        approved_dir = artifact_root / "approved"
        generated_dir.mkdir(parents=True, exist_ok=True)
        approved_dir.mkdir(parents=True, exist_ok=True)

        plan_by_id = {
            item["artifact_id"]: item
            for item in plan.get("artifacts", [])
        }

        events = []
        for record in manifest.get("artifacts", []):
            artifact_id = record["artifact_id"]
            item = plan_by_id.get(artifact_id, {})
            strategy = record.get("source_strategy")

            if strategy in {
                ArtifactStrategy.TYPOGRAPHY_ONLY.value,
                ArtifactStrategy.REMOTION_NATIVE.value,
            }:
                record["status"] = ArtifactStatus.READY.value
                record["approved"] = True
                record["validation_errors"] = []
                record["validation_warnings"] = []
                events.append(self._event(record, "ready_for_remotion"))
                continue

            if strategy in {
                ArtifactStrategy.DETERMINISTIC_CHART.value,
                ArtifactStrategy.DETERMINISTIC_DIAGRAM.value,
            }:
                self._prepare_native_visual(record, item, approved_dir)
                events.append(self._event(record, "native_spec_approved"))
                continue

            if strategy == ArtifactStrategy.IMAGE_GENERATION.value:
                if generate_images:
                    self._generate_decorative_image(record, item, generated_dir)
                    events.append(self._event(record, "image_generation_completed"))
                else:
                    record["status"] = ArtifactStatus.PLANNED.value
                    record["approved"] = False
                    self._append_warning(
                        record,
                        "Image generation was skipped. Rerun with --generate-images.",
                    )
                    events.append(self._event(record, "image_generation_skipped"))
                continue

            if strategy == ArtifactStrategy.EXTRACT_FROM_DOSSIER.value:
                self._resolve_manual_approval(record, approved_dir)
                events.append(self._event(record, "manual_approval_checked"))
                continue

            if strategy == ArtifactStrategy.APPROVED_LOCAL_ASSET.value:
                # P0 #1: ArtifactService can pre-approve the highest-ranked
                # extracted dossier image. Preserve that decision instead of
                # forcing a second manual approval gate in Phase 3B.
                if self._has_valid_preapproved_local_asset(record):
                    record["status"] = ArtifactStatus.APPROVED.value
                    record["approved"] = True
                    record["validation_errors"] = []
                    record["validation_warnings"] = []
                    events.append(self._event(record, "preapproved_local_asset"))
                else:
                    self._resolve_manual_approval(record, approved_dir)
                    events.append(self._event(record, "local_asset_checked"))
                continue

        publish_dir = (
            renderer_path
            / "public"
            / "generated"
            / "artifacts"
            / run_path.name
        )
        publish_dir.mkdir(parents=True, exist_ok=True)
        self._publish_approved_files(manifest, publish_dir, run_path.name)

        summary = self._recalculate_manifest(manifest)
        save_json(manifest, artifact_root / "artifact_manifest_final.json")
        save_json(events, artifact_root / "artifact_generation_events.json")
        save_json(summary, artifact_root / "artifact_generation_summary.json")
        (artifact_root / "artifact_generation_summary.md").write_text(
            self._summary_markdown(summary, manifest), encoding="utf-8"
        )
        logger.info(
            "Artifact generation completed. Artifacts: %s, approved: %s, pending review: %s, failed: %s.",
            summary["artifact_count"],
            summary["approved_count"],
            summary["pending_review_count"],
            summary["failed_count"],
        )
        return {"manifest": manifest, "summary": summary, "events": events}

    @staticmethod
    def _has_valid_preapproved_local_asset(record):
        if not record.get("approved") or not record.get("local_path"):
            return False
        path = Path(record["local_path"]).expanduser().resolve()
        return path.exists() and path.is_file() and path.stat().st_size > 0

    def _prepare_native_visual(self, record, item, approved_dir):
        artifact_id = record["artifact_id"]
        output_path = approved_dir / f"{artifact_id}.json"
        payload = {
            "artifact_id": artifact_id,
            "artifact_type": record.get("artifact_type"),
            "scene_id": record.get("scene_id"),
            "render_mode": "remotion_native",
            "purpose": item.get("purpose"),
            "visual_brief": item.get("visual_brief"),
            "data_reference": item.get("data_reference"),
            "source_reference_ids": item.get("source_reference_ids", []),
            "generation_constraints": item.get("generation_constraints", []),
            "do_not_render_instructions_as_text": True,
        }
        save_json(payload, output_path)
        record.update(
            {
                "status": ArtifactStatus.READY.value,
                "approved": True,
                "local_path": str(output_path),
                "mime_type": "application/json",
                "file_size_bytes": output_path.stat().st_size,
                "source_description": "Approved Remotion-native deterministic visual specification.",
                "validation_errors": [],
                "validation_warnings": [],
            }
        )

    def _generate_decorative_image(self, record, item, generated_dir):
        if self.client is None:
            raise ArtifactGenerationError(
                "OPENAI_API_KEY is required when --generate-images is used."
            )
        artifact_id = record["artifact_id"]
        if record.get("factual_status") == "factual":
            raise ArtifactGenerationError(
                f"Factual artifact cannot use image generation: {artifact_id}"
            )

        prompt = self._build_image_prompt(item)
        output_format = str(item.get("output_format", "png") or "png").lower()
        if output_format not in {"png", "jpeg", "webp"}:
            output_format = "png"
        transparent = bool(item.get("transparent_background", False))
        if transparent and output_format == "jpeg":
            output_format = "png"
        background = "transparent" if transparent else "opaque"
        size = self._resolve_image_size(item)

        try:
            response = self.client.images.generate(
                model=self.image_model,
                prompt=prompt,
                size=size,
                quality=self.image_quality,
                output_format=output_format,
                background=background,
                n=1,
            )
        except Exception as error:
            logger.exception("Image generation failed for artifact %s.", artifact_id)
            record.update(
                {
                    "status": ArtifactStatus.FALLBACK.value,
                    "approved": False,
                }
            )
            self._append_warning(
                record,
                f"Image generation failed: {type(error).__name__}: {error}",
            )
            return

        if not response.data or not response.data[0].b64_json:
            record.update(
                {
                    "status": ArtifactStatus.FALLBACK.value,
                    "approved": False,
                }
            )
            self._append_warning(record, "Image API returned no image data.")
            return

        image_bytes = base64.b64decode(response.data[0].b64_json)
        suffix = ".jpg" if output_format == "jpeg" else f".{output_format}"
        output_path = generated_dir / f"{artifact_id}{suffix}"
        output_path.write_bytes(image_bytes)

        try:
            width, height = self._inspect_image(output_path)
        except Exception as error:
            record.update(
                {
                    "status": ArtifactStatus.FAILED.value,
                    "approved": False,
                    "local_path": str(output_path),
                    "validation_errors": [
                        f"Generated image failed validation: {error}"
                    ],
                }
            )
            return

        mime_type = mimetypes.guess_type(output_path.name)[0] or (
            "image/jpeg" if output_format == "jpeg" else f"image/{output_format}"
        )
        record.update(
            {
                "status": ArtifactStatus.READY.value,
                "approved": True,
                "local_path": str(output_path),
                "mime_type": mime_type,
                "width": width,
                "height": height,
                "file_size_bytes": output_path.stat().st_size,
                "source_description": (
                    "Decorative image generated using "
                    f"{self.image_model} and automatically approved after deterministic image validation."
                ),
                "validation_errors": [],
                "validation_warnings": [],
            }
        )

    @staticmethod
    def _build_image_prompt(item):
        constraints = "; ".join(item.get("generation_constraints", []))
        purpose = item.get("purpose", "")
        visual_brief = item.get("visual_brief", "Abstract professional visual.")
        return (
            "Create one premium editorial visual asset for an executive-profile motion video. "
            f"Visual purpose: {purpose}. "
            f"Visual brief: {visual_brief}. "
            "The visual must be decorative, illustrative, non-documentary and presentation-ready. "
            "Use a sophisticated corporate editorial aesthetic with visual depth, strong composition, "
            "controlled colour variation and clear visual hierarchy. "
            "The visual should work naturally inside a 16:9 motion-graphics composition. "
            "Do not depict any identifiable real person. Do not create a candidate likeness. "
            "Do not create company logos or trademark-like marks. "
            "Do not fabricate documentary photography or events. "
            "Do not add unsupported facts, metrics, locations, dates or claims. "
            "Avoid text, labels, numbers, documents, UI elements and watermarks unless explicitly "
            "required by the approved visual brief. Do not leave large unfinished or empty areas. "
            "Additional constraints: " + (constraints or "none")
        )

    @staticmethod
    def _resolve_image_size(item):
        width = item.get("preferred_width")
        height = item.get("preferred_height")
        if width and height:
            try:
                resolved_width = max(16, int(round(float(width) / 16) * 16))
                resolved_height = max(16, int(round(float(height) / 16) * 16))
                ratio = resolved_width / resolved_height
                pixels = resolved_width * resolved_height
                if (
                    1 / 3 <= ratio <= 3
                    and resolved_width <= 3840
                    and resolved_height <= 3840
                    and 655_360 <= pixels <= 8_294_400
                ):
                    return f"{resolved_width}x{resolved_height}"
            except (TypeError, ValueError):
                pass
        return "1536x1024"

    def _resolve_manual_approval(self, record, approved_dir):
        approval_file = approved_dir / f"{record['artifact_id']}.approval.json"
        if not approval_file.exists():
            record["status"] = ArtifactStatus.NEEDS_REVIEW.value
            record["approved"] = False
            self._append_warning(record, f"Approval file missing: {approval_file.name}")
            return

        approval = load_json(approval_file)
        selected_path_value = approval.get("selected_path")
        if not approval.get("approved") or not selected_path_value:
            record["status"] = ArtifactStatus.REJECTED.value
            record["approved"] = False
            self._append_warning(record, "Artifact was not approved.")
            return

        selected_path = Path(selected_path_value).expanduser().resolve()
        if not selected_path.exists() or not selected_path.is_file():
            record["status"] = ArtifactStatus.FAILED.value
            record["approved"] = False
            record.setdefault("validation_errors", []).append(
                f"Approved file does not exist: {selected_path}"
            )
            return

        suffix = selected_path.suffix.lower() or ".bin"
        approved_copy = approved_dir / f"{record['artifact_id']}{suffix}"
        if selected_path != approved_copy:
            shutil.copy2(selected_path, approved_copy)

        mime_type = mimetypes.guess_type(approved_copy.name)[0]
        width = None
        height = None
        if mime_type and mime_type.startswith("image/"):
            width, height = self._inspect_image(approved_copy)

        record.update(
            {
                "status": ArtifactStatus.APPROVED.value,
                "approved": True,
                "local_path": str(approved_copy),
                "mime_type": mime_type or "application/octet-stream",
                "width": width,
                "height": height,
                "file_size_bytes": approved_copy.stat().st_size,
                "source_description": approval.get(
                    "source_description", "Manually approved source artifact."
                ),
                "validation_errors": [],
                "validation_warnings": [],
            }
        )

    @staticmethod
    def _publish_approved_files(manifest, publish_dir, run_id):
        for record in manifest.get("artifacts", []):
            if not record.get("approved"):
                continue
            local_path = record.get("local_path")
            if not local_path:
                continue
            source = Path(local_path)
            if not source.exists() or not source.is_file():
                continue
            if source.suffix.lower() == ".json":
                continue
            destination = publish_dir / source.name
            shutil.copy2(source, destination)
            record["renderer_path"] = (
                f"generated/artifacts/{run_id}/{destination.name}"
            )

    @staticmethod
    def _inspect_image(path):
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            return int(image.width), int(image.height)

    @staticmethod
    def _append_warning(record, warning):
        warnings = record.setdefault("validation_warnings", [])
        if warning not in warnings:
            warnings.append(warning)

    @staticmethod
    def _event(record, event):
        return {
            "artifact_id": record.get("artifact_id"),
            "event": event,
            "status": record.get("status"),
            "approved": record.get("approved"),
        }

    @staticmethod
    def _recalculate_manifest(manifest):
        artifacts = manifest.get("artifacts", [])
        approved = sum(1 for item in artifacts if item.get("approved"))
        pending = sum(
            1
            for item in artifacts
            if item.get("status") == ArtifactStatus.NEEDS_REVIEW.value
        )
        planned = sum(
            1
            for item in artifacts
            if item.get("status") == ArtifactStatus.PLANNED.value
        )
        failed = sum(
            1
            for item in artifacts
            if item.get("status") == ArtifactStatus.FAILED.value
        )
        rejected = sum(
            1
            for item in artifacts
            if item.get("status") == ArtifactStatus.REJECTED.value
        )
        fallback = sum(
            1
            for item in artifacts
            if item.get("status") == ArtifactStatus.FALLBACK.value
        )
        manifest["approved_artifact_count"] = approved
        manifest["pending_review_count"] = pending
        manifest["failed_artifact_count"] = failed
        return {
            "artifact_count": len(artifacts),
            "approved_count": approved,
            "pending_review_count": pending,
            "planned_count": planned,
            "fallback_count": fallback,
            "failed_count": failed,
            "rejected_count": rejected,
            "ready_for_component_generation": failed == 0,
        }

    @staticmethod
    def _summary_markdown(summary, manifest):
        lines = [
            "# Phase 3B Artifact Generation Summary",
            "",
            f"Artifacts: {summary['artifact_count']}",
            f"Approved or ready: {summary['approved_count']}",
            f"Pending review: {summary['pending_review_count']}",
            f"Planned: {summary['planned_count']}",
            f"Fallback: {summary['fallback_count']}",
            f"Failed: {summary['failed_count']}",
            f"Rejected: {summary['rejected_count']}",
            "",
            "## Artifacts",
            "",
        ]
        for item in manifest.get("artifacts", []):
            lines.extend(
                [
                    f"### {item['artifact_id']}",
                    f"- Strategy: {item.get('source_strategy')}",
                    f"- Status: {item.get('status')}",
                    f"- Approved: {item.get('approved')}",
                    f"- Local path: {item.get('local_path')}",
                    f"- Renderer path: {item.get('renderer_path')}",
                    "",
                ]
            )
        return "\n".join(lines)
