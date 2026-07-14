import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path

from app.config import Settings, get_settings


SCHEMA_VERSION = 1
EXPECTED_TABLES = ("conversations", "messages", "documents", "audit_logs")
EXPECTED_SCHEMAS = {
    "conversations": (
        "id INTEGER PRIMARY KEY AUTOINCREMENT",
        "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP",
        "title TEXT NOT NULL DEFAULT 'New conversation'",
        "updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP",
    ),
    "messages": (
        "id INTEGER PRIMARY KEY AUTOINCREMENT",
        "conversation_id INTEGER NOT NULL",
        "role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system', 'tool'))",
        "content TEXT NOT NULL",
        "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP",
        "FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE",
    ),
    "documents": (
        "id INTEGER PRIMARY KEY AUTOINCREMENT",
        "file_name TEXT NOT NULL",
        "file_path TEXT NOT NULL",
        "file_type TEXT NOT NULL",
        "indexed INTEGER NOT NULL DEFAULT 0 CHECK (indexed IN (0, 1))",
        "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP",
    ),
    "audit_logs": (
        "id INTEGER PRIMARY KEY AUTOINCREMENT",
        "action TEXT NOT NULL",
        "tool_name TEXT",
        "arguments TEXT",
        "status TEXT NOT NULL",
        "execution_time_ms INTEGER CHECK (execution_time_ms IS NULL OR execution_time_ms >= 0)",
        "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP",
    ),
}


def ensure_parent_directory(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)


def get_connection(settings: Settings | None = None) -> sqlite3.Connection:
    active_settings = settings or get_settings()
    database_path = active_settings.resolved_database_path
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON;")
    return connection


@contextmanager
def connection_scope(settings: Settings | None = None):
    """Yield a sqlite connection and always close it afterwards."""

    connection = get_connection(settings)
    try:
        yield connection
    finally:
        connection.close()


def get_schema_version(connection: sqlite3.Connection) -> int:
    row = connection.execute("PRAGMA user_version;").fetchone()
    return int(row[0]) if row else 0


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


def create_tables(connection: sqlite3.Connection) -> None:
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
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
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


def fetch_existing_tables(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table' AND name NOT LIKE 'sqlite_%';
        """
    ).fetchall()
    return {row["name"] for row in rows}


def count_rows(connection: sqlite3.Connection, table_name: str) -> int:
    row = connection.execute(f"SELECT COUNT(*) AS total FROM {table_name};").fetchone()
    return int(row["total"]) if row else 0


def table_sql_matches(connection: sqlite3.Connection, table_name: str, expected_parts: tuple[str, ...]) -> bool:
    row = connection.execute(
        """
        SELECT sql
        FROM sqlite_master
        WHERE type = 'table' AND name = ?;
        """,
        (table_name,),
    ).fetchone()
    if not row or not row["sql"]:
        return False

    sql = " ".join(str(row["sql"]).split())
    return all(part in sql for part in expected_parts)


def can_recreate_legacy_schema(connection: sqlite3.Connection, existing_tables: set[str]) -> bool:
    for table_name in existing_tables:
        if table_name == "schema_version":
            continue
        if count_rows(connection, table_name) > 0:
            return False
    return True


def recreate_schema(connection: sqlite3.Connection, existing_tables: set[str]) -> None:
    for table_name in existing_tables:
        if table_name == "schema_version":
            continue
        connection.execute(f"DROP TABLE IF EXISTS {table_name};")

    create_tables(connection)
    create_schema_version_table(connection)
    set_schema_version(connection, SCHEMA_VERSION)


def migrate_schema(connection: sqlite3.Connection) -> None:
    existing_tables = fetch_existing_tables(connection)
    current_version = get_schema_version(connection)

    if not existing_tables:
        create_tables(connection)
        create_schema_version_table(connection)
        set_schema_version(connection, SCHEMA_VERSION)
        return

    if current_version == SCHEMA_VERSION and all(
        table_sql_matches(connection, table_name, EXPECTED_SCHEMAS[table_name]) for table_name in EXPECTED_TABLES
    ):
        create_schema_version_table(connection)
        return

    relevant_tables = existing_tables.intersection(set(EXPECTED_TABLES))
    if can_recreate_legacy_schema(connection, relevant_tables):
        recreate_schema(connection, relevant_tables.union({"schema_version"}))
        return

    raise RuntimeError(
        "Mavjud database schema eski holatda va unda ma'lumot bor. "
        "Avtomatik destructive migration bajarilmadi."
    )


def initialize_database(settings: Settings | None = None) -> None:
    active_settings = settings or get_settings()
    database_path = active_settings.resolved_database_path
    ensure_parent_directory(database_path)

    try:
        with closing(get_connection(active_settings)) as connection:
            migrate_schema(connection)
            connection.commit()
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
            if not all(
                table_sql_matches(connection, table_name, EXPECTED_SCHEMAS[table_name]) for table_name in EXPECTED_TABLES
            ):
                return False
        return True
    except (sqlite3.Error, RuntimeError):
        return False
