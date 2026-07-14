import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path

from app.config import Settings, get_settings


SCHEMA_VERSION = 2
EXPECTED_TABLES = ("conversations", "messages", "documents", "audit_logs")
DOCUMENT_COLUMNS_V2 = {
    "id",
    "file_name",
    "file_path",
    "file_type",
    "indexed",
    "created_at",
    "size_bytes",
    "sha256",
    "status",
    "text_path",
    "char_count",
    "page_count",
    "warning_code",
    "updated_at",
}


def ensure_parent_directory(database_path: Path) -> None:
    """Create the database parent directory when needed."""

    database_path.parent.mkdir(parents=True, exist_ok=True)


def get_connection(settings: Settings | None = None) -> sqlite3.Connection:
    """Create a SQLite connection with row access by name."""

    active_settings = settings or get_settings()
    connection = sqlite3.connect(active_settings.resolved_database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON;")
    return connection


@contextmanager
def connection_scope(settings: Settings | None = None):
    """Yield a SQLite connection and always close it."""

    connection = get_connection(settings)
    try:
        yield connection
    finally:
        connection.close()


def get_schema_version(connection: sqlite3.Connection) -> int:
    """Return the SQLite PRAGMA user_version."""

    row = connection.execute("PRAGMA user_version;").fetchone()
    return int(row[0]) if row else 0


def set_schema_version(connection: sqlite3.Connection, version: int) -> None:
    """Set SQLite PRAGMA user_version."""

    connection.execute(f"PRAGMA user_version = {version};")


def create_schema_version_table(connection: sqlite3.Connection) -> None:
    """Create or update the auxiliary schema_version table."""

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER NOT NULL
        );
        """
    )
    row = connection.execute("SELECT COUNT(*) FROM schema_version;").fetchone()
    if row and row[0] == 0:
        connection.execute("INSERT INTO schema_version (version) VALUES (?);", (SCHEMA_VERSION,))
    else:
        connection.execute("UPDATE schema_version SET version = ?;", (SCHEMA_VERSION,))


def create_tables(connection: sqlite3.Connection) -> None:
    """Create the current schema tables."""

    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            title TEXT NOT NULL DEFAULT 'New conversation',
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system', 'tool')),
            content TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_name TEXT NOT NULL,
            file_path TEXT NOT NULL,
            file_type TEXT NOT NULL,
            indexed INTEGER NOT NULL DEFAULT 0 CHECK (indexed IN (0, 1)),
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

        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT NOT NULL,
            tool_name TEXT,
            arguments TEXT,
            status TEXT NOT NULL,
            execution_time_ms INTEGER CHECK (execution_time_ms IS NULL OR execution_time_ms >= 0),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_documents_sha256
        ON documents(sha256)
        WHERE sha256 IS NOT NULL;
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_documents_created_at
        ON documents(created_at DESC);
        """
    )


def fetch_existing_tables(connection: sqlite3.Connection) -> set[str]:
    """Return the existing user tables."""

    rows = connection.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table' AND name NOT LIKE 'sqlite_%';
        """
    ).fetchall()
    return {str(row["name"]) for row in rows}


def get_table_columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    """Return column names for a table."""

    rows = connection.execute(f"PRAGMA table_info({table_name});").fetchall()
    return {str(row["name"]) for row in rows}


def index_exists(connection: sqlite3.Connection, table_name: str, index_name: str) -> bool:
    """Check whether an index exists for a table."""

    rows = connection.execute(f"PRAGMA index_list({table_name});").fetchall()
    return any(str(row["name"]) == index_name for row in rows)


def create_document_indexes(connection: sqlite3.Connection) -> None:
    """Create indexes required by the documents table."""

    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_documents_sha256
        ON documents(sha256)
        WHERE sha256 IS NOT NULL;
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_documents_created_at
        ON documents(created_at DESC);
        """
    )


def migrate_documents_table_to_v2(connection: sqlite3.Connection) -> None:
    """Migrate legacy documents rows into the v2 table shape."""

    columns = get_table_columns(connection, "documents")
    if DOCUMENT_COLUMNS_V2.issubset(columns):
        create_document_indexes(connection)
        return

    connection.execute("ALTER TABLE documents RENAME TO documents_legacy;")
    connection.execute(
        """
        CREATE TABLE documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_name TEXT NOT NULL,
            file_path TEXT NOT NULL,
            file_type TEXT NOT NULL,
            indexed INTEGER NOT NULL DEFAULT 0 CHECK (indexed IN (0, 1)),
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
        """
    )
    connection.execute(
        """
        INSERT INTO documents (
            id,
            file_name,
            file_path,
            file_type,
            indexed,
            created_at,
            size_bytes,
            sha256,
            status,
            text_path,
            char_count,
            page_count,
            warning_code,
            updated_at
        )
        SELECT
            id,
            file_name,
            file_path,
            file_type,
            COALESCE(indexed, 0),
            created_at,
            0,
            NULL,
            'uploaded',
            NULL,
            0,
            NULL,
            NULL,
            created_at
        FROM documents_legacy;
        """
    )
    connection.execute("DROP TABLE documents_legacy;")
    create_document_indexes(connection)


def migrate_schema(connection: sqlite3.Connection) -> None:
    """Migrate any existing database to schema version 2."""

    existing_tables = fetch_existing_tables(connection)
    current_version = get_schema_version(connection)

    if not existing_tables:
        create_tables(connection)
        create_schema_version_table(connection)
        set_schema_version(connection, SCHEMA_VERSION)
        return

    if not set(EXPECTED_TABLES).issubset(existing_tables):
        raise RuntimeError("Mavjud database schema to'liq emas yoki kutilmagan holatda.")

    if "documents" in existing_tables:
        migrate_documents_table_to_v2(connection)

    create_schema_version_table(connection)
    set_schema_version(connection, SCHEMA_VERSION)


def initialize_database(settings: Settings | None = None) -> None:
    """Create or migrate the SQLite database."""

    active_settings = settings or get_settings()
    ensure_parent_directory(active_settings.resolved_database_path)

    try:
        with closing(get_connection(active_settings)) as connection:
            connection.execute("BEGIN;")
            try:
                migrate_schema(connection)
                connection.commit()
            except Exception:
                connection.rollback()
                raise
    except sqlite3.Error as exc:
        raise RuntimeError(f"Database initialization muvaffaqiyatsiz tugadi: {exc}") from exc


def check_database(settings: Settings | None = None) -> bool:
    """Return whether the current database is present and structurally valid."""

    active_settings = settings or get_settings()
    database_path = active_settings.resolved_database_path
    if not database_path.exists():
        return False

    try:
        with closing(get_connection(active_settings)) as connection:
            connection.execute("SELECT 1;").fetchone()
            if get_schema_version(connection) != SCHEMA_VERSION:
                return False
            if not set(EXPECTED_TABLES).issubset(fetch_existing_tables(connection)):
                return False
            if not DOCUMENT_COLUMNS_V2.issubset(get_table_columns(connection, "documents")):
                return False
            if not index_exists(connection, "documents", "idx_documents_sha256"):
                return False
            if not index_exists(connection, "documents", "idx_documents_created_at"):
                return False
        return True
    except (sqlite3.Error, RuntimeError):
        return False
