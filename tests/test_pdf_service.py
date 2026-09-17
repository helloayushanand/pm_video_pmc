"""Tests for PDF preparation."""

from pathlib import Path

import fitz
import pytest

from app.services.pdf_service import (
    InvalidPDFError,
    PDFService,
)
from app.utils.json_utils import load_json


def create_test_pdf(output_path):
    document = fitz.open()

    first_page = document.new_page(
        width=595,
        height=842,
    )

    first_page.insert_text(
        (72, 72),
        "Candidate Profile",
        fontsize=18,
    )

    first_page.insert_text(
        (72, 110),
        "Test Candidate",
        fontsize=14,
    )

    first_page.insert_text(
        (72, 145),
        "Current Role: Chief Executive",
        fontsize=11,
    )

    second_page = document.new_page(
        width=595,
        height=842,
    )

    second_page.insert_text(
        (72, 72),
        "Career Highlights",
        fontsize=18,
    )

    second_page.insert_text(
        (72, 110),
        "Led a major business transformation.",
        fontsize=11,
    )

    document.save(str(output_path))
    document.close()

    return output_path


def test_validate_pdf_rejects_missing_file(tmp_path):
    service = PDFService()

    with pytest.raises(FileNotFoundError):
        service.validate_pdf(
            tmp_path / "missing.pdf"
        )


def test_validate_pdf_rejects_non_pdf(tmp_path):
    text_file = tmp_path / "candidate.txt"
    text_file.write_text(
        "Not a PDF",
        encoding="utf-8",
    )

    service = PDFService()

    with pytest.raises(InvalidPDFError):
        service.validate_pdf(text_file)


def test_prepare_pdf_creates_expected_artifacts(tmp_path):
    source_pdf = create_test_pdf(
        tmp_path / "candidate.pdf"
    )

    output_directory = tmp_path / "prepared"

    service = PDFService(render_dpi=100)

    result = service.prepare_pdf(
        pdf_path=source_pdf,
        output_directory=output_directory,
    )

    assert result.page_count == 2
    assert len(result.pages) == 2

    assert (
        output_directory / "document.json"
    ).exists()

    assert (
        output_directory / "native_text.json"
    ).exists()

    assert (
        output_directory / "full_text.txt"
    ).exists()

    assert (
        output_directory / "pages" / "page_001.png"
    ).exists()

    assert (
        output_directory / "pages" / "page_002.png"
    ).exists()

    assert (
        output_directory / "page_text" / "page_001.txt"
    ).exists()

    document_metadata = load_json(
        output_directory / "document.json"
    )

    assert document_metadata["page_count"] == 2
    assert document_metadata["render_dpi"] == 100

    full_text = (
        output_directory / "full_text.txt"
    ).read_text(encoding="utf-8")

    assert "Test Candidate" in full_text
    assert "Career Highlights" in full_text


def test_inspect_pdf_does_not_create_artifacts(tmp_path):
    source_pdf = create_test_pdf(
        tmp_path / "candidate.pdf"
    )

    service = PDFService()
    inspection = service.inspect_pdf(source_pdf)

    assert inspection["page_count"] == 2
    assert inspection["filename"] == "candidate.pdf"
    assert len(inspection["pages"]) == 2
