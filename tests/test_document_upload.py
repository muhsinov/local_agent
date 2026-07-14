from pathlib import Path

from docx import Document
from fastapi.testclient import TestClient
from pypdf import PdfWriter

from tests.conftest import FakeOllamaClient, build_test_app


def build_docx_bytes() -> bytes:
    path = Path.cwd() / "_temp_test.docx"
    document = Document()
    document.add_paragraph("Hello docx")
    document.save(path)
    data = path.read_bytes()
    path.unlink()
    return data


def build_pdf_bytes() -> bytes:
    path = Path.cwd() / "_temp_test.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    with open(path, "wb") as handle:
        writer.write(handle)
    data = path.read_bytes()
    path.unlink()
    return data


def test_valid_txt_upload(tmp_path) -> None:
    app, _ = build_test_app(tmp_path, FakeOllamaClient())
    with TestClient(app) as client:
        response = client.post("/documents/upload", files={"file": ("sample.txt", b"hello", "text/plain")})
    assert response.status_code == 201
    assert response.json()["file_type"] == "txt"


def test_valid_md_upload(tmp_path) -> None:
    app, _ = build_test_app(tmp_path, FakeOllamaClient())
    with TestClient(app) as client:
        response = client.post("/documents/upload", files={"file": ("sample.md", b"# Title", "text/markdown")})
    assert response.status_code == 201
    assert response.json()["file_type"] == "md"


def test_valid_docx_upload(tmp_path) -> None:
    app, _ = build_test_app(tmp_path, FakeOllamaClient())
    with TestClient(app) as client:
        response = client.post(
            "/documents/upload",
            files={
                "file": (
                    "sample.docx",
                    build_docx_bytes(),
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
        )
    assert response.status_code == 201
    assert response.json()["file_type"] == "docx"


def test_valid_blank_pdf_upload(tmp_path) -> None:
    app, _ = build_test_app(tmp_path, FakeOllamaClient())
    with TestClient(app) as client:
        response = client.post("/documents/upload", files={"file": ("sample.pdf", build_pdf_bytes(), "application/pdf")})
    assert response.status_code == 201
    assert response.json()["status"] == "no_text"


def test_oversized_file_returns_413(tmp_path) -> None:
    app, _ = build_test_app(tmp_path, FakeOllamaClient(), MAX_FILE_SIZE_MB=1)
    with TestClient(app) as client:
        response = client.post("/documents/upload", files={"file": ("big.txt", b"a" * (1024 * 1024 + 1), "text/plain")})
    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "FILE_TOO_LARGE"


def test_unsupported_extension_returns_415(tmp_path) -> None:
    app, _ = build_test_app(tmp_path, FakeOllamaClient())
    with TestClient(app) as client:
        response = client.post("/documents/upload", files={"file": ("sample.rtf", b"{\\rtf1}", "application/rtf")})
    assert response.status_code == 415


def test_fake_pdf_returns_415(tmp_path) -> None:
    app, _ = build_test_app(tmp_path, FakeOllamaClient())
    with TestClient(app) as client:
        response = client.post("/documents/upload", files={"file": ("fake.pdf", b"not pdf", "application/pdf")})
    assert response.status_code == 415


def test_invalid_utf8_returns_415(tmp_path) -> None:
    app, _ = build_test_app(tmp_path, FakeOllamaClient())
    with TestClient(app) as client:
        response = client.post("/documents/upload", files={"file": ("bad.txt", b"\xff\xfe\xfd", "text/plain")})
    assert response.status_code == 415


def test_duplicate_upload_returns_409(tmp_path) -> None:
    app, _ = build_test_app(tmp_path, FakeOllamaClient())
    with TestClient(app) as client:
        first = client.post("/documents/upload", files={"file": ("dup.txt", b"same text", "text/plain")})
        second = client.post("/documents/upload", files={"file": ("dup.txt", b"same text", "text/plain")})
    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["detail"]["code"] == "DOCUMENT_DUPLICATE"
