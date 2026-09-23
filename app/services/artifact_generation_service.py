"""Generate, approve, validate, and publish Phase 3B artifacts."""

from __future__ import annotations

import base64
import json
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
    """Generate approved visual artifacts and publish them to Remotion."""

    def __init__(self, image_model=None, api_key=None):
        self.image_model = image_model or os.getenv(
            "OPENAI_IMAGE_MODEL", "gpt-image-1"
        )
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.client = OpenAI(api_key=self.api_key) if self.api_key else None

    def generate_artifacts(
        self,
        run_directory,
        renderer_directory,
        generate_images=False,
    ):
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
            item["artifact_id"]: item for item in plan.get("artifacts", [])
        }

        events = []
        for record in manifest.get("artifacts", []):
            item = plan_by_id.get(record["artifact_id"], {})
            strategy = record.get("source_strategy")

            if strategy in {
                ArtifactStrategy.TYPOGRAPHY_ONLY.value,
                ArtifactStrategy.REMOTION_NATIVE.value,
            }:
                record["status"] = ArtifactStatus.READY.value
                record["approved"] = True
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
                    events.append(self._event(record, "image_generated"))
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
        return {"manifest": manifest, "summary": summary, "events": events}

    def _prepare_native_visual(self, record, item, approved_dir):
        """Approve a deterministic visual as a Remotion-native specification.

        Phase 4 generated components will render this exact specification.
        No image is rasterized here, which preserves animation and exact data.
        """
        artifact_id = record["artifact_id"]
        output_path = approved_dir / f"{artifact_id}.json"
        payload = {
            "artifact_id": artifact_id,
            "artifact_type": record.get("artifact_type"),
            "render_mode": "remotion_native",
            "purpose": item.get("purpose"),
            "visual_brief": item.get("visual_brief"),
            "data_reference": item.get("data_reference"),
            "source_reference_ids": item.get("source_reference_ids", []),
            "generation_constraints": item.get("generation_constraints", []),
        }
        save_json(payload, output_path)
        record.update(
            {
                "status": ArtifactStatus.READY.value,
                "approved": True,
                "local_path": str(output_path),
                "mime_type": "application/json",
                "file_size_bytes": output_path.stat().st_size,
                "source_description": (
                    "Approved Remotion-native deterministic visual specification."
                ),
                "validation_errors": [],
            }
        )

    def _generate_decorative_image(self, record, item, generated_dir):
        if self.client is None:
            raise ArtifactGenerationError(
                "OPENAI_API_KEY is required when --generate-images is used."
            )
        if record.get("factual_status") == "factual":
            raise ArtifactGenerationError(
                f"Factual artifact cannot use image generation: {record['artifact_id']}"
            )

        prompt = self._build_image_prompt(item)
        response = self.client.images.generate(
            model=self.image_model,
            prompt=prompt,
            size="1536x1024",
            quality="medium",
            n=1,
        )
        image_base64 = response.data[0].b64_json
        if not image_base64:
            raise ArtifactGenerationError(
                f"Image API returned no image for {record['artifact_id']}."
            )

        output_path = generated_dir / f"{record['artifact_id']}.png"
        output_path.write_bytes(base64.b64decode(image_base64))
        width, height = self._inspect_image(output_path)
        record.update(
            {
                "status": ArtifactStatus.NEEDS_REVIEW.value,
                "approved": False,
                "local_path": str(output_path),
                "mime_type": "image/png",
                "width": width,
                "height": height,
                "file_size_bytes": output_path.stat().st_size,
                "source_description": (
                    f"Decorative image generated using {self.image_model}."
                ),
                "validation_errors": [],
            }
        )
        self._append_warning(record, "Generated image requires approval before use.")

    @staticmethod
    def _build_image_prompt(item):
        constraints = "; ".join(item.get("generation_constraints", []))
        return (
            "Create a premium editorial visual for an executive profile video. "
            + item.get("visual_brief", "Abstract professional visual.")
            + " The image must be decorative and non-documentary. "
            "Do not depict any identifiable real person. Do not include logos, "
            "company names, text, numbers, signatures, documents, UI, or watermarks. "
            "Use a refined corporate editorial aesthetic, subtle depth, restrained "
            "warm neutrals with charcoal and muted gold, presentation-ready composition, "
            "no empty space. Additional constraints: "
            + constraints
        )

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
                    "source_description", "Manually approved artifact."
                ),
                "validation_errors": [],
                "validation_warnings": [],
            }
        )

    @staticmethod
    def _publish_approved_files(manifest, publish_dir, run_id):
        for record in manifest.get("artifacts", []):
            if not record.get("approved") or not record.get("local_path"):
                continue
            source = Path(record["local_path"])
            if not source.exists() or source.suffix.lower() == ".json":
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
        manifest["approved_artifact_count"] = approved
        manifest["pending_review_count"] = pending
        manifest["failed_artifact_count"] = failed
        return {
            "artifact_count": len(artifacts),
            "approved_count": approved,
            "pending_review_count": pending,
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
