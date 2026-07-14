import sqlite3

from fastapi.testclient import TestClient

import app.api.documents as document_api
from app.services.document_service import create_document
from tests.conftest import FakeOllamaClient, build_test_app


def seed_document(settings):
    return create_document(
        settings,
        file_name="seed.txt",
        file_path="data/uploads/seed.txt",
        file_type="txt",
        size_bytes=4,
        sha256="seed",
        status="ready",
        text_path="data/extracted/seed.txt",
        char_count=20,
        page_count=None,
        warning_code=None,
    )


def test_document_list_and_metadata(tmp_path) -> None:
    app, settings = build_test_app(tmp_path, FakeOllamaClient())
    with TestClient(app):
        document = seed_document(settings)
        (settings.resolved_upload_directory / "seed.txt").write_text("seed", encoding="utf-8")
        (settings.resolved_extracted_text_directory / "seed.txt").write_text("hello world", encoding="utf-8")

    with TestClient(app) as client:
        listing = client.get("/documents?limit=50&offset=0")
        metadata = client.get(f"/documents/{document.id}")

    assert listing.status_code == 200
    assert metadata.status_code == 200
    assert listing.json()["items"][0]["id"] == document.id
    assert "file_path" not in metadata.json()


def test_document_preview_truncation(tmp_path) -> None:
    app, settings = build_test_app(tmp_path, FakeOllamaClient())
    with TestClient(app):
        document = seed_document(settings)
        (settings.resolved_upload_directory / "seed.txt").write_text("seed", encoding="utf-8")
        (settings.resolved_extracted_text_directory / "seed.txt").write_text("abcdefghij", encoding="utf-8")

    with TestClient(app) as client:
        preview = client.get(f"/documents/{document.id}/text?limit=5")

    assert preview.status_code == 200
    assert preview.json()["truncated"] is True


def test_document_delete_requires_confirmation(tmp_path) -> None:
    app, settings = build_test_app(tmp_path, FakeOllamaClient())
    with TestClient(app):
        document = seed_document(settings)
        (settings.resolved_upload_directory / "seed.txt").write_text("seed", encoding="utf-8")
        (settings.resolved_extracted_text_directory / "seed.txt").write_text("hello", encoding="utf-8")

    with TestClient(app) as client:
        response = client.delete(f"/documents/{document.id}")

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "CONFIRMATION_REQUIRED"


def test_document_delete_removes_files_and_row(tmp_path) -> None:
    app, settings = build_test_app(tmp_path, FakeOllamaClient())
    with TestClient(app):
        document = seed_document(settings)
        raw_path = settings.resolved_upload_directory / "seed.txt"
        text_path = settings.resolved_extracted_text_directory / "seed.txt"
        raw_path.write_text("seed", encoding="utf-8")
        text_path.write_text("hello", encoding="utf-8")

    with TestClient(app) as client:
        response = client.delete(f"/documents/{document.id}?confirm=true")

    assert response.status_code == 200
    assert raw_path.exists() is False
    assert text_path.exists() is False
    with sqlite3.connect(settings.resolved_database_path) as connection:
        count = connection.execute("SELECT COUNT(*) FROM documents WHERE id = ?;", (document.id,)).fetchone()[0]
    assert count == 0


def test_document_preview_missing_storage_returns_stable_error(tmp_path) -> None:
    app, settings = build_test_app(tmp_path, FakeOllamaClient())
    with TestClient(app):
        document = seed_document(settings)

    with TestClient(app) as client:
        response = client.get(f"/documents/{document.id}/text?limit=5")

    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "DOCUMENT_STORAGE_ERROR"


def test_document_delete_rolls_back_rename_on_database_error(monkeypatch, tmp_path) -> None:
    app, settings = build_test_app(tmp_path, FakeOllamaClient())
    with TestClient(app):
        document = seed_document(settings)
        raw_path = settings.resolved_upload_directory / "seed.txt"
        text_path = settings.resolved_extracted_text_directory / "seed.txt"
        raw_path.write_text("seed", encoding="utf-8")
        text_path.write_text("hello", encoding="utf-8")

    def broken_delete(*args, **kwargs):
        raise sqlite3.OperationalError("db error")

    monkeypatch.setattr(document_api, "delete_document_record", broken_delete)

    with TestClient(app) as client:
        response = client.delete(f"/documents/{document.id}?confirm=true")

    assert response.status_code == 500
    assert raw_path.exists() is True
    assert text_path.exists() is True
