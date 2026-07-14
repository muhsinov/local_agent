import sqlite3

from app.database import DOCUMENT_COLUMNS_V2, SCHEMA_VERSION, initialize_database
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


def test_version_1_database_migrates_to_v2(tmp_path) -> None:
    settings = build_settings(tmp_path)
    create_v1_database(settings.resolved_database_path)
    initialize_database(settings)

    connection = sqlite3.connect(settings.resolved_database_path)
    columns = {row[1] for row in connection.execute("PRAGMA table_info(documents);").fetchall()}
    conversation_count = connection.execute("SELECT COUNT(*) FROM conversations;").fetchone()[0]
    message_count = connection.execute("SELECT COUNT(*) FROM messages;").fetchone()[0]
    document_count = connection.execute("SELECT COUNT(*) FROM documents;").fetchone()[0]
    version = connection.execute("PRAGMA user_version;").fetchone()[0]
    indexes = {row[1] for row in connection.execute("PRAGMA index_list(documents);").fetchall()}
    connection.close()

    assert DOCUMENT_COLUMNS_V2.issubset(columns)
    assert conversation_count == 1
    assert message_count == 1
    assert document_count == 1
    assert version == SCHEMA_VERSION
    assert "idx_documents_sha256" in indexes


def test_migration_is_idempotent(tmp_path) -> None:
    settings = build_settings(tmp_path)
    create_v1_database(settings.resolved_database_path)
    initialize_database(settings)
    initialize_database(settings)
    connection = sqlite3.connect(settings.resolved_database_path)
    version = connection.execute("PRAGMA user_version;").fetchone()[0]
    connection.close()
    assert version == SCHEMA_VERSION
