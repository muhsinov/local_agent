import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings, get_settings
from app.database import check_database
from app.main import create_app


def build_test_settings(tmp_path: Path) -> Settings:
    return Settings(
        DATABASE_PATH=tmp_path / "test_local_agent.db",
        UPLOAD_DIRECTORY=tmp_path / "uploads",
        EXTRACTED_TEXT_DIRECTORY=tmp_path / "extracted",
        VECTOR_STORE_DIRECTORY=tmp_path / "vector_store",
        LOCAL_CONTROL_PLANE_ENABLED=False,
        RUNTIME_RESILIENCE_ENABLED=False,
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
            WHERE type = 'table' AND name IN ('conversations', 'messages', 'documents', 'audit_logs', 'document_chunks', 'vector_index_state', 'approval_requests');
            """
        ).fetchall()

    assert {row[0] for row in rows} == {
        "conversations",
        "messages",
        "documents",
        "audit_logs",
        "document_chunks",
        "vector_index_state",
        "approval_requests",
    }


def test_documents_and_audit_logs_columns_match_spec(tmp_path: Path) -> None:
    test_settings = build_test_settings(tmp_path)
    app = create_app(test_settings)

    with TestClient(app):
        pass

    with sqlite3.connect(test_settings.resolved_database_path) as connection:
        documents = connection.execute("PRAGMA table_info(documents);").fetchall()
        audit_logs = connection.execute("PRAGMA table_info(audit_logs);").fetchall()
        document_chunks = connection.execute("PRAGMA table_info(document_chunks);").fetchall()
        vector_index_state = connection.execute("PRAGMA table_info(vector_index_state);").fetchall()
        approval_requests = connection.execute("PRAGMA table_info(approval_requests);").fetchall()

    document_columns = {column[1] for column in documents}
    audit_columns = {column[1] for column in audit_logs}
    chunk_columns = {column[1] for column in document_chunks}
    state_columns = {column[1] for column in vector_index_state}
    approval_columns = {column[1] for column in approval_requests}
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
    assert {"document_id", "chunk_index", "text", "start_char", "end_char", "char_count", "content_sha256"}.issubset(
        chunk_columns
    )
    assert {"active_generation", "status", "chunk_count", "document_count", "dirty"}.issubset(state_columns)
    assert {"tool_name", "arguments_json", "arguments_sha256", "nonce_sha256", "status", "safe_summary"}.issubset(
        approval_columns
    )


def test_invalid_config_values_raise_validation_error() -> None:
    with pytest.raises(ValidationError):
        Settings(PORT=70000)

    with pytest.raises(ValidationError):
        Settings(REQUEST_TIMEOUT_SECONDS=0)

    with pytest.raises(ValidationError):
        Settings(MAX_AGENT_ITERATIONS=11)

    with pytest.raises(ValidationError):
        Settings(MAX_FILE_SIZE_MB=101)

    with pytest.raises(ValidationError):
        Settings(DOCUMENT_EXTRACTION_TIMEOUT_SECONDS=301)

    with pytest.raises(ValidationError):
        Settings(DOCUMENT_EXTRACTION_MEMORY_MB=64)


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


def test_health_endpoint_reports_error_for_bad_schema_version(tmp_path: Path) -> None:
    test_settings = build_test_settings(tmp_path)
    app = create_app(test_settings)

    with TestClient(app) as client:
        with sqlite3.connect(test_settings.resolved_database_path) as connection:
            connection.execute("UPDATE schema_version SET version = 1;")
            connection.commit()
        response = client.get("/health")

    assert response.status_code == 503
    assert response.json()["database"] == "error"


def test_check_database_rejects_missing_messages_foreign_key(tmp_path: Path) -> None:
    settings = build_test_settings(tmp_path)
    connection = sqlite3.connect(settings.resolved_database_path)
    connection.executescript(
        """
        CREATE TABLE conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            title TEXT NOT NULL DEFAULT 'New conversation',
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_name TEXT NOT NULL,
            file_path TEXT NOT NULL,
            file_type TEXT NOT NULL,
            indexed INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            size_bytes INTEGER NOT NULL DEFAULT 0,
            sha256 TEXT,
            status TEXT NOT NULL DEFAULT 'uploaded',
            text_path TEXT,
            char_count INTEGER NOT NULL DEFAULT 0,
            page_count INTEGER,
            warning_code TEXT,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE UNIQUE INDEX idx_documents_sha256 ON documents(sha256) WHERE sha256 IS NOT NULL;
        CREATE INDEX idx_documents_created_at ON documents(created_at DESC);
        CREATE TABLE audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT NOT NULL,
            tool_name TEXT,
            arguments TEXT,
            status TEXT NOT NULL,
            execution_time_ms INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE schema_version (version INTEGER NOT NULL);
        CREATE TABLE document_chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL,
            chunk_index INTEGER NOT NULL,
            text TEXT NOT NULL,
            start_char INTEGER NOT NULL,
            end_char INTEGER NOT NULL,
            char_count INTEGER NOT NULL,
            content_sha256 TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX idx_document_chunks_document ON document_chunks(document_id, chunk_index);
        CREATE INDEX idx_document_chunks_sha256 ON document_chunks(content_sha256);
        CREATE TABLE vector_index_state (
            id INTEGER PRIMARY KEY CHECK(id = 1),
            active_generation TEXT,
            status TEXT NOT NULL DEFAULT 'empty',
            embedding_model TEXT,
            embedding_dimension INTEGER,
            chunk_count INTEGER NOT NULL DEFAULT 0,
            document_count INTEGER NOT NULL DEFAULT 0,
            dirty INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        INSERT INTO vector_index_state(id, status, chunk_count, document_count, dirty) VALUES (1, 'empty', 0, 0, 0);
        CREATE TABLE approval_requests (
            id TEXT PRIMARY KEY,
            conversation_id INTEGER NULL,
            tool_call_id TEXT NOT NULL,
            tool_name TEXT NOT NULL,
            arguments_json TEXT NOT NULL,
            arguments_sha256 TEXT NOT NULL,
            nonce_sha256 TEXT NOT NULL,
            original_user_message TEXT NOT NULL,
            use_rag INTEGER NOT NULL DEFAULT 0,
            document_ids_json TEXT NULL,
            status TEXT NOT NULL,
            safe_summary TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            expires_at TEXT NOT NULL,
            executing_at TEXT NULL,
            completed_at TEXT NULL,
            error_code TEXT NULL,
            execution_result_json TEXT NULL
        );
        CREATE INDEX idx_approval_requests_status ON approval_requests(status);
        CREATE INDEX idx_approval_requests_expires_at ON approval_requests(expires_at);
        INSERT INTO schema_version(version) VALUES (4);
        PRAGMA user_version = 4;
        """
    )
    connection.commit()
    connection.close()

    assert check_database(settings) is False
