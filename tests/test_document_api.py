import os
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

import app.api.documents as document_api
from app.main import create_app
from app.services.document_service import create_document
from tests.conftest import FakeOllamaClient, build_settings, build_test_app


def seed_document(settings):
    return create_document(
        settings,
        file_name="seed.txt",
        file_path="seed.txt",
        file_type="txt",
        size_bytes=4,
        sha256="seed",
        status="ready",
        text_path="seed.txt",
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


def test_document_preview_truncation_uses_db_char_count(monkeypatch, tmp_path) -> None:
    app, settings = build_test_app(tmp_path, FakeOllamaClient())
    with TestClient(app):
        document = seed_document(settings)
        (settings.resolved_upload_directory / "seed.txt").write_text("seed", encoding="utf-8")
        (settings.resolved_extracted_text_directory / "seed.txt").write_text("abcdefghij", encoding="utf-8")

    def forbidden_read_text(self, *args, **kwargs):
        raise AssertionError("preview should not read full file")

    monkeypatch.setattr(Path, "read_text", forbidden_read_text)
    with TestClient(app) as client:
        preview = client.get(f"/documents/{document.id}/text?limit=5")

    assert preview.status_code == 200
    assert preview.json()["text"] == "abcde"
    assert preview.json()["returned_chars"] == 5
    assert preview.json()["total_chars"] == 20
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
    assert response.json()["detail"]["code"] == "DATABASE_ERROR"
    assert raw_path.exists() is True
    assert text_path.exists() is True


def test_document_delete_rolls_back_on_text_rename_failure(monkeypatch, tmp_path) -> None:
    app, settings = build_test_app(tmp_path, FakeOllamaClient())
    with TestClient(app):
        document = seed_document(settings)
        raw_path = settings.resolved_upload_directory / "seed.txt"
        text_path = settings.resolved_extracted_text_directory / "seed.txt"
        raw_path.write_text("seed", encoding="utf-8")
        text_path.write_text("hello", encoding="utf-8")

    original_replace = document_api.os.replace
    calls = {"count": 0}

    def broken_replace(source, target):
        calls["count"] += 1
        if calls["count"] == 2:
            raise OSError("rename failed")
        return original_replace(source, target)

    monkeypatch.setattr(document_api.os, "replace", broken_replace)

    with TestClient(app) as client:
        response = client.delete(f"/documents/{document.id}?confirm=true")

    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "DOCUMENT_STORAGE_ERROR"
    assert raw_path.exists() is True
    assert text_path.exists() is True
    with sqlite3.connect(settings.resolved_database_path) as connection:
        count = connection.execute("SELECT COUNT(*) FROM documents WHERE id = ?;", (document.id,)).fetchone()[0]
    assert count == 1


def test_document_delete_unlink_failure_returns_success(monkeypatch, tmp_path) -> None:
    app, settings = build_test_app(tmp_path, FakeOllamaClient())
    with TestClient(app):
        document = seed_document(settings)
        raw_path = settings.resolved_upload_directory / "seed.txt"
        text_path = settings.resolved_extracted_text_directory / "seed.txt"
        raw_path.write_text("seed", encoding="utf-8")
        text_path.write_text("hello", encoding="utf-8")

    original_unlink = Path.unlink
    failed_once = {"value": False}

    def broken_unlink(self, missing_ok=False):
        if self.suffix == ".delete-pending" and not failed_once["value"]:
            failed_once["value"] = True
            raise PermissionError("busy")
        return original_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", broken_unlink)
    with TestClient(app) as client:
        response = client.delete(f"/documents/{document.id}?confirm=true")

    assert response.status_code == 200
    assert list(settings.resolved_upload_directory.glob("*.delete-pending"))


def test_startup_cleanup_removes_stale_quarantine_only_in_storage_dirs(tmp_path) -> None:
    settings = build_settings(tmp_path)
    settings.resolved_upload_directory.mkdir(parents=True, exist_ok=True)
    settings.resolved_extracted_text_directory.mkdir(parents=True, exist_ok=True)
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    stale_upload = settings.resolved_upload_directory / "stale.delete-pending"
    stale_text = settings.resolved_extracted_text_directory / "stale.delete-pending"
    outside = outside_dir / "stale.delete-pending"
    stale_upload.write_text("x", encoding="utf-8")
    stale_text.write_text("x", encoding="utf-8")
    outside.write_text("x", encoding="utf-8")

    app = create_app(settings)
    app.state.ollama_client = FakeOllamaClient()
    with TestClient(app):
        pass

    assert stale_upload.exists() is False
    assert stale_text.exists() is False
    assert outside.exists() is True


def test_document_endpoints_return_stable_database_errors(monkeypatch, tmp_path) -> None:
    app, settings = build_test_app(tmp_path, FakeOllamaClient())
    with TestClient(app):
        document = seed_document(settings)
        (settings.resolved_upload_directory / "seed.txt").write_text("seed", encoding="utf-8")
        (settings.resolved_extracted_text_directory / "seed.txt").write_text("hello", encoding="utf-8")

    def broken_list(*args, **kwargs):
        raise sqlite3.OperationalError("db")

    def broken_get(*args, **kwargs):
        raise sqlite3.OperationalError("db")

    monkeypatch.setattr(document_api, "list_documents", broken_list)
    monkeypatch.setattr(document_api, "get_document", broken_get)
    with TestClient(app) as client:
        responses = [
            client.get("/documents"),
            client.get(f"/documents/{document.id}"),
            client.get(f"/documents/{document.id}/text?limit=5"),
            client.delete(f"/documents/{document.id}?confirm=true"),
        ]

    for response in responses:
        assert response.status_code == 500
        assert response.json()["detail"]["code"] == "DATABASE_ERROR"
