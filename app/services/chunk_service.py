import sqlite3

from app.config import Settings
from app.database import connection_scope
from app.rag.models import RetrievedChunk, TextChunk


def replace_all_chunks(connection: sqlite3.Connection, chunks: list[TextChunk]) -> list[int]:
    connection.execute("DELETE FROM document_chunks;")
    chunk_ids: list[int] = []
    for chunk in chunks:
        cursor = connection.execute(
            """
            INSERT INTO document_chunks (
                document_id,
                chunk_index,
                text,
                start_char,
                end_char,
                char_count,
                content_sha256
            ) VALUES (?, ?, ?, ?, ?, ?, ?);
            """,
            (
                chunk.document_id,
                chunk.chunk_index,
                chunk.text,
                chunk.start_char,
                chunk.end_char,
                chunk.char_count,
                chunk.content_sha256,
            ),
        )
        chunk_ids.append(int(cursor.lastrowid))
    return chunk_ids


def get_chunks_by_ids(settings: Settings, chunk_ids: list[int]) -> dict[int, RetrievedChunk]:
    if not chunk_ids:
        return {}
    placeholders = ",".join("?" for _ in chunk_ids)
    with connection_scope(settings) as connection:
        rows = connection.execute(
            f"""
            SELECT
                c.id,
                c.document_id,
                d.file_name,
                c.chunk_index,
                c.text,
                c.start_char,
                c.end_char
            FROM document_chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE c.id IN ({placeholders});
            """,
            tuple(chunk_ids),
        ).fetchall()
    return {
        int(row["id"]): RetrievedChunk(
            chunk_id=int(row["id"]),
            document_id=int(row["document_id"]),
            file_name=str(row["file_name"]),
            chunk_index=int(row["chunk_index"]),
            text=str(row["text"]),
            score=0.0,
            start_char=int(row["start_char"]),
            end_char=int(row["end_char"]),
        )
        for row in rows
    }


def count_chunks(settings: Settings) -> int:
    with connection_scope(settings) as connection:
        row = connection.execute("SELECT COUNT(*) FROM document_chunks;").fetchone()
    return int(row[0]) if row else 0


def clear_chunks(connection: sqlite3.Connection) -> None:
    connection.execute("DELETE FROM document_chunks;")
