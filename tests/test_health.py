import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings, get_settings
from app.main import create_app


def build_test_settings(tmp_path: Path) -> Settings:
    return Settings(
        DATABASE_PATH=tmp_path / "test_local_agent.db",
        UPLOAD_DIRECTORY=tmp_path / "uploads",
        VECTOR_STORE_DIRECTORY=tmp_path / "vector_store",
    )


def test_health_endpoint_returns_ok_and_uses_temp_database(tmp_path: Path) -> None:
    test_settings = build_test_settings(tmp_path)
    app = create_app(test_settings)

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "app": "local-agent-demo",
        "version": "0.1.0",
        "database": "ok",
    }
    assert test_settings.resolved_database_path.exists()


def test_required_tables_are_created(tmp_path: Path) -> None:
    test_settings = build_test_settings(tmp_path)
    app = create_app(test_settings)

    with TestClient(app):
        pass

    with sqlite3.connect(test_settings.resolved_database_path) as connection:
        rows = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name IN ('conversations', 'messages', 'documents', 'audit_logs');
            """
        ).fetchall()

    assert {row[0] for row in rows} == {"conversations", "messages", "documents", "audit_logs"}


def test_documents_and_audit_logs_columns_match_spec(tmp_path: Path) -> None:
    test_settings = build_test_settings(tmp_path)
    app = create_app(test_settings)

    with TestClient(app):
        pass

    with sqlite3.connect(test_settings.resolved_database_path) as connection:
        documents = connection.execute("PRAGMA table_info(documents);").fetchall()
        audit_logs = connection.execute("PRAGMA table_info(audit_logs);").fetchall()

    document_columns = {column[1] for column in documents}
    audit_columns = {column[1] for column in audit_logs}
    assert {
        "id",
        "file_name",
        "file_path",
        "file_type",
        "indexed",
        "created_at",
    }.issubset(document_columns)
    assert {
        "id",
        "action",
        "tool_name",
        "arguments",
        "status",
        "execution_time_ms",
        "created_at",
    }.issubset(audit_columns)


def test_invalid_config_values_raise_validation_error() -> None:
    with pytest.raises(ValidationError):
        Settings(PORT=70000)

    with pytest.raises(ValidationError):
        Settings(REQUEST_TIMEOUT_SECONDS=0)

    with pytest.raises(ValidationError):
        Settings(MAX_AGENT_ITERATIONS=11)

    with pytest.raises(ValidationError):
        Settings(MAX_FILE_SIZE_MB=101)


def test_global_settings_cache_is_unchanged() -> None:
    get_settings.cache_clear()
    baseline = get_settings()

    Settings(
        DATABASE_PATH=Path("data/test_override.db"),
        UPLOAD_DIRECTORY=Path("data/test_uploads"),
        VECTOR_STORE_DIRECTORY=Path("data/test_vector_store"),
    )

    current = get_settings()
    assert current.resolved_database_path == baseline.resolved_database_path
