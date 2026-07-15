import sqlite3

import pytest

import app.database as database
from app.database import (
    DOCUMENT_CHUNK_COLUMNS,
    DOCUMENT_COLUMNS_V2,
    SCHEMA_VERSION,
    VECTOR_INDEX_STATE_COLUMNS,
    check_database,
    initialize_database,
)
from tests.conftest import build_settings


def create_v1_database(path) -> None:
    connection = sqlite3.connect(path)
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
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
        );
        CREATE TABLE documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_name TEXT NOT NULL,
            file_path TEXT NOT NULL,
            file_type TEXT NOT NULL,
            indexed INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT NOT NULL,
            tool_name TEXT,
            arguments TEXT,
            status TEXT NOT NULL,
            execution_time_ms INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        INSERT INTO conversations (title) VALUES ('Old');
        INSERT INTO messages (conversation_id, role, content) VALUES (1, 'user', 'hello');
        INSERT INTO documents (file_name, file_path, file_type) VALUES ('a.txt', 'data/uploads/a.txt', 'txt');
        PRAGMA user_version = 1;
        """
    )
    connection.commit()
    connection.close()


def add_v4_approval_table(path, *, include_deadline: bool = False) -> None:
    connection = sqlite3.connect(path)
    deadline_column = ", execution_deadline_at TEXT NULL" if include_deadline else ""
    connection.executescript(
        f"""
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
            execution_result_json TEXT NULL{deadline_column},
            FOREIGN KEY(conversation_id) REFERENCES conversations(id)
        );
        CREATE INDEX idx_approval_requests_status ON approval_requests(status);
        CREATE INDEX idx_approval_requests_expires_at ON approval_requests(expires_at);
        INSERT INTO approval_requests (
            id, tool_call_id, tool_name, arguments_json, arguments_sha256, nonce_sha256,
            original_user_message, status, safe_summary, expires_at
        ) VALUES
            ('pending-1', 'call_1', 'rename_conversation', '{{}}', 'a', 'b', 'pending', 'pending', 'summary', datetime('now', '+1 hour')),
            ('executed-1', 'call_2', 'rename_conversation', '{{}}', 'c', 'd', 'executed', 'executed', 'summary', datetime('now', '+1 hour')),
            ('rejected-1', 'call_3', 'rename_conversation', '{{}}', 'e', 'f', 'rejected', 'rejected', 'summary', datetime('now', '+1 hour'));
        CREATE TABLE schema_version (version INTEGER NOT NULL);
        INSERT INTO schema_version(version) VALUES (4);
        PRAGMA user_version = 4;
        """
    )
    connection.commit()
    connection.close()


def inspect_state(path):
    connection = sqlite3.connect(path)
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()}
    version = connection.execute("PRAGMA user_version;").fetchone()[0]
    schema_value = None
    if "schema_version" in tables:
        row = connection.execute("SELECT version FROM schema_version LIMIT 1;").fetchone()
        schema_value = row[0] if row else None
    count = connection.execute("SELECT COUNT(*) FROM documents;").fetchone()[0]
    connection.close()
    return tables, version, schema_value, count


def test_version_1_database_migrates_to_v6(tmp_path) -> None:
    settings = build_settings(tmp_path)
    create_v1_database(settings.resolved_database_path)
    initialize_database(settings)

    connection = sqlite3.connect(settings.resolved_database_path)
    columns = {row[1] for row in connection.execute("PRAGMA table_info(documents);").fetchall()}
    chunk_columns = {row[1] for row in connection.execute("PRAGMA table_info(document_chunks);").fetchall()}
    state_columns = {row[1] for row in connection.execute("PRAGMA table_info(vector_index_state);").fetchall()}
    approval_columns = {row[1] for row in connection.execute("PRAGMA table_info(approval_requests);").fetchall()}
    conversation_count = connection.execute("SELECT COUNT(*) FROM conversations;").fetchone()[0]
    message_count = connection.execute("SELECT COUNT(*) FROM messages;").fetchone()[0]
    document_count = connection.execute("SELECT COUNT(*) FROM documents;").fetchone()[0]
    version = connection.execute("PRAGMA user_version;").fetchone()[0]
    indexes = {row[1] for row in connection.execute("PRAGMA index_list(documents);").fetchall()}
    schema_version = connection.execute("SELECT version FROM schema_version LIMIT 1;").fetchone()[0]
    state = connection.execute("SELECT status, active_generation, dirty FROM vector_index_state WHERE id = 1;").fetchone()
    connection.close()

    assert DOCUMENT_COLUMNS_V2.issubset(columns)
    assert DOCUMENT_CHUNK_COLUMNS.issubset(chunk_columns)
    assert VECTOR_INDEX_STATE_COLUMNS.issubset(state_columns)
    assert {"tool_name", "arguments_json", "arguments_sha256", "nonce_sha256", "safe_summary", "execution_deadline_at", "result_message_id"}.issubset(approval_columns)
    assert conversation_count == 1
    assert message_count == 1
    assert document_count == 1
    assert version == SCHEMA_VERSION
    assert schema_version == SCHEMA_VERSION
    assert "idx_documents_sha256" in indexes
    assert state == ("empty", None, 0)
    assert check_database(settings) is True


@pytest.mark.parametrize("include_deadline", [False, True])
def test_v4_and_malformed_v5_approval_databases_migrate_to_v6(tmp_path, include_deadline) -> None:
    settings = build_settings(tmp_path)
    create_v1_database(settings.resolved_database_path)
    add_v4_approval_table(settings.resolved_database_path, include_deadline=include_deadline)
    if include_deadline:
        with sqlite3.connect(settings.resolved_database_path) as connection:
            connection.execute("UPDATE schema_version SET version = 5;")
            connection.execute("PRAGMA user_version = 5;")
            connection.commit()
    initialize_database(settings)
    with sqlite3.connect(settings.resolved_database_path) as connection:
        rows = connection.execute("SELECT id, status FROM approval_requests ORDER BY id;").fetchall()
        columns = {row[1] for row in connection.execute("PRAGMA table_info(approval_requests);").fetchall()}
        version = connection.execute("PRAGMA user_version;").fetchone()[0]
        schema_version = connection.execute("SELECT version FROM schema_version;").fetchone()[0]
        indexes = {row[1] for row in connection.execute("PRAGMA index_list(approval_requests);").fetchall()}
    assert rows == [("executed-1", "executed"), ("pending-1", "pending"), ("rejected-1", "rejected")]
    assert {"execution_deadline_at", "result_message_id"}.issubset(columns)
    assert version == 6
    assert schema_version == 6
    assert {"idx_approval_requests_status", "idx_approval_requests_expires_at"}.issubset(indexes)
    assert check_database(settings) is True


def test_approval_migration_failure_rolls_back(tmp_path, monkeypatch) -> None:
    settings = build_settings(tmp_path)
    create_v1_database(settings.resolved_database_path)
    add_v4_approval_table(settings.resolved_database_path)
    monkeypatch.setattr(database, "migrate_approval_requests_table", lambda connection: (_ for _ in ()).throw(sqlite3.OperationalError("repair failed")))
    with pytest.raises(RuntimeError):
        initialize_database(settings)
    with sqlite3.connect(settings.resolved_database_path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(approval_requests);").fetchall()}
        version = connection.execute("PRAGMA user_version;").fetchone()[0]
        schema_version = connection.execute("SELECT version FROM schema_version;").fetchone()[0]
    assert "result_message_id" not in columns
    assert version == 4
    assert schema_version == 4


def test_migration_is_idempotent(tmp_path) -> None:
    settings = build_settings(tmp_path)
    create_v1_database(settings.resolved_database_path)
    initialize_database(settings)
    initialize_database(settings)
    connection = sqlite3.connect(settings.resolved_database_path)
    version = connection.execute("PRAGMA user_version;").fetchone()[0]
    connection.close()
    assert version == SCHEMA_VERSION


@pytest.mark.parametrize(
    ("failing_target", "replacement"),
    [
        ("create_documents_v2_table", lambda connection: (_ for _ in ()).throw(sqlite3.OperationalError("create failed"))),
        ("copy_documents_rows_to_v2", lambda connection: (_ for _ in ()).throw(sqlite3.OperationalError("copy failed"))),
        ("create_document_indexes", lambda connection: (_ for _ in ()).throw(sqlite3.OperationalError("index failed"))),
    ],
)
def test_migration_failure_rolls_back(tmp_path, monkeypatch, failing_target, replacement) -> None:
    settings = build_settings(tmp_path)
    create_v1_database(settings.resolved_database_path)
    monkeypatch.setattr(database, failing_target, replacement)

    with pytest.raises(RuntimeError):
        initialize_database(settings)

    tables, version, schema_value, count = inspect_state(settings.resolved_database_path)
    assert "documents_legacy" not in tables
    assert "documents" in tables
    assert version == 1
    assert schema_value is None
    assert count == 1


def test_migration_failure_after_rename_rolls_back(tmp_path, monkeypatch) -> None:
    settings = build_settings(tmp_path)
    create_v1_database(settings.resolved_database_path)

    def broken_create(connection):
        raise sqlite3.OperationalError("after rename")

    monkeypatch.setattr(database, "create_documents_v2_table", broken_create)
    with pytest.raises(RuntimeError):
        initialize_database(settings)

    tables, version, schema_value, count = inspect_state(settings.resolved_database_path)
    assert "documents_legacy" not in tables
    assert "documents" in tables
    assert version == 1
    assert schema_value is None
    assert count == 1
