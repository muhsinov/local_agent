import io
import zipfile
from pathlib import Path

import pytest
from docx import Document
from pypdf import PdfWriter

from app.api.errors import ApiError
from app.documents.extractor import extract_document
from app.documents.validator import validate_docx_archive
from tests.conftest import build_settings


def create_docx(path: Path, paragraphs: list[str], table_rows: list[list[str]] | None = None) -> None:
    document = Document()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    if table_rows:
        table = document.add_table(rows=len(table_rows), cols=len(table_rows[0]))
        for row_index, row in enumerate(table_rows):
            for column_index, value in enumerate(row):
                table.cell(row_index, column_index).text = value
    document.save(path)


def create_pdf(path: Path, encrypted: bool = False, pages: int = 1) -> None:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=200)
    if encrypted:
        writer.encrypt("secret")
    with open(path, "wb") as handle:
        writer.write(handle)


def test_extract_txt_document(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    path = tmp_path / "sample.txt"
    path.write_text("A\r\n\r\n\r\nB  \n", encoding="utf-8")
    extracted = extract_document(path, "txt", settings)
    assert extracted.text == "A\n\nB"
    assert extracted.status == "ready"


def test_extract_md_document(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    path = tmp_path / "sample.md"
    path.write_text("# Title\n\nText", encoding="utf-8")
    extracted = extract_document(path, "md", settings)
    assert "Title" in extracted.text


def test_extract_docx_document(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    path = tmp_path / "sample.docx"
    create_docx(path, ["Heading", "Paragraph"], [["A", "B"]])
    extracted = extract_document(path, "docx", settings)
    assert "Heading" in extracted.text
    assert "A | B" in extracted.text


def test_extract_blank_pdf_returns_no_text(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    path = tmp_path / "blank.pdf"
    create_pdf(path)
    extracted = extract_document(path, "pdf", settings)
    assert extracted.status == "no_text"
    assert extracted.warning_code == "OCR_REQUIRED"


def test_extract_encrypted_pdf_is_rejected(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    path = tmp_path / "encrypted.pdf"
    create_pdf(path, encrypted=True)
    with pytest.raises(ApiError) as exc:
        extract_document(path, "pdf", settings)
    assert exc.value.code == "PDF_ENCRYPTED"


def test_validate_docx_archive_rejects_missing_document_xml(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    path = tmp_path / "bad.docx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
    with pytest.raises(ApiError):
        validate_docx_archive(path, settings)
