"""Artifact planning, extraction, generation, and manifest service."""
from __future__ import annotations

import base64
import mimetypes
import os
import shutil
from pathlib import Path

import pymupdf
from openai import OpenAI
from PIL import Image

from app.config import RENDERER_DIR, settings
from app.schemas.artifact_plan import (
    ArtifactManifest,
    ArtifactPlan,
    ArtifactPlanItem,
    ArtifactRecord,
    ArtifactStatus,
    ArtifactStrategy,
    ArtifactType,
    ArtifactValidationReport,
    FactualStatus,
)
from app.utils.json_utils import load_json, save_json
from app.utils.logging import get_logger

logger = get_logger(__name__)


class ArtifactServiceError(Exception):
    """Base exception for artifact-stage failures."""


class ArtifactService:
    """Prepare artifact plans, dossier candidates, specs, and decorative images."""

    def __init__(self, api_key=None, image_model=None):
        self.api_key = api_key or settings.openai_api_key
        self.client = OpenAI(api_key=self.api_key) if self.api_key else None
        self.image_model = image_model or os.getenv(
            "OPENAI_IMAGE_MODEL", "gpt-image-2.5-flare"
        )
        self._run_path = None

    def prepare_artifacts(self, run_directory, output_directory):
        run_path = Path(run_directory).expanduser().resolve()
        output_path = Path(output_directory).expanduser().resolve()
        self._run_path = run_path

        creative_plan_path = run_path / "05b_creative_plan" / "creative_plan.json"
        if not creative_plan_path.exists():
            raise FileNotFoundError(
                "Creative plan not found. Run Phase 2 first. "
                f"Expected file: {creative_plan_path}"
            )

        creative_plan = load_json(creative_plan_path)
        draft = creative_plan.get("draft", {})
        candidate_name = draft.get("candidate_name", "Unknown Candidate")
        creative_direction = draft.get("creative_direction", {})

        output_path.mkdir(parents=True, exist_ok=True)
        extracted_directory = output_path / "extracted"
        specification_directory = output_path / "specifications"
        generated_directory = output_path / "generated"
        approved_directory = output_path / "approved"
        for directory in (
            extracted_directory,
            specification_directory,
            generated_directory,
            approved_directory,
        ):
            directory.mkdir(parents=True, exist_ok=True)

        plan = self._build_plan(
            candidate_name=candidate_name,
            creative_direction=creative_direction,
            scene_briefs=draft.get("scene_briefs", []),
            global_notes=draft.get("global_artifact_notes", []),
        )
        save_json(plan.model_dump(mode="json"), output_path / "artifact_plan.json")

        extracted_candidates = self._extract_pdf_images(
            run_path=run_path,
            output_directory=extracted_directory,
        )
        save_json(
            extracted_candidates,
            output_path / "extracted_image_candidates.json",
        )

        records = []
        for artifact in plan.artifacts:
            records.append(
                self._prepare_one_artifact(
                    artifact=artifact,
                    extracted_candidates=extracted_candidates,
                    specification_directory=specification_directory,
                    generated_directory=generated_directory,
                )
            )

        manifest = ArtifactManifest(
            candidate_name=candidate_name,
            artifacts=records,
        )
        validation = self._validate_manifest(manifest)
        save_json(manifest.model_dump(mode="json"), output_path / "artifact_manifest.json")
        save_json(validation.model_dump(mode="json"), output_path / "artifact_validation.json")
        (output_path / "artifact_summary.md").write_text(
            self._build_markdown_summary(plan, manifest, validation),
            encoding="utf-8",
        )
        logger.info(
            "Artifact preparation completed. Artifacts: %s, approved: %s, "
            "pending review: %s, failed: %s.",
            len(manifest.artifacts),
            manifest.approved_artifact_count,
            manifest.pending_review_count,
            manifest.failed_artifact_count,
        )
        return {"plan": plan, "manifest": manifest, "validation": validation}

    def _build_plan(self, candidate_name, creative_direction, scene_briefs, global_notes):
        artifacts = []
        for scene in scene_briefs:
            scene_id = scene.get("scene_id", "unknown_scene")
            for requirement in scene.get("artifact_requirements", []):
                artifact_type = self._normalise_artifact_type(
                    requirement.get("artifact_type", "other")
                )
                factual_status = requirement.get(
                    "factual_status", FactualStatus.DECORATIVE.value
                )
                artifact_id = requirement.get("artifact_id")
                source_strategy = requirement.get("source_strategy")
                purpose = requirement.get("purpose")
                visual_brief = requirement.get("visual_brief")
                if not artifact_id:
                    raise ArtifactServiceError(
                        f"Artifact requirement in scene {scene_id} is missing artifact_id."
                    )
                if not source_strategy:
                    raise ArtifactServiceError(
                        f"Artifact requirement {artifact_id} is missing source_strategy."
                    )
                if not purpose:
                    raise ArtifactServiceError(
                        f"Artifact requirement {artifact_id} is missing purpose."
                    )
                if not visual_brief:
                    raise ArtifactServiceError(
                        f"Artifact requirement {artifact_id} is missing visual_brief."
                    )
                fallback_strategy = requirement.get("fallback_strategy") or (
                    "Use an approved typography-only or Remotion-native fallback."
                )
                requires_human_approval = (
                    artifact_type in {ArtifactType.PORTRAIT, ArtifactType.LOGO}
                    or factual_status == FactualStatus.MIXED.value
                )
                artifacts.append(
                    ArtifactPlanItem(
                        artifact_id=artifact_id,
                        scene_id=scene_id,
                        artifact_type=artifact_type,
                        source_strategy=source_strategy,
                        factual_status=factual_status,
                        purpose=purpose,
                        required=requirement.get("required", True),
                        data_reference=requirement.get("data_reference"),
                        source_reference_ids=requirement.get("source_reference_ids", []),
                        visual_brief=visual_brief,
                        fallback_strategy=fallback_strategy,
                        preferred_width=requirement.get("preferred_width"),
                        preferred_height=requirement.get("preferred_height"),
                        transparent_background=requirement.get("transparent_background", False),
                        output_format=requirement.get("output_format", "png"),
                        generation_constraints=requirement.get("generation_constraints", []),
                        requires_human_approval=requires_human_approval,
                    )
                )
        return ArtifactPlan(
            candidate_name=candidate_name,
            creative_concept=creative_direction.get(
                "creative_concept", "Candidate-specific visual system"
            ),
            artifacts=artifacts,
            global_constraints=[
                "Do not introduce factual information not present in approved video content.",
                "Do not generate or recreate candidate photographs.",
                "Do not generate company logos.",
                "Factual charts must use exact structured values.",
                "Generated imagery must remain decorative and non-documentary.",
                "Restricted PII and sensitive personal information must not appear in artifacts.",
                "Every factual artifact must retain a source-data reference.",
            ],
            generation_notes=global_notes,
        )

    def _extract_pdf_images(self, run_path, output_directory):
        pdf_files = sorted((run_path / "00_input").glob("*.pdf"))
        if not pdf_files:
            logger.warning("No source PDF found for embedded-image extraction.")
            return []
        candidates = []
        try:
            document = pymupdf.open(str(pdf_files[0]))
        except Exception as error:
            raise ArtifactServiceError(
                f"Unable to open the source PDF for image extraction: {error}"
            ) from error
        try:
            seen_xrefs = set()
            for page_index in range(document.page_count):
                page = document.load_page(page_index)
                for image_index, image in enumerate(page.get_images(full=True), start=1):
                    xref = image[0]
                    if xref in seen_xrefs:
                        continue
                    seen_xrefs.add(xref)
                    try:
                        extracted = document.extract_image(xref)
                    except Exception as error:
                        logger.warning(
                            "Unable to extract image xref %s from page %s: %s",
                            xref, page_index + 1, error,
                        )
                        continue
                    image_bytes = extracted.get("image")
                    if not image_bytes:
                        continue
                    extension = extracted.get("ext", "png")
                    width = int(extracted.get("width", 0))
                    height = int(extracted.get("height", 0))
                    if width < 120 or height < 120:
                        continue
                    filename = f"page_{page_index + 1:03d}_image_{image_index:03d}.{extension}"
                    destination = output_directory / filename
                    destination.write_bytes(image_bytes)
                    mime_type = mimetypes.guess_type(destination.name)[0] or f"image/{extension}"
                    candidates.append(
                        {
                            "candidate_id": f"pdf_image_{xref}",
                            "page_number": page_index + 1,
                            "xref": xref,
                            "path": str(destination),
                            "filename": destination.name,
                            "width": width,
                            "height": height,
                            "aspect_ratio": round(width / height, 4),
                            "file_size_bytes": destination.stat().st_size,
                            "mime_type": mime_type,
                            "portrait_likelihood": self._calculate_portrait_likelihood(
                                width, height, destination.stat().st_size
                            ),
                            "requires_review": True,
                        }
                    )
        finally:
            document.close()
        candidates.sort(
            key=lambda item: (item["portrait_likelihood"], item["file_size_bytes"]),
            reverse=True,
        )
        logger.info("Extracted %s embedded PDF image candidates.", len(candidates))
        return candidates

    @staticmethod
    def _calculate_portrait_likelihood(width, height, file_size_bytes):
        if width <= 0 or height <= 0:
            return 0.0
        ratio = width / height
        score = 0.0
        if height > width:
            score += 0.35
        if 0.55 <= ratio <= 0.85:
            score += 0.35
        if width >= 300 and height >= 400:
            score += 0.20
        if file_size_bytes >= 20_000:
            score += 0.10
        return round(min(score, 1.0), 3)

    def _prepare_one_artifact(
        self,
        artifact,
        extracted_candidates,
        specification_directory,
        generated_directory,
    ):
        base_kwargs = {
            "artifact_id": artifact.artifact_id,
            "scene_id": artifact.scene_id,
            "artifact_type": artifact.artifact_type,
            "source_strategy": artifact.source_strategy,
            "factual_status": artifact.factual_status,
            "required": artifact.required,
            "alt_text": artifact.purpose,
            "fallback_strategy": artifact.fallback_strategy,
        }
        if artifact.source_strategy in {
            ArtifactStrategy.TYPOGRAPHY_ONLY,
            ArtifactStrategy.REMOTION_NATIVE,
        }:
            return ArtifactRecord(
                **base_kwargs,
                status=ArtifactStatus.READY,
                approved=True,
                source_description="Rendered directly through approved Remotion primitives.",
            )
        if artifact.source_strategy in {
            ArtifactStrategy.DETERMINISTIC_CHART,
            ArtifactStrategy.DETERMINISTIC_DIAGRAM,
        }:
            return self._prepare_deterministic_specification(
                artifact, base_kwargs, specification_directory
            )
        if artifact.source_strategy == ArtifactStrategy.EXTRACT_FROM_DOSSIER:
            return self._prepare_extracted_artifact(
                artifact, base_kwargs, extracted_candidates, specification_directory
            )
        if artifact.source_strategy == ArtifactStrategy.IMAGE_GENERATION:
            return self._generate_decorative_image(
                artifact,
                base_kwargs,
                specification_directory,
                generated_directory,
            )
        if artifact.source_strategy == ArtifactStrategy.APPROVED_LOCAL_ASSET:
            return ArtifactRecord(
                **base_kwargs,
                status=ArtifactStatus.NEEDS_REVIEW,
                approved=False,
                source_description="Approved local asset has not yet been attached.",
                validation_warnings=["Attach and approve a local asset."],
            )
        return ArtifactRecord(
            **base_kwargs,
            status=ArtifactStatus.FAILED,
            approved=False,
            source_description="Unsupported artifact strategy.",
            validation_errors=[f"No processor exists for {artifact.source_strategy.value}."],
        )

    def _prepare_deterministic_specification(self, artifact, base_kwargs, specification_directory):
        path = specification_directory / f"{artifact.artifact_id}.json"
        warnings = []
        if not artifact.data_reference:
            warnings.append("The deterministic visual lacks a structured data reference.")
        if artifact.factual_status == FactualStatus.FACTUAL and not artifact.source_reference_ids:
            warnings.append("The factual visual lacks source-reference IDs.")
        specification = {
            "artifact_id": artifact.artifact_id,
            "scene_id": artifact.scene_id,
            "artifact_type": artifact.artifact_type.value,
            "source_strategy": artifact.source_strategy.value,
            "factual_status": artifact.factual_status.value,
            "purpose": artifact.purpose,
            "visual_brief": artifact.visual_brief,
            "data_reference": artifact.data_reference,
            "source_reference_ids": artifact.source_reference_ids,
            "constraints": artifact.generation_constraints,
            "preferred_width": artifact.preferred_width,
            "preferred_height": artifact.preferred_height,
            "transparent_background": artifact.transparent_background,
            "output_format": artifact.output_format,
            "status": "awaiting_phase_3b_renderer",
        }
        save_json(specification, path)
        warnings.append("Visual output will be generated in Phase 3B.")
        return ArtifactRecord(
            **base_kwargs,
            status=ArtifactStatus.PLANNED,
            approved=False,
            local_path=str(path),
            mime_type="application/json",
            file_size_bytes=path.stat().st_size,
            source_description="Deterministic visual specification created.",
            validation_warnings=warnings,
        )

    def _prepare_extracted_artifact(self, artifact, base_kwargs, extracted_candidates, specification_directory):
        if not extracted_candidates:
            return ArtifactRecord(
                **base_kwargs,
                status=ArtifactStatus.FALLBACK,
                approved=False,
                source_description="No embedded PDF images were available.",
                validation_warnings=["Use the configured fallback strategy."],
            )
        path = specification_directory / f"{artifact.artifact_id}_candidates.json"
        save_json(
            {
                "artifact_id": artifact.artifact_id,
                "scene_id": artifact.scene_id,
                "artifact_type": artifact.artifact_type.value,
                "purpose": artifact.purpose,
                "visual_brief": artifact.visual_brief,
                "candidates": extracted_candidates,
                "approval_required": True,
                "automatic_approval": False,
                "fallback_strategy": artifact.fallback_strategy,
            },
            path,
        )
        return ArtifactRecord(
            **base_kwargs,
            status=ArtifactStatus.NEEDS_REVIEW,
            approved=False,
            local_path=str(path),
            mime_type="application/json",
            file_size_bytes=path.stat().st_size,
            source_description="Embedded dossier images were extracted as review candidates.",
            validation_warnings=["A human must choose and approve the correct extracted image."],
        )

    def _prepare_image_generation_specification(self, artifact, base_kwargs, specification_directory):
        validation_errors = []
        if artifact.factual_status == FactualStatus.FACTUAL:
            validation_errors.append("A factual artifact cannot use image_generation.")
        spec = {
            "artifact_id": artifact.artifact_id,
            "scene_id": artifact.scene_id,
            "artifact_type": artifact.artifact_type.value,
            "purpose": artifact.purpose,
            "visual_brief": artifact.visual_brief,
            "factual_status": artifact.factual_status.value,
            "constraints": artifact.generation_constraints,
            "transparent_background": artifact.transparent_background,
            "preferred_width": artifact.preferred_width,
            "preferred_height": artifact.preferred_height,
            "output_format": artifact.output_format,
            "prohibited_content": [
                "Do not depict the candidate or any identifiable real person.",
                "Do not depict a fabricated documentary event.",
                "Do not create or recreate company logos.",
                "Do not add unsupported facts, metrics, locations, or text.",
            ],
            "status": "awaiting_image_generation",
        }
        path = specification_directory / f"{artifact.artifact_id}_image_prompt.json"
        save_json(spec, path)
        if validation_errors:
            return ArtifactRecord(
                **base_kwargs,
                status=ArtifactStatus.FAILED,
                approved=False,
                local_path=str(path),
                mime_type="application/json",
                file_size_bytes=path.stat().st_size,
                source_description="Unsafe image-generation specification rejected.",
                validation_errors=validation_errors,
            )
        return ArtifactRecord(
            **base_kwargs,
            status=ArtifactStatus.PLANNED,
            approved=False,
            local_path=str(path),
            mime_type="application/json",
            file_size_bytes=path.stat().st_size,
            source_description="Decorative image-generation specification created.",
            validation_warnings=["Decorative image generation is pending."],
        )

    def _generate_decorative_image(self, artifact, base_kwargs, specification_directory, generated_directory):
        spec_record = self._prepare_image_generation_specification(
            artifact, base_kwargs, specification_directory
        )
        if spec_record.status == ArtifactStatus.FAILED:
            return spec_record
        if self.client is None:
            logger.warning("OPENAI_API_KEY unavailable; leaving %s planned.", artifact.artifact_id)
            return spec_record

        output_format = str(artifact.output_format or "png").lower()
        if output_format not in {"png", "jpeg", "webp"}:
            output_format = "png"
        if artifact.transparent_background and output_format == "jpeg":
            output_format = "png"
        background = "transparent" if artifact.transparent_background else "opaque"
        size = self._image_size(artifact)
        prompt = self._image_prompt(artifact)

        try:
            result = self.client.images.generate(
                model=self.image_model,
                prompt=prompt,
                size=size,
                quality=os.getenv("OPENAI_IMAGE_QUALITY", "high"),
                output_format=output_format,
                background=background,
                n=1,
            )
            encoded = result.data[0].b64_json
            if not encoded:
                raise ArtifactServiceError("Image API returned no base64 image data.")
            image_bytes = base64.b64decode(encoded)
        except Exception as error:
            logger.warning("Image generation failed for %s: %s", artifact.artifact_id, error)
            return ArtifactRecord(
                **base_kwargs,
                status=ArtifactStatus.FALLBACK,
                approved=False,
                local_path=spec_record.local_path,
                mime_type="application/json",
                source_description="Decorative image generation failed.",
                validation_warnings=[
                    f"Image generation failed: {type(error).__name__}: {error}",
                    "Use the configured fallback strategy.",
                ],
            )

        extension = "jpg" if output_format == "jpeg" else output_format
        generated_path = generated_directory / f"{artifact.artifact_id}.{extension}"
        generated_path.write_bytes(image_bytes)
        try:
            with Image.open(generated_path) as image:
                width, height = image.size
                image.verify()
        except Exception as error:
            return ArtifactRecord(
                **base_kwargs,
                status=ArtifactStatus.FAILED,
                approved=False,
                local_path=str(generated_path),
                source_description="Generated image failed validation.",
                validation_errors=[str(error)],
            )

        renderer_root = (
            Path(RENDERER_DIR).expanduser().resolve()
            / "public" / "generated" / "artifacts" / self._run_path.name
        )
        renderer_root.mkdir(parents=True, exist_ok=True)
        renderer_destination = renderer_root / generated_path.name
        shutil.copy2(generated_path, renderer_destination)
        renderer_path = f"/generated/artifacts/{self._run_path.name}/{generated_path.name}"
        return ArtifactRecord(
            **base_kwargs,
            status=ArtifactStatus.READY,
            approved=True,
            local_path=str(generated_path),
            renderer_path=renderer_path,
            mime_type=mimetypes.guess_type(generated_path.name)[0] or f"image/{output_format}",
            file_size_bytes=generated_path.stat().st_size,
            width=width,
            height=height,
            source_description=(
                "Decorative image generated with the OpenAI Image API and copied into the Remotion renderer."
            ),
        )

    def _image_prompt(self, artifact):
        constraints = "\n".join(f"- {value}" for value in artifact.generation_constraints)
        background = "transparent background" if artifact.transparent_background else "opaque presentation-ready background"
        return (
            "Create one premium editorial visual asset for an executive-profile motion video.\n"
            f"Purpose: {artifact.purpose}\n"
            f"Visual brief: {artifact.visual_brief}\n"
            f"Background requirement: {background}.\n"
            "Style: polished, modern, restrained executive editorial illustration, strong composition, high visual clarity, no UI mockup, no slide frame.\n"
            "Do not depict a real or identifiable person. Do not create a candidate likeness. Do not create company logos. Do not depict a fabricated documentary event. Do not add unsupported facts, metrics, places, or labels. Avoid text unless the approved visual brief explicitly requires it.\n"
            f"Additional constraints:\n{constraints or '- none'}"
        )

    @staticmethod
    def _image_size(artifact):
        width = artifact.preferred_width
        height = artifact.preferred_height
        if width and height:
            width = max(16, int(round(float(width) / 16) * 16))
            height = max(16, int(round(float(height) / 16) * 16))
            ratio = width / height
            pixels = width * height
            if 1 / 3 <= ratio <= 3 and width <= 3840 and height <= 3840 and 655_360 <= pixels <= 8_294_400:
                return f"{width}x{height}"
        return "1536x1024"

    def _validate_manifest(self, manifest):
        missing_required = []
        errors = []
        warnings = []
        for artifact in manifest.artifacts:
            if artifact.required and artifact.status in {ArtifactStatus.FAILED, ArtifactStatus.REJECTED}:
                missing_required.append(artifact.artifact_id)
            errors.extend(f"{artifact.artifact_id}: {e}" for e in artifact.validation_errors)
            warnings.extend(f"{artifact.artifact_id}: {w}" for w in artifact.validation_warnings)
        return ArtifactValidationReport(
            valid=not errors and not missing_required,
            artifact_count=len(manifest.artifacts),
            approved_count=manifest.approved_artifact_count,
            pending_review_count=manifest.pending_review_count,
            failed_count=manifest.failed_artifact_count,
            missing_required_artifacts=missing_required,
            errors=errors,
            warnings=warnings,
        )

    @staticmethod
    def _normalise_artifact_type(value):
        normalised = str(value).strip().lower().replace("-", "_").replace(" ", "_")
        aliases = {
            "candidate_photo": ArtifactType.PORTRAIT,
            "candidate_portrait": ArtifactType.PORTRAIT,
            "executive_portrait": ArtifactType.PORTRAIT,
            "photo": ArtifactType.PORTRAIT,
            "company_logo": ArtifactType.LOGO,
            "metric_chart": ArtifactType.CHART,
            "bar_chart": ArtifactType.CHART,
            "donut_chart": ArtifactType.CHART,
            "comparison_chart": ArtifactType.CHART,
            "career_timeline": ArtifactType.TIMELINE,
            "professional_timeline": ArtifactType.TIMELINE,
            "organization_chart": ArtifactType.ORGANISATION_CHART,
            "organisation_chart": ArtifactType.ORGANISATION_CHART,
            "organisation_structure": ArtifactType.ORGANISATION_CHART,
            "organization_structure": ArtifactType.ORGANISATION_CHART,
            "reporting_structure": ArtifactType.ORGANISATION_CHART,
            "geographic_map": ArtifactType.MAP,
            "market_map": ArtifactType.MAP,
            "geographic_footprint": ArtifactType.MAP,
            "editorial_background": ArtifactType.BACKGROUND,
            "abstract_background": ArtifactType.BACKGROUND,
            "decorative_background": ArtifactType.BACKGROUND,
            "remotion_graphic": ArtifactType.REMOTION_GRAPHIC,
            "animated_graphic": ArtifactType.REMOTION_GRAPHIC,
        }
        if normalised in aliases:
            return aliases[normalised]
        try:
            return ArtifactType(normalised)
        except ValueError:
            return ArtifactType.OTHER

    @staticmethod
    def _build_markdown_summary(plan, manifest, validation):
        lines = [
            "# Artifact Preparation Summary", "",
            f"Candidate: {plan.candidate_name}", "",
            f"Creative concept: {plan.creative_concept}", "",
            f"Artifact count: {len(plan.artifacts)}", "",
            f"Approved or ready: {manifest.approved_artifact_count}", "",
            f"Pending review: {manifest.pending_review_count}", "",
            f"Failed: {manifest.failed_artifact_count}", "",
            f"Manifest valid: {validation.valid}", "", "## Artifacts", "",
        ]
        if not manifest.artifacts:
            lines.extend(["No explicit artifacts were requested by the creative plan.", ""])
        for artifact in manifest.artifacts:
            lines.extend([
                f"### {artifact.artifact_id}", "",
                f"Scene: {artifact.scene_id}", "",
                f"Type: {artifact.artifact_type.value}", "",
                f"Strategy: {artifact.source_strategy.value}", "",
                f"Factual status: {artifact.factual_status.value}", "",
                f"Status: {artifact.status.value}", "",
                f"Approved: {artifact.approved}", "",
                f"Fallback: {artifact.fallback_strategy}", "",
            ])
            if artifact.local_path:
                lines.extend([f"Local path: `{artifact.local_path}`", ""])
            if getattr(artifact, "renderer_path", None):
                lines.extend([f"Renderer path: `{artifact.renderer_path}`", ""])
            if artifact.validation_warnings:
                lines.append("Warnings:")
                lines.extend(f"- {w}" for w in artifact.validation_warnings)
                lines.append("")
            if artifact.validation_errors:
                lines.append("Errors:")
                lines.extend(f"- {e}" for e in artifact.validation_errors)
                lines.append("")
        if validation.warnings:
            lines.extend(["## Validation Warnings", ""])
            lines.extend(f"- {w}" for w in validation.warnings)
        if validation.errors:
            lines.extend(["", "## Validation Errors", ""])
            lines.extend(f"- {e}" for e in validation.errors)
        if validation.missing_required_artifacts:
            lines.extend(["", "## Missing Required Artifacts", ""])
            lines.extend(f"- {a}" for a in validation.missing_required_artifacts)
        return "\n".join(lines)
