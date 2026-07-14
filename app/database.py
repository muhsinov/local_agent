import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path

from app.config import Settings, get_settings


SCHEMA_VERSION = 3
EXPECTED_TABLES = (
    "conversations",
    "messages",
    "documents",
    "audit_logs",
    "document_chunks",
    "vector_index_state",
    "schema_version",
)
CONVERSATION_COLUMNS = {"id", "created_at", "title", "updated_at"}
MESSAGE_COLUMNS = {"id", "conversation_id", "role", "content", "created_at"}
AUDIT_LOG_COLUMNS = {"id", "action", "tool_name", "arguments", "status", "execution_time_ms", "created_at"}
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
DOCUMENT_CHUNK_COLUMNS = {
    "id",
    "document_id",
    "chunk_index",
    "text",
    "start_char",
    "end_char",
    "char_count",
    "content_sha256",
    "created_at",
}
VECTOR_INDEX_STATE_COLUMNS = {
    "id",
    "active_generation",
    "status",
    "embedding_model",
    "embedding_dimension",
    "chunk_count",
    "document_count",
    "dirty",
    "updated_at",
}


def ensure_parent_directory(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)


def get_connection(settings: Settings | None = None) -> sqlite3.Connection:
    active_settings = settings or get_settings()
    connection = sqlite3.connect(active_settings.resolved_database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON;")
    return connection


@contextmanager
def connection_scope(settings: Settings | None = None):
    connection = get_connection(settings)
    try:
        yield connection
    finally:
        connection.close()


def get_schema_version(connection: sqlite3.Connection) -> int:
    row = connection.execute("PRAGMA user_version;").fetchone()
    return int(row[0]) if row else 0


def get_schema_version_table_value(connection: sqlite3.Connection) -> int | None:
    if "schema_version" not in fetch_existing_tables(connection):
        return None
    row = connection.execute("SELECT version FROM schema_version LIMIT 1;").fetchone()
    return int(row[0]) if row else None


def set_schema_version(connection: sqlite3.Connection, version: int) -> None:
    connection.execute(f"PRAGMA user_version = {version};")


def create_schema_version_table(connection: sqlite3.Connection) -> None:
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


def create_document_indexes(connection: sqlite3.Connection) -> None:
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


def create_document_chunk_tables(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS document_chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL,
            chunk_index INTEGER NOT NULL,
            text TEXT NOT NULL,
            start_char INTEGER NOT NULL CHECK(start_char >= 0),
            end_char INTEGER NOT NULL CHECK(end_char > start_char),
            char_count INTEGER NOT NULL CHECK(char_count > 0),
            content_sha256 TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE,
            UNIQUE(document_id, chunk_index)
        );
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_document_chunks_document
        ON document_chunks(document_id, chunk_index);
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_document_chunks_sha256
        ON document_chunks(content_sha256);
        """
    )


def ensure_vector_index_state_row(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS vector_index_state (
            id INTEGER PRIMARY KEY CHECK(id = 1),
            active_generation TEXT,
            status TEXT NOT NULL DEFAULT 'empty' CHECK(status IN ('empty', 'ready', 'error')),
            embedding_model TEXT,
            embedding_dimension INTEGER,
            chunk_count INTEGER NOT NULL DEFAULT 0,
            document_count INTEGER NOT NULL DEFAULT 0,
            dirty INTEGER NOT NULL DEFAULT 0 CHECK(dirty IN (0, 1)),
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    row = connection.execute("SELECT COUNT(*) FROM vector_index_state WHERE id = 1;").fetchone()
    if row and row[0] == 0:
        connection.execute(
            """
            INSERT INTO vector_index_state (
                id,
                active_generation,
                status,
                embedding_model,
                embedding_dimension,
                chunk_count,
                document_count,
                dirty
            ) VALUES (1, NULL, 'empty', NULL, NULL, 0, 0, 0);
            """
        )


def create_tables(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            title TEXT NOT NULL DEFAULT 'New conversation',
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system', 'tool')),
            content TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
        );
        """
    )
    connection.execute(
        """
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
        """
    )
    connection.execute(
        """
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
    create_document_indexes(connection)
    create_document_chunk_tables(connection)
    ensure_vector_index_state_row(connection)
    create_schema_version_table(connection)


def fetch_existing_tables(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table' AND name NOT LIKE 'sqlite_%';
        """
    ).fetchall()
    return {str(row["name"]) for row in rows}


def get_table_columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    rows = connection.execute(f"PRAGMA table_info({table_name});").fetchall()
    return {str(row["name"]) for row in rows}


def index_exists(connection: sqlite3.Connection, table_name: str, index_name: str) -> bool:
    rows = connection.execute(f"PRAGMA index_list({table_name});").fetchall()
    return any(str(row["name"]) == index_name for row in rows)


def messages_foreign_key_valid(connection: sqlite3.Connection) -> bool:
    rows = connection.execute("PRAGMA foreign_key_list(messages);").fetchall()
    for row in rows:
        if (
            str(row["table"]) == "conversations"
            and str(row["from"]) == "conversation_id"
            and str(row["to"]) == "id"
            and str(row["on_delete"]).upper() == "CASCADE"
        ):
            return True
    return False


def document_chunks_foreign_key_valid(connection: sqlite3.Connection) -> bool:
    rows = connection.execute("PRAGMA foreign_key_list(document_chunks);").fetchall()
    for row in rows:
        if (
            str(row["table"]) == "documents"
            and str(row["from"]) == "document_id"
            and str(row["to"]) == "id"
            and str(row["on_delete"]).upper() == "CASCADE"
        ):
            return True
    return False


def create_documents_v2_table(connection: sqlite3.Connection) -> None:
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


def copy_documents_rows_to_v2(connection: sqlite3.Connection) -> None:
    columns = get_table_columns(connection, "documents_legacy")
    size_bytes = "COALESCE(size_bytes, 0)" if "size_bytes" in columns else "0"
    sha256 = "sha256" if "sha256" in columns else "NULL"
    status = "COALESCE(status, 'uploaded')" if "status" in columns else "'uploaded'"
    text_path = "text_path" if "text_path" in columns else "NULL"
    char_count = "COALESCE(char_count, 0)" if "char_count" in columns else "0"
    page_count = "page_count" if "page_count" in columns else "NULL"
    warning_code = "warning_code" if "warning_code" in columns else "NULL"
    updated_at = "COALESCE(updated_at, created_at)" if "updated_at" in columns else "created_at"
    connection.execute(
        f"""
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
            {size_bytes},
            {sha256},
            {status},
            {text_path},
            {char_count},
            {page_count},
            {warning_code},
            {updated_at}
        FROM documents_legacy;
        """
    )


def migrate_documents_table_to_v2(connection: sqlite3.Connection) -> None:
    columns = get_table_columns(connection, "documents")
    if DOCUMENT_COLUMNS_V2.issubset(columns):
        create_document_indexes(connection)
        return
    connection.execute("ALTER TABLE documents RENAME TO documents_legacy;")
    create_documents_v2_table(connection)
    copy_documents_rows_to_v2(connection)
    connection.execute("DROP TABLE documents_legacy;")
    create_document_indexes(connection)


def migrate_schema(connection: sqlite3.Connection) -> None:
    existing_tables = fetch_existing_tables(connection)
    if not existing_tables:
        create_tables(connection)
        set_schema_version(connection, SCHEMA_VERSION)
        return

    if not {"conversations", "messages", "documents", "audit_logs"}.issubset(existing_tables):
        raise RuntimeError("Mavjud database schema to'liq emas yoki kutilmagan holatda.")

    migrate_documents_table_to_v2(connection)
    create_document_chunk_tables(connection)
    ensure_vector_index_state_row(connection)
    create_schema_version_table(connection)
    set_schema_version(connection, SCHEMA_VERSION)


def initialize_database(settings: Settings | None = None) -> None:
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
    active_settings = settings or get_settings()
    database_path = active_settings.resolved_database_path
    if not database_path.exists():
        return False

    try:
        with closing(get_connection(active_settings)) as connection:
            connection.execute("SELECT 1;").fetchone()
            if get_schema_version(connection) != SCHEMA_VERSION:
                return False
            if get_schema_version_table_value(connection) != SCHEMA_VERSION:
                return False
            existing_tables = fetch_existing_tables(connection)
            if not set(EXPECTED_TABLES).issubset(existing_tables):
                return False
            if not CONVERSATION_COLUMNS.issubset(get_table_columns(connection, "conversations")):
                return False
            if not MESSAGE_COLUMNS.issubset(get_table_columns(connection, "messages")):
                return False
            if not DOCUMENT_COLUMNS_V2.issubset(get_table_columns(connection, "documents")):
                return False
            if not AUDIT_LOG_COLUMNS.issubset(get_table_columns(connection, "audit_logs")):
                return False
            if not DOCUMENT_CHUNK_COLUMNS.issubset(get_table_columns(connection, "document_chunks")):
                return False
            if not VECTOR_INDEX_STATE_COLUMNS.issubset(get_table_columns(connection, "vector_index_state")):
                return False
            if not messages_foreign_key_valid(connection):
                return False
            if not document_chunks_foreign_key_valid(connection):
                return False
            if not index_exists(connection, "documents", "idx_documents_sha256"):
                return False
            if not index_exists(connection, "documents", "idx_documents_created_at"):
                return False
            if not index_exists(connection, "document_chunks", "idx_document_chunks_document"):
                return False
            if not index_exists(connection, "document_chunks", "idx_document_chunks_sha256"):
                return False
            state_row = connection.execute("SELECT COUNT(*) FROM vector_index_state WHERE id = 1;").fetchone()
            if not state_row or int(state_row[0]) != 1:
                return False
        return True
    except (sqlite3.Error, RuntimeError):
        return False
