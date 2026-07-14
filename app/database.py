import sqlite3
from contextlib import closing
from pathlib import Path

from app.config import Settings, get_settings


def ensure_parent_directory(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)


def get_connection(settings: Settings | None = None) -> sqlite3.Connection:
    active_settings = settings or get_settings()
    database_path = active_settings.resolved_database_path
    ensure_parent_directory(database_path)
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON;")
    return connection


def initialize_database(settings: Settings | None = None) -> None:
    active_settings = settings or get_settings()
    database_path = active_settings.resolved_database_path
    ensure_parent_directory(database_path)

    with closing(get_connection(active_settings)) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL DEFAULT 'New conversation',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER,
                filename TEXT NOT NULL,
                file_path TEXT NOT NULL,
                mime_type TEXT,
                status TEXT NOT NULL DEFAULT 'uploaded',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                details TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        connection.commit()


def check_database(settings: Settings | None = None) -> bool:
    try:
        with closing(get_connection(settings)) as connection:
            connection.execute("SELECT 1;").fetchone()
        return True
    except sqlite3.Error:
        return False
