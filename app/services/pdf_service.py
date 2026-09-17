"""PDF validation, text extraction, and page rendering service."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import fitz

from app.config import settings
from app.utils.files import (
    calculate_sha256,
    ensure_directory,
    get_relative_path,
)
from app.utils.json_utils import save_json
from app.utils.logging import get_logger


logger = get_logger(__name__)


SUPPORTED_PDF_EXTENSION = ".pdf"


class PDFServiceError(Exception):
    """Base exception for PDF-processing failures."""


class InvalidPDFError(PDFServiceError):
    """Raised when an input file is not a valid usable PDF."""


class PasswordProtectedPDFError(PDFServiceError):
    """Raised when a PDF requires a password."""


@dataclass
class PDFPageResult:
    """Artifacts and metadata generated for one PDF page."""

    page_number: int
    width_points: float
    height_points: float
    width_pixels: int
    height_pixels: int
    rotation: int
    native_text_available: bool
    native_text_length: int
    native_text_path: str
    image_path: str
    estimated_word_count: int


@dataclass
class PDFPreparationResult:
    """Complete result produced after preparing one PDF."""

    document_id: str
    original_filename: str
    source_path: str
    sha256: str
    file_size_bytes: int
    page_count: int
    pdf_metadata: dict[str, Any]
    render_dpi: int
    processed_at: str
    full_text_path: str
    native_text_json_path: str
    pages_directory: str
    pages: list[PDFPageResult]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible dictionary."""

        return asdict(self)


class PDFService:
    """Prepare a local PDF for downstream VLM extraction."""

    def __init__(self, render_dpi: int | None = None) -> None:
        self.render_dpi = render_dpi or settings.pdf_render_dpi

        if self.render_dpi <= 0:
            raise ValueError("render_dpi must be greater than zero.")

    def validate_pdf(self, pdf_path: str | Path) -> Path:
        """Validate that a file exists and is a readable PDF."""

        path = Path(pdf_path).resolve()

        if not path.exists():
            raise FileNotFoundError(f"PDF file not found: {path}")

        if not path.is_file():
            raise InvalidPDFError(
                f"Expected a file but received: {path}"
            )

        if path.suffix.lower() != SUPPORTED_PDF_EXTENSION:
            raise InvalidPDFError(
                f"Only PDF files are supported. Received: {path.suffix}"
            )

        if path.stat().st_size == 0:
            raise InvalidPDFError(f"PDF file is empty: {path}")

        try:
            document = fitz.open(path)
        except Exception as error:
            raise InvalidPDFError(
                f"Unable to open PDF: {path}"
            ) from error

        try:
            if document.needs_pass:
                raise PasswordProtectedPDFError(
                    "The PDF is password protected. "
                    "Provide an unlocked PDF for the prototype."
                )

            if document.page_count == 0:
                raise InvalidPDFError(
                    "The PDF does not contain any pages."
                )
        finally:
            document.close()

        return path

    def prepare_pdf(
        self,
        pdf_path: str | Path,
        output_directory: str | Path,
    ) -> PDFPreparationResult:
        """
        Extract native text, render page images, and save metadata.

        The output directory will contain:

        document.json
        native_text.json
        full_text.txt
        page_text/
        pages/
        """

        validated_path = self.validate_pdf(pdf_path)
        output_path = ensure_directory(output_directory)

        pages_directory = ensure_directory(output_path / "pages")
        page_text_directory = ensure_directory(
            output_path / "page_text"
        )

        file_hash = calculate_sha256(validated_path)
        document_id = f"doc_{file_hash[:16]}"

        logger.info(
            "Preparing PDF '%s' with document ID %s",
            validated_path.name,
            document_id,
        )

        try:
            document = fitz.open(validated_path)
        except Exception as error:
            raise PDFServiceError(
                f"Failed to open validated PDF: {validated_path}"
            ) from error

        page_results: list[PDFPageResult] = []
        native_text_pages: list[dict[str, Any]] = []
        full_text_sections: list[str] = []

        zoom = self.render_dpi / 72.0
        transformation_matrix = fitz.Matrix(zoom, zoom)

        try:
            for page_index in range(document.page_count):
                page = document.load_page(page_index)
                page_number = page_index + 1

                logger.info(
                    "Processing page %s of %s",
                    page_number,
                    document.page_count,
                )

                page_text = page.get_text("text").strip()
                native_text_available = bool(page_text)
                estimated_word_count = len(page_text.split())

                page_text_filename = f"page_{page_number:03d}.txt"
                page_text_path = (
                    page_text_directory / page_text_filename
                )
                page_text_path.write_text(
                    page_text,
                    encoding="utf-8",
                )

                image_filename = f"page_{page_number:03d}.png"
                image_path = pages_directory / image_filename

                pixmap = page.get_pixmap(
                    matrix=transformation_matrix,
                    alpha=False,
                    colorspace=fitz.csRGB,
                )
                pixmap.save(str(image_path))

                page_result = PDFPageResult(
                    page_number=page_number,
                    width_points=round(page.rect.width, 2),
                    height_points=round(page.rect.height, 2),
                    width_pixels=pixmap.width,
                    height_pixels=pixmap.height,
                    rotation=page.rotation,
                    native_text_available=native_text_available,
                    native_text_length=len(page_text),
                    native_text_path=get_relative_path(
                        page_text_path,
                        output_path,
                    ),
                    image_path=get_relative_path(
                        image_path,
                        output_path,
                    ),
                    estimated_word_count=estimated_word_count,
                )

                page_results.append(page_result)

                native_text_pages.append(
                    {
                        "page_number": page_number,
                        "text": page_text,
                        "native_text_available": (
                            native_text_available
                        ),
                        "character_count": len(page_text),
                        "estimated_word_count": (
                            estimated_word_count
                        ),
                    }
                )

                full_text_sections.append(
                    f"===== PAGE {page_number} =====\n\n"
                    f"{page_text}"
                )
        except Exception as error:
            raise PDFServiceError(
                f"PDF processing failed on page "
                f"{len(page_results) + 1}."
            ) from error
        finally:
            pdf_metadata = self._normalise_pdf_metadata(
                document.metadata
            )
            page_count = document.page_count
            document.close()

        full_text_path = output_path / "full_text.txt"
        full_text_path.write_text(
            "\n\n".join(full_text_sections),
            encoding="utf-8",
        )

        native_text_json_path = output_path / "native_text.json"
        save_json(
            {
                "document_id": document_id,
                "page_count": page_count,
                "pages": native_text_pages,
            },
            native_text_json_path,
        )

        result = PDFPreparationResult(
            document_id=document_id,
            original_filename=validated_path.name,
            source_path=str(validated_path),
            sha256=file_hash,
            file_size_bytes=validated_path.stat().st_size,
            page_count=page_count,
            pdf_metadata=pdf_metadata,
            render_dpi=self.render_dpi,
            processed_at=datetime.now()
            .astimezone()
            .isoformat(timespec="seconds"),
            full_text_path=get_relative_path(
                full_text_path,
                output_path,
            ),
            native_text_json_path=get_relative_path(
                native_text_json_path,
                output_path,
            ),
            pages_directory=get_relative_path(
                pages_directory,
                output_path,
            ),
            pages=page_results,
        )

        document_json_path = output_path / "document.json"
        save_json(result.to_dict(), document_json_path)

        logger.info(
            "PDF preparation completed. Generated %s page images.",
            page_count,
        )

        return result

    def inspect_pdf(
        self,
        pdf_path: str | Path,
    ) -> dict[str, Any]:
        """Return basic metadata without generating artifacts."""

        validated_path = self.validate_pdf(pdf_path)
        file_hash = calculate_sha256(validated_path)

        document = fitz.open(validated_path)

        try:
            page_dimensions = []

            for page_index in range(document.page_count):
                page = document.load_page(page_index)

                page_dimensions.append(
                    {
                        "page_number": page_index + 1,
                        "width_points": round(
                            page.rect.width,
                            2,
                        ),
                        "height_points": round(
                            page.rect.height,
                            2,
                        ),
                        "rotation": page.rotation,
                    }
                )

            return {
                "document_id": f"doc_{file_hash[:16]}",
                "filename": validated_path.name,
                "sha256": file_hash,
                "file_size_bytes": validated_path.stat().st_size,
                "page_count": document.page_count,
                "metadata": self._normalise_pdf_metadata(
                    document.metadata
                ),
                "pages": page_dimensions,
            }
        finally:
            document.close()

    @staticmethod
    def _normalise_pdf_metadata(
        metadata: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Convert PDF metadata into clean JSON-compatible values."""

        if not metadata:
            return {}

        return {
            str(key): value
            for key, value in metadata.items()
            if value not in (None, "")
        }
