import sqlite3

from app.api.errors import ApiError
from app.config import Settings
from app.database import connection_scope
from app.documents.models import DocumentRecord


def _record_from_row(row: sqlite3.Row) -> DocumentRecord:
    return DocumentRecord(
        id=int(row["id"]),
        file_name=str(row["file_name"]),
        file_path=str(row["file_path"]),
        file_type=str(row["file_type"]),
        size_bytes=int(row["size_bytes"]),
        sha256=str(row["sha256"]) if row["sha256"] is not None else None,
        status=str(row["status"]),
        text_path=str(row["text_path"]) if row["text_path"] is not None else None,
        char_count=int(row["char_count"]),
        page_count=int(row["page_count"]) if row["page_count"] is not None else None,
        warning_code=str(row["warning_code"]) if row["warning_code"] is not None else None,
        indexed=bool(row["indexed"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def find_document_by_sha256(settings: Settings, sha256: str) -> DocumentRecord | None:
    """Return the document that already owns the SHA-256 hash, if any."""

    with connection_scope(settings) as connection:
        row = connection.execute(
            "SELECT * FROM documents WHERE sha256 = ?;",
            (sha256,),
        ).fetchone()
    return _record_from_row(row) if row else None


def _raise_duplicate_document(settings: Settings, sha256: str) -> None:
    duplicate = find_document_by_sha256(settings, sha256)
    if duplicate is not None:
        raise ApiError(
            409,
            "DOCUMENT_DUPLICATE",
            "Bu hujjat avval yuklangan.",
            extra={"existing_document_id": duplicate.id},
        )


def _mark_vector_index_dirty(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        UPDATE vector_index_state
        SET dirty = CASE
            WHEN active_generation IS NOT NULL OR status = 'ready' OR chunk_count > 0 THEN 1
            ELSE dirty
        END,
        updated_at = CURRENT_TIMESTAMP
        WHERE id = 1;
        """
    )


def create_document(
    settings: Settings,
    *,
    file_name: str,
    file_path: str,
    file_type: str,
    size_bytes: int,
    sha256: str,
    status: str,
    text_path: str | None,
    char_count: int,
    page_count: int | None,
    warning_code: str | None,
) -> DocumentRecord:
    """Create a document row and return the created record."""

    try:
        with connection_scope(settings) as connection:
            connection.execute("BEGIN;")
            try:
                cursor = connection.execute(
                    """
                    INSERT INTO documents (
                        file_name,
                        file_path,
                        file_type,
                        size_bytes,
                        sha256,
                        status,
                        text_path,
                        char_count,
                        page_count,
                        warning_code
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        file_name,
                        file_path,
                        file_type,
                        size_bytes,
                        sha256,
                        status,
                        text_path,
                        char_count,
                        page_count,
                        warning_code,
                    ),
                )
                document_id = int(cursor.lastrowid)
                _mark_vector_index_dirty(connection)
                row = connection.execute("SELECT * FROM documents WHERE id = ?;", (document_id,)).fetchone()
                if row is None:
                    raise ApiError(500, "DATABASE_ERROR", "Lokal database operatsiyasini bajarib bo'lmadi.")
                record = _record_from_row(row)
                connection.commit()
                return record
            except Exception:
                connection.rollback()
                raise
    except sqlite3.IntegrityError as exc:
        message = str(exc).lower()
        if "documents.sha256" in message or "idx_documents_sha256" in message or "unique constraint failed" in message:
            _raise_duplicate_document(settings, sha256)
        raise


def get_document(settings: Settings, document_id: int) -> DocumentRecord | None:
    """Load a single document record by id."""

    with connection_scope(settings) as connection:
        row = connection.execute("SELECT * FROM documents WHERE id = ?;", (document_id,)).fetchone()
    return _record_from_row(row) if row else None


def list_documents(settings: Settings, limit: int, offset: int) -> list[DocumentRecord]:
    """Return paginated documents ordered by most recent first."""

    if offset < 0:
        raise ApiError(422, "VALIDATION_ERROR", "Offset manfiy bo'lishi mumkin emas.")
    safe_limit = min(limit, settings.max_document_list_limit)
    with connection_scope(settings) as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM documents
            ORDER BY created_at DESC, id DESC
            LIMIT ? OFFSET ?;
            """,
            (safe_limit, offset),
        ).fetchall()
    return [_record_from_row(row) for row in rows]


def delete_document_record(connection: sqlite3.Connection, document_id: int) -> bool:
    """Delete a document row inside an existing transaction."""

    cursor = connection.execute("DELETE FROM documents WHERE id = ?;", (document_id,))
    if cursor.rowcount > 0:
        _mark_vector_index_dirty(connection)
    return cursor.rowcount > 0
