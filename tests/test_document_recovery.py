import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.services.document_recovery_service import reconcile_document_quarantine
from app.services.document_service import create_document
from tests.conftest import FakeOllamaClient, build_settings, build_test_app


def seed_document(settings, *, file_path: str = "seed.txt", text_path: str | None = "seed.txt"):
    return create_document(
        settings,
        file_name="seed.txt",
        file_path=file_path,
        file_type="txt",
        size_bytes=4,
        sha256=f"seed-{file_path}-{text_path}",
        status="ready",
        text_path=text_path,
        char_count=5,
        page_count=None,
        warning_code=None,
    )


def test_reconcile_restores_raw_quarantine_when_db_row_exists(tmp_path) -> None:
    app, settings = build_test_app(tmp_path, FakeOllamaClient())
    with TestClient(app):
        seed_document(settings, file_path="seed.txt")
    quarantine = settings.resolved_upload_directory / "seed.txt.1234567890abcdef1234567890abcdef.delete-pending"
    quarantine.write_text("seed", encoding="utf-8")

    reconcile_document_quarantine(settings)

    assert (settings.resolved_upload_directory / "seed.txt").exists() is True
    assert quarantine.exists() is False


def test_reconcile_restores_text_quarantine_when_db_row_exists(tmp_path) -> None:
    app, settings = build_test_app(tmp_path, FakeOllamaClient())
    with TestClient(app):
        seed_document(settings, text_path="seed.txt")
    quarantine = settings.resolved_extracted_text_directory / "seed.txt.1234567890abcdef1234567890abcdef.delete-pending"
    quarantine.write_text("seed", encoding="utf-8")

    reconcile_document_quarantine(settings)

    assert (settings.resolved_extracted_text_directory / "seed.txt").exists() is True
    assert quarantine.exists() is False


def test_reconcile_cleans_committed_delete_quarantine(tmp_path) -> None:
    settings = build_settings(tmp_path)
    settings.resolved_upload_directory.mkdir(parents=True, exist_ok=True)
    settings.resolved_extracted_text_directory.mkdir(parents=True, exist_ok=True)
    app = create_app(settings)
    app.state.ollama_client = FakeOllamaClient()
    with TestClient(app):
        pass

    quarantine = settings.resolved_upload_directory / "gone.txt.1234567890abcdef1234567890abcdef.delete-pending"
    quarantine.write_text("seed", encoding="utf-8")
    reconcile_document_quarantine(settings)
    assert quarantine.exists() is False


def test_reconcile_ignores_invalid_quarantine_pattern(tmp_path) -> None:
    settings = build_settings(tmp_path)
    settings.resolved_upload_directory.mkdir(parents=True, exist_ok=True)
    settings.resolved_extracted_text_directory.mkdir(parents=True, exist_ok=True)
    app = create_app(settings)
    app.state.ollama_client = FakeOllamaClient()
    with TestClient(app):
        pass

    quarantine = settings.resolved_upload_directory / "notes.delete-pending"
    quarantine.write_text("seed", encoding="utf-8")
    reconcile_document_quarantine(settings)
    assert quarantine.exists() is True


def test_startup_reconciliation_does_not_touch_outside_directories(tmp_path) -> None:
    settings = build_settings(tmp_path)
    settings.resolved_upload_directory.mkdir(parents=True, exist_ok=True)
    settings.resolved_extracted_text_directory.mkdir(parents=True, exist_ok=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    outside_quarantine = outside / "seed.txt.1234567890abcdef1234567890abcdef.delete-pending"
    outside_quarantine.write_text("seed", encoding="utf-8")

    app = create_app(settings)
    app.state.ollama_client = FakeOllamaClient()
    with TestClient(app):
        pass

    assert outside_quarantine.exists() is True


def test_restart_reconciliation_restores_after_db_rollback_failure(monkeypatch, tmp_path) -> None:
    app, settings = build_test_app(tmp_path, FakeOllamaClient())
    with TestClient(app):
        document = seed_document(settings)
        raw_path = settings.resolved_upload_directory / "seed.txt"
        text_path = settings.resolved_extracted_text_directory / "seed.txt"
        raw_path.write_text("seed", encoding="utf-8")
        text_path.write_text("hello", encoding="utf-8")

    calls = {"count": 0}
    real_replace = __import__("os").replace

    def broken_delete(*args, **kwargs):
        raise sqlite3.OperationalError("db error")

    def flaky_replace(source, target):
        calls["count"] += 1
        if calls["count"] == 3:
            raise OSError("restore failed")
        return real_replace(source, target)

    import app.api.documents as document_api

    monkeypatch.setattr(document_api, "delete_document_record", broken_delete)
    monkeypatch.setattr(document_api.os, "replace", flaky_replace)

    with TestClient(app) as client:
        response = client.delete(f"/documents/{document.id}?confirm=true")

    assert response.status_code == 500
    assert list(settings.resolved_upload_directory.glob("*.delete-pending")) or list(
        settings.resolved_extracted_text_directory.glob("*.delete-pending")
    )
    reconcile_document_quarantine(settings)
    assert raw_path.exists() is True
    assert text_path.exists() is True
