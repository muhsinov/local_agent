import asyncio
import builtins
import io
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest
from docx import Document
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from starlette.datastructures import UploadFile

import app.api.documents as document_api
import app.documents.storage as document_storage
from app.api.documents import upload_document
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


def assert_clean_storage(root: Path) -> None:
    assert list((root / "uploads").glob("*")) == []
    assert list((root / "extracted").glob("*")) == []


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


def test_duplicate_upload_returns_existing_document_id(tmp_path) -> None:
    app, _ = build_test_app(tmp_path, FakeOllamaClient())
    with TestClient(app) as client:
        first = client.post("/documents/upload", files={"file": ("dup.txt", b"same text", "text/plain")})
        second = client.post("/documents/upload", files={"file": ("dup.txt", b"same text", "text/plain")})
    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["detail"]["code"] == "DOCUMENT_DUPLICATE"
    assert second.json()["detail"]["existing_document_id"] == first.json()["id"]


def test_signature_validation_runs_in_thread(monkeypatch, tmp_path) -> None:
    app, _ = build_test_app(tmp_path, FakeOllamaClient())
    called = {"value": False}
    original_to_thread = document_api.asyncio.to_thread

    async def tracking_to_thread(func, *args, **kwargs):
        called["value"] = True
        return await original_to_thread(func, *args, **kwargs)

    monkeypatch.setattr(document_api.asyncio, "to_thread", tracking_to_thread)
    with TestClient(app) as client:
        response = client.post("/documents/upload", files={"file": ("sample.txt", b"hello", "text/plain")})
    assert response.status_code == 201
    assert called["value"] is True


def test_pdf_signature_validation_uses_bounded_read(monkeypatch, tmp_path) -> None:
    app, _ = build_test_app(tmp_path, FakeOllamaClient())
    pdf_bytes = build_pdf_bytes()

    def fail_read_bytes(self):
        raise AssertionError("read_bytes should not be used for PDF header validation")

    monkeypatch.setattr(Path, "read_bytes", fail_read_bytes)
    with TestClient(app) as client:
        response = client.post("/documents/upload", files={"file": ("sample.pdf", pdf_bytes, "application/pdf")})
    assert response.status_code == 201


def test_upload_cleanup_on_raw_write_error(monkeypatch, tmp_path) -> None:
    app, settings = build_test_app(tmp_path, FakeOllamaClient())
    original_open = builtins.open

    def broken_open(path, mode="r", *args, **kwargs):
        if str(path).endswith(".part") and mode == "wb":
            raise OSError("disk full")
        return original_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", broken_open)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post("/documents/upload", files={"file": ("sample.txt", b"hello", "text/plain")})
    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "DOCUMENT_STORAGE_ERROR"
    assert_clean_storage(tmp_path)


def test_upload_cleanup_on_raw_rename_error(monkeypatch, tmp_path) -> None:
    app, _ = build_test_app(tmp_path, FakeOllamaClient())
    original_replace = document_api.os.replace

    def broken_replace(source, target):
        if str(source).endswith(".part") and str(target).endswith(".txt"):
            raise OSError("rename failed")
        return original_replace(source, target)

    monkeypatch.setattr(document_api.os, "replace", broken_replace)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post("/documents/upload", files={"file": ("sample.txt", b"hello", "text/plain")})
    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "DOCUMENT_STORAGE_ERROR"
    assert_clean_storage(tmp_path)


def test_upload_cleanup_on_extraction_exception(monkeypatch, tmp_path) -> None:
    app, _ = build_test_app(tmp_path, FakeOllamaClient())

    async def broken_extract(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(document_api, "extract_document_isolated_async", broken_extract)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post("/documents/upload", files={"file": ("sample.txt", b"hello", "text/plain")})
    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "DOCUMENT_PROCESSING_ERROR"
    assert_clean_storage(tmp_path)


def test_upload_cleanup_on_text_write_error(monkeypatch, tmp_path) -> None:
    app, _ = build_test_app(tmp_path, FakeOllamaClient())

    def broken_write(*args, **kwargs):
        raise OSError("write failed")

    monkeypatch.setattr(document_api, "write_atomic_text", broken_write)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post("/documents/upload", files={"file": ("sample.txt", b"hello", "text/plain")})
    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "DOCUMENT_STORAGE_ERROR"
    assert_clean_storage(tmp_path)


def test_upload_cleanup_on_text_replace_error(monkeypatch, tmp_path) -> None:
    app, _ = build_test_app(tmp_path, FakeOllamaClient())
    original_replace = document_storage.os.replace
    calls = {"count": 0}

    def broken_replace(source, target):
        calls["count"] += 1
        if calls["count"] == 1:
            raise OSError("replace failed")
        return original_replace(source, target)

    monkeypatch.setattr(document_storage.os, "replace", broken_replace)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post("/documents/upload", files={"file": ("sample.txt", b"hello", "text/plain")})
    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "DOCUMENT_STORAGE_ERROR"
    assert_clean_storage(tmp_path)


def test_upload_cleanup_on_database_insert_error(monkeypatch, tmp_path) -> None:
    app, _ = build_test_app(tmp_path, FakeOllamaClient())

    def broken_create(*args, **kwargs):
        raise sqlite3.OperationalError("db down")

    monkeypatch.setattr(document_api, "create_document", broken_create)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post("/documents/upload", files={"file": ("sample.txt", b"hello", "text/plain")})
    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "DATABASE_ERROR"
    assert_clean_storage(tmp_path)


def test_upload_cleanup_on_document_record_parse_failure(monkeypatch, tmp_path) -> None:
    app, _ = build_test_app(tmp_path, FakeOllamaClient())

    def broken_create(*args, **kwargs):
        raise ValueError("bad row")

    monkeypatch.setattr(document_api, "create_document", broken_create)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post("/documents/upload", files={"file": ("sample.txt", b"hello", "text/plain")})
    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "DATABASE_ERROR"
    assert_clean_storage(tmp_path)


def test_duplicate_race_returns_409_and_cleans_loser_files(tmp_path) -> None:
    app, settings = build_test_app(tmp_path, FakeOllamaClient())
    payload = {"file": ("dup.txt", b"same text", "text/plain")}

    with TestClient(app) as client:
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _: client.post("/documents/upload", files=payload), range(2)))

    statuses = sorted(response.status_code for response in responses)
    assert statuses == [201, 409]
    duplicate = next(response for response in responses if response.status_code == 409)
    winner = next(response for response in responses if response.status_code == 201)
    assert duplicate.json()["detail"]["existing_document_id"] == winner.json()["id"]

    with sqlite3.connect(settings.resolved_database_path) as connection:
        count = connection.execute("SELECT COUNT(*) FROM documents;").fetchone()[0]
    assert count == 1
    assert len(list(settings.resolved_upload_directory.glob("*"))) == 1
    assert len(list(settings.resolved_extracted_text_directory.glob("*"))) == 1


def test_upload_cancellation_cleans_artifacts_and_releases_semaphore(monkeypatch, tmp_path) -> None:
    app, settings = build_test_app(tmp_path, FakeOllamaClient())
    with TestClient(app):
        pass
    process_terminated = {"value": False}

    async def cancelling_extract(*args, **kwargs):
        started.set()
        try:
            while True:
                await asyncio.sleep(0)
        except asyncio.CancelledError:
            process_terminated["value"] = True
            raise

    monkeypatch.setattr(document_api, "extract_document_isolated_async", cancelling_extract)
    started = asyncio.Event()

    async def run_test() -> None:
        upload = UploadFile(filename="sample.txt", file=io.BytesIO(b"hello"))
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(settings=settings, document_semaphore=asyncio.Semaphore(1))))
        task = asyncio.create_task(upload_document(request, upload))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await asyncio.wait_for(request.app.state.document_semaphore.acquire(), timeout=1)
        assert request.app.state.document_semaphore.locked() is True

    asyncio.run(run_test())
    assert process_terminated["value"] is True
    assert list(settings.resolved_upload_directory.rglob("*")) == []
    assert list(settings.resolved_extracted_text_directory.rglob("*")) == []


def test_health_responds_during_document_processing(monkeypatch, tmp_path) -> None:
    app, _ = build_test_app(tmp_path, FakeOllamaClient())
    entered = threading.Event()
    release = threading.Event()

    async def slow_extract(*args, **kwargs):
        entered.set()
        while not release.is_set():
            await asyncio.sleep(0)
        return SimpleNamespace(text="hello", char_count=5, page_count=None, status="ready", warning_code=None)

    monkeypatch.setattr(document_api, "extract_document_isolated_async", slow_extract)

    with TestClient(app) as client:
        upload_response = {}

        def run_upload():
            upload_response["response"] = client.post("/documents/upload", files={"file": ("sample.txt", b"hello", "text/plain")})

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(run_upload)
            assert entered.wait(timeout=1)
            health = client.get("/health")
            release.set()
            future.result()

    assert health.status_code == 200
    assert upload_response["response"].status_code == 201
