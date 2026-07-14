import sqlite3

from app.config import Settings
from app.database import get_connection


def conversation_exists(settings: Settings, conversation_id: int) -> bool:
    """Check whether a conversation exists."""

    with get_connection(settings) as connection:
        row = connection.execute(
            "SELECT 1 FROM conversations WHERE id = ?;",
            (conversation_id,),
        ).fetchone()
    return row is not None


def create_conversation(connection: sqlite3.Connection, title: str) -> int:
    """Insert a conversation row and return its id."""

    cursor = connection.execute(
        "INSERT INTO conversations (title) VALUES (?);",
        (title[:80],),
    )
    return int(cursor.lastrowid)


def get_recent_messages(settings: Settings, conversation_id: int, limit: int) -> list[dict[str, str]]:
    """Load the most recent user/assistant messages in chronological order."""

    if limit <= 0:
        return []

    with get_connection(settings) as connection:
        rows = connection.execute(
            """
            SELECT role, content
            FROM messages
            WHERE conversation_id = ? AND role IN ('user', 'assistant')
            ORDER BY id DESC
            LIMIT ?;
            """,
            (conversation_id, limit),
        ).fetchall()

    chronological_rows = list(reversed(rows))
    return [{"role": str(row["role"]), "content": str(row["content"])} for row in chronological_rows]


def save_exchange(
    settings: Settings,
    conversation_id: int | None,
    user_message: str,
    assistant_message: str,
) -> int:
    """Persist a user/assistant exchange in a single transaction."""

    with get_connection(settings) as connection:
        connection.execute("BEGIN;")
        try:
            active_conversation_id = conversation_id
            if active_conversation_id is None:
                active_conversation_id = create_conversation(connection, _build_conversation_title(user_message))

            connection.execute(
                """
                INSERT INTO messages (conversation_id, role, content)
                VALUES (?, ?, ?);
                """,
                (active_conversation_id, "user", user_message),
            )
            connection.execute(
                """
                INSERT INTO messages (conversation_id, role, content)
                VALUES (?, ?, ?);
                """,
                (active_conversation_id, "assistant", assistant_message),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    return int(active_conversation_id)


def _build_conversation_title(message: str) -> str:
    normalized = " ".join(message.split())
    if len(normalized) <= 80:
        return normalized
    return normalized[:77].rstrip() + "..."
