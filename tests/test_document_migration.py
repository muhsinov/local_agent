import sqlite3

import pytest

import app.database as database
from app.database import DOCUMENT_CHUNK_COLUMNS, DOCUMENT_COLUMNS_V2, SCHEMA_VERSION, VECTOR_INDEX_STATE_COLUMNS, initialize_database
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
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
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


def test_version_1_database_migrates_to_v3(tmp_path) -> None:
    settings = build_settings(tmp_path)
    create_v1_database(settings.resolved_database_path)
    initialize_database(settings)

    connection = sqlite3.connect(settings.resolved_database_path)
    columns = {row[1] for row in connection.execute("PRAGMA table_info(documents);").fetchall()}
    chunk_columns = {row[1] for row in connection.execute("PRAGMA table_info(document_chunks);").fetchall()}
    state_columns = {row[1] for row in connection.execute("PRAGMA table_info(vector_index_state);").fetchall()}
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
    assert conversation_count == 1
    assert message_count == 1
    assert document_count == 1
    assert version == SCHEMA_VERSION
    assert schema_version == SCHEMA_VERSION
    assert "idx_documents_sha256" in indexes
    assert state == ("empty", None, 0)


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
