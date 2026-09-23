"""Artifact planning, extraction, and manifest service."""

from __future__ import annotations

import mimetypes
from pathlib import Path

import pymupdf

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
    """Prepare artifact plans and local artifact candidates."""

    def prepare_artifacts(self, run_directory, output_directory):
        """Prepare artifacts from a Phase 2 creative plan."""

        run_path = Path(run_directory).expanduser().resolve()
        output_path = Path(output_directory).expanduser().resolve()

        creative_plan_path = (
            run_path / "05b_creative_plan" / "creative_plan.json"
        )

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

        directories = [
            extracted_directory,
            specification_directory,
            generated_directory,
            approved_directory,
        ]

        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)

        plan = self._build_plan(
            candidate_name=candidate_name,
            creative_direction=creative_direction,
            scene_briefs=draft.get("scene_briefs", []),
            global_notes=draft.get("global_artifact_notes", []),
        )

        artifact_plan_path = output_path / "artifact_plan.json"
        save_json(plan.model_dump(mode="json"), artifact_plan_path)

        extracted_candidates = self._extract_pdf_images(
            run_path=run_path,
            output_directory=extracted_directory,
        )

        extracted_candidates_path = (
            output_path / "extracted_image_candidates.json"
        )
        save_json(extracted_candidates, extracted_candidates_path)

        records = []

        for artifact in plan.artifacts:
            record = self._prepare_one_artifact(
                artifact=artifact,
                extracted_candidates=extracted_candidates,
                specification_directory=specification_directory,
            )
            records.append(record)

        manifest = ArtifactManifest(
            candidate_name=candidate_name,
            artifacts=records,
        )
        validation = self._validate_manifest(manifest)

        manifest_path = output_path / "artifact_manifest.json"
        validation_path = output_path / "artifact_validation.json"
        summary_path = output_path / "artifact_summary.md"

        save_json(manifest.model_dump(mode="json"), manifest_path)
        save_json(validation.model_dump(mode="json"), validation_path)

        summary_path.write_text(
            self._build_markdown_summary(
                plan=plan,
                manifest=manifest,
                validation=validation,
            ),
            encoding="utf-8",
        )

        logger.info(
            "Artifact preparation completed. "
            "Artifacts: %s, approved: %s, pending review: %s, failed: %s.",
            len(manifest.artifacts),
            manifest.approved_artifact_count,
            manifest.pending_review_count,
            manifest.failed_artifact_count,
        )

        return {
            "plan": plan,
            "manifest": manifest,
            "validation": validation,
        }

    def _build_plan(
        self,
        candidate_name,
        creative_direction,
        scene_briefs,
        global_notes,
    ):
        """Build an executable artifact plan."""

        artifacts = []

        for scene in scene_briefs:
            scene_id = scene.get("scene_id", "unknown_scene")
            requirements = scene.get("artifact_requirements", [])

            for requirement in requirements:
                artifact_type = self._normalise_artifact_type(
                    requirement.get("artifact_type", "other")
                )
                factual_status = requirement.get(
                    "factual_status",
                    FactualStatus.DECORATIVE.value,
                )
                artifact_id = requirement.get("artifact_id")

                if not artifact_id:
                    raise ArtifactServiceError(
                        "An artifact requirement is missing artifact_id "
                        f"in scene {scene_id}."
                    )

                source_strategy = requirement.get("source_strategy")
                if not source_strategy:
                    raise ArtifactServiceError(
                        f"Artifact requirement {artifact_id} is missing "
                        "source_strategy."
                    )

                purpose = requirement.get("purpose")
                if not purpose:
                    raise ArtifactServiceError(
                        f"Artifact requirement {artifact_id} is missing purpose."
                    )

                visual_brief = requirement.get("visual_brief")
                if not visual_brief:
                    raise ArtifactServiceError(
                        f"Artifact requirement {artifact_id} is missing "
                        "visual_brief."
                    )

                fallback_strategy = requirement.get("fallback_strategy")
                if not fallback_strategy:
                    fallback_strategy = (
                        "Use an approved typography-only or "
                        "Remotion-native fallback."
                    )

                requires_human_approval = (
                    artifact_type
                    in {
                        ArtifactType.PORTRAIT,
                        ArtifactType.LOGO,
                    }
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
                        source_reference_ids=requirement.get(
                            "source_reference_ids", []
                        ),
                        visual_brief=visual_brief,
                        fallback_strategy=fallback_strategy,
                        preferred_width=requirement.get("preferred_width"),
                        preferred_height=requirement.get("preferred_height"),
                        transparent_background=requirement.get(
                            "transparent_background", False
                        ),
                        output_format=requirement.get("output_format", "png"),
                        generation_constraints=requirement.get(
                            "generation_constraints", []
                        ),
                        requires_human_approval=requires_human_approval,
                    )
                )

        return ArtifactPlan(
            candidate_name=candidate_name,
            creative_concept=creative_direction.get(
                "creative_concept",
                "Candidate-specific visual system",
            ),
            artifacts=artifacts,
            global_constraints=[
                (
                    "Do not introduce factual information not present "
                    "in approved video content."
                ),
                "Do not generate or recreate candidate photographs.",
                "Do not generate company logos.",
                "Factual charts must use exact structured values.",
                (
                    "Generated imagery must remain decorative and "
                    "non-documentary."
                ),
                (
                    "Restricted PII and sensitive personal information "
                    "must not appear in artifacts."
                ),
                (
                    "Every factual artifact must retain a source-data "
                    "reference."
                ),
            ],
            generation_notes=global_notes,
        )

    def _extract_pdf_images(self, run_path, output_directory):
        """Extract embedded images as review candidates."""

        input_directory = run_path / "00_input"
        pdf_files = sorted(input_directory.glob("*.pdf"))

        if not pdf_files:
            logger.warning(
                "No source PDF found for embedded-image extraction."
            )
            return []

        pdf_path = pdf_files[0]
        candidates = []

        try:
            document = pymupdf.open(str(pdf_path))
        except Exception as error:
            raise ArtifactServiceError(
                "Unable to open the source PDF for image extraction. "
                f"Details: {error}"
            ) from error

        try:
            seen_xrefs = set()

            for page_index in range(document.page_count):
                page = document.load_page(page_index)
                images = page.get_images(full=True)

                for image_index, image in enumerate(images, start=1):
                    xref = image[0]

                    if xref in seen_xrefs:
                        continue

                    seen_xrefs.add(xref)

                    try:
                        extracted = document.extract_image(xref)
                    except Exception as error:
                        logger.warning(
                            "Unable to extract image xref %s "
                            "from page %s: %s",
                            xref,
                            page_index + 1,
                            error,
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

                    filename = (
                        f"page_{page_index + 1:03d}"
                        f"_image_{image_index:03d}"
                        f".{extension}"
                    )
                    destination = output_directory / filename
                    destination.write_bytes(image_bytes)

                    mime_type = (
                        mimetypes.guess_type(destination.name)[0]
                        or f"image/{extension}"
                    )
                    aspect_ratio = round(width / height, 4)
                    portrait_likelihood = (
                        self._calculate_portrait_likelihood(
                            width=width,
                            height=height,
                            file_size_bytes=destination.stat().st_size,
                        )
                    )

                    candidates.append(
                        {
                            "candidate_id": f"pdf_image_{xref}",
                            "page_number": page_index + 1,
                            "xref": xref,
                            "path": str(destination),
                            "filename": destination.name,
                            "width": width,
                            "height": height,
                            "aspect_ratio": aspect_ratio,
                            "file_size_bytes": destination.stat().st_size,
                            "mime_type": mime_type,
                            "portrait_likelihood": portrait_likelihood,
                            "requires_review": True,
                        }
                    )
        finally:
            document.close()

        candidates.sort(
            key=lambda item: (
                item["portrait_likelihood"],
                item["file_size_bytes"],
            ),
            reverse=True,
        )

        logger.info(
            "Extracted %s embedded PDF image candidates.",
            len(candidates),
        )

        return candidates

    @staticmethod
    def _calculate_portrait_likelihood(
        width,
        height,
        file_size_bytes,
    ):
        """Estimate whether an image may be a portrait.

        This is only a heuristic. It never approves an image.
        """

        if width <= 0 or height <= 0:
            return 0.0

        aspect_ratio = width / height
        score = 0.0

        if height > width:
            score += 0.35

        if 0.55 <= aspect_ratio <= 0.85:
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
    ):
        """Prepare one artifact according to its strategy."""

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
                source_description=(
                    "Rendered directly through approved "
                    "Remotion primitives."
                ),
            )

        if artifact.source_strategy in {
            ArtifactStrategy.DETERMINISTIC_CHART,
            ArtifactStrategy.DETERMINISTIC_DIAGRAM,
        }:
            return self._prepare_deterministic_specification(
                artifact=artifact,
                base_kwargs=base_kwargs,
                specification_directory=specification_directory,
            )

        if (
            artifact.source_strategy
            == ArtifactStrategy.EXTRACT_FROM_DOSSIER
        ):
            return self._prepare_extracted_artifact(
                artifact=artifact,
                base_kwargs=base_kwargs,
                extracted_candidates=extracted_candidates,
                specification_directory=specification_directory,
            )

        if artifact.source_strategy == ArtifactStrategy.IMAGE_GENERATION:
            return self._prepare_image_generation_specification(
                artifact=artifact,
                base_kwargs=base_kwargs,
                specification_directory=specification_directory,
            )

        if (
            artifact.source_strategy
            == ArtifactStrategy.APPROVED_LOCAL_ASSET
        ):
            return ArtifactRecord(
                **base_kwargs,
                status=ArtifactStatus.NEEDS_REVIEW,
                approved=False,
                source_description=(
                    "Approved local asset has not yet been attached."
                ),
                validation_warnings=[
                    "Attach and approve a local asset in Phase 3B."
                ],
            )

        return ArtifactRecord(
            **base_kwargs,
            status=ArtifactStatus.FAILED,
            approved=False,
            source_description="Unsupported artifact strategy.",
            validation_errors=[
                "No processor exists for "
                f"{artifact.source_strategy.value}."
            ],
        )

    def _prepare_deterministic_specification(
        self,
        artifact,
        base_kwargs,
        specification_directory,
    ):
        """Create a specification for a factual visual."""

        specification_path = (
            specification_directory / f"{artifact.artifact_id}.json"
        )
        validation_warnings = []

        if not artifact.data_reference:
            validation_warnings.append(
                "The deterministic visual does not yet contain "
                "a structured data reference."
            )

        if (
            artifact.factual_status == FactualStatus.FACTUAL
            and not artifact.source_reference_ids
        ):
            validation_warnings.append(
                "The factual visual does not yet contain "
                "source-reference IDs."
            )

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

        save_json(specification, specification_path)
        validation_warnings.append(
            "Visual output will be generated in Phase 3B."
        )

        return ArtifactRecord(
            **base_kwargs,
            status=ArtifactStatus.PLANNED,
            approved=False,
            local_path=str(specification_path),
            mime_type="application/json",
            file_size_bytes=specification_path.stat().st_size,
            source_description=(
                "Deterministic visual specification created."
            ),
            validation_warnings=validation_warnings,
        )

    def _prepare_extracted_artifact(
        self,
        artifact,
        base_kwargs,
        extracted_candidates,
        specification_directory,
    ):
        """Prepare extracted dossier-image candidates."""

        if not extracted_candidates:
            return ArtifactRecord(
                **base_kwargs,
                status=ArtifactStatus.FALLBACK,
                approved=False,
                source_description=(
                    "No embedded PDF images were available."
                ),
                validation_warnings=[
                    "Use the configured fallback strategy."
                ],
            )

        candidate_reference_path = (
            specification_directory
            / f"{artifact.artifact_id}_candidates.json"
        )

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
            candidate_reference_path,
        )

        return ArtifactRecord(
            **base_kwargs,
            status=ArtifactStatus.NEEDS_REVIEW,
            approved=False,
            local_path=str(candidate_reference_path),
            mime_type="application/json",
            file_size_bytes=candidate_reference_path.stat().st_size,
            source_description=(
                "Embedded dossier images were extracted "
                "as review candidates."
            ),
            validation_warnings=[
                (
                    "A human must choose and approve the correct "
                    "extracted image."
                )
            ],
        )

    def _prepare_image_generation_specification(
        self,
        artifact,
        base_kwargs,
        specification_directory,
    ):
        """Create a decorative-image generation specification."""

        validation_errors = []

        if artifact.factual_status == FactualStatus.FACTUAL:
            validation_errors.append(
                "A factual artifact cannot use the "
                "image_generation strategy."
            )

        generation_specification = {
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
                (
                    "Do not depict the candidate or any "
                    "identifiable real person."
                ),
                "Do not depict a fabricated documentary event.",
                "Do not create or recreate company logos.",
                (
                    "Do not add unsupported facts, metrics, "
                    "locations, or text."
                ),
            ],
            "status": "awaiting_phase_3b_image_generation",
        }

        specification_path = (
            specification_directory
            / f"{artifact.artifact_id}_image_prompt.json"
        )
        save_json(generation_specification, specification_path)

        if validation_errors:
            return ArtifactRecord(
                **base_kwargs,
                status=ArtifactStatus.FAILED,
                approved=False,
                local_path=str(specification_path),
                mime_type="application/json",
                file_size_bytes=specification_path.stat().st_size,
                source_description=(
                    "Unsafe image-generation specification rejected."
                ),
                validation_errors=validation_errors,
            )

        return ArtifactRecord(
            **base_kwargs,
            status=ArtifactStatus.PLANNED,
            approved=False,
            local_path=str(specification_path),
            mime_type="application/json",
            file_size_bytes=specification_path.stat().st_size,
            source_description=(
                "Decorative image-generation specification created."
            ),
            validation_warnings=[
                (
                    "The decorative image will be generated and "
                    "validated in Phase 3B."
                )
            ],
        )

    def _validate_manifest(self, manifest):
        """Validate required artifact availability."""

        missing_required = []
        errors = []
        warnings = []

        for artifact in manifest.artifacts:
            if (
                artifact.required
                and artifact.status
                in {
                    ArtifactStatus.FAILED,
                    ArtifactStatus.REJECTED,
                }
            ):
                missing_required.append(artifact.artifact_id)

            for error in artifact.validation_errors:
                errors.append(f"{artifact.artifact_id}: {error}")

            for warning in artifact.validation_warnings:
                warnings.append(f"{artifact.artifact_id}: {warning}")

        valid = not errors and not missing_required

        return ArtifactValidationReport(
            valid=valid,
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
        """Map free-form requirements to supported types."""

        normalised = (
            str(value)
            .strip()
            .lower()
            .replace("-", "_")
            .replace(" ", "_")
        )

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
        """Create a human-readable artifact summary."""

        lines = [
            "# Artifact Preparation Summary",
            "",
            f"Candidate: {plan.candidate_name}",
            "",
            f"Creative concept: {plan.creative_concept}",
            "",
            f"Artifact count: {len(plan.artifacts)}",
            "",
            (
                "Approved or ready: "
                f"{manifest.approved_artifact_count}"
            ),
            "",
            (
                "Pending review: "
                f"{manifest.pending_review_count}"
            ),
            "",
            f"Failed: {manifest.failed_artifact_count}",
            "",
            f"Manifest valid: {validation.valid}",
            "",
            "## Artifacts",
            "",
        ]

        if not manifest.artifacts:
            lines.extend(
                [
                    (
                        "No explicit artifacts were requested "
                        "by the creative plan."
                    ),
                    "",
                ]
            )

        for artifact in manifest.artifacts:
            lines.extend(
                [
                    f"### {artifact.artifact_id}",
                    "",
                    f"Scene: {artifact.scene_id}",
                    "",
                    f"Type: {artifact.artifact_type.value}",
                    "",
                    f"Strategy: {artifact.source_strategy.value}",
                    "",
                    f"Factual status: {artifact.factual_status.value}",
                    "",
                    f"Status: {artifact.status.value}",
                    "",
                    f"Approved: {artifact.approved}",
                    "",
                    f"Fallback: {artifact.fallback_strategy}",
                    "",
                ]
            )

            if artifact.local_path:
                lines.extend(
                    [
                        f"Local path: `{artifact.local_path}`",
                        "",
                    ]
                )

            if artifact.validation_warnings:
                lines.append("Warnings:")

                for warning in artifact.validation_warnings:
                    lines.append(f"- {warning}")

                lines.append("")

            if artifact.validation_errors:
                lines.append("Errors:")

                for error in artifact.validation_errors:
                    lines.append(f"- {error}")

                lines.append("")

        if validation.warnings:
            lines.extend(
                [
                    "## Validation Warnings",
                    "",
                ]
            )

            for warning in validation.warnings:
                lines.append(f"- {warning}")

        if validation.errors:
            lines.extend(
                [
                    "",
                    "## Validation Errors",
                    "",
                ]
            )

            for error in validation.errors:
                lines.append(f"- {error}")

        if validation.missing_required_artifacts:
            lines.extend(
                [
                    "",
                    "## Missing Required Artifacts",
                    "",
                ]
            )

            for artifact_id in validation.missing_required_artifacts:
                lines.append(f"- {artifact_id}")

        lines.extend(
            [
                "",
                "## Phase Status",
                "",
                (
                    "Phase 3A prepares artifact plans, embedded-image "
                    "candidates, factual visual specifications, "
                    "decorative image specifications, and the "
                    "artifact manifest."
                ),
                "",
                (
                    "Phase 3B will generate visual files, approve "
                    "selected images, validate dimensions and formats, "
                    "and copy approved artifacts into the Remotion "
                    "renderer."
                ),
            ]
        )

        return "\n".join(lines)
