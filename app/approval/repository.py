import json
import sqlite3

from app.approval.models import ApprovalRecord, ApprovalRequest
from app.database import connection_scope


def _row_to_record(row: sqlite3.Row) -> ApprovalRecord:
    return ApprovalRecord(
        id=str(row["id"]),
        conversation_id=int(row["conversation_id"]) if row["conversation_id"] is not None else None,
        tool_call_id=str(row["tool_call_id"]),
        tool_name=str(row["tool_name"]),
        arguments_json=str(row["arguments_json"]),
        arguments_sha256=str(row["arguments_sha256"]),
        nonce_sha256=str(row["nonce_sha256"]),
        original_user_message=str(row["original_user_message"]),
        use_rag=bool(row["use_rag"]),
        document_ids_json=str(row["document_ids_json"]) if row["document_ids_json"] is not None else None,
        status=str(row["status"]),
        safe_summary=str(row["safe_summary"]),
        created_at=str(row["created_at"]),
        expires_at=str(row["expires_at"]),
        executing_at=str(row["executing_at"]) if row["executing_at"] is not None else None,
        completed_at=str(row["completed_at"]) if row["completed_at"] is not None else None,
        error_code=str(row["error_code"]) if row["error_code"] is not None else None,
        execution_result_json=str(row["execution_result_json"]) if row["execution_result_json"] is not None else None,
    )


def expire_pending_approvals(settings) -> int:
    with connection_scope(settings) as connection:
        cursor = connection.execute(
            """
            UPDATE approval_requests
            SET status = 'expired',
                completed_at = CURRENT_TIMESTAMP
            WHERE status = 'pending'
              AND expires_at <= CURRENT_TIMESTAMP;
            """
        )
        connection.commit()
        return int(cursor.rowcount)


def count_pending_approvals(settings) -> int:
    with connection_scope(settings) as connection:
        row = connection.execute("SELECT COUNT(*) FROM approval_requests WHERE status = 'pending';").fetchone()
    return int(row[0]) if row else 0


def create_approval(
    settings,
    *,
    approval_id: str,
    conversation_id: int | None,
    tool_call_id: str,
    tool_name: str,
    arguments_json: str,
    arguments_sha256: str,
    nonce_sha256: str,
    original_user_message: str,
    use_rag: bool,
    document_ids_json: str | None,
    safe_summary: str,
    expiry_seconds: int,
) -> ApprovalRequest:
    with connection_scope(settings) as connection:
        connection.execute("BEGIN;")
        try:
            connection.execute(
                """
                INSERT INTO approval_requests (
                    id,
                    conversation_id,
                    tool_call_id,
                    tool_name,
                    arguments_json,
                    arguments_sha256,
                    nonce_sha256,
                    original_user_message,
                    use_rag,
                    document_ids_json,
                    status,
                    safe_summary,
                    expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, datetime('now', '+' || ? || ' seconds'));
                """,
                (
                    approval_id,
                    conversation_id,
                    tool_call_id,
                    tool_name,
                    arguments_json,
                    arguments_sha256,
                    nonce_sha256,
                    original_user_message,
                    int(use_rag),
                    document_ids_json,
                    safe_summary,
                    expiry_seconds,
                ),
            )
            row = connection.execute(
                """
                SELECT id, conversation_id, tool_call_id, tool_name, arguments_sha256, status, safe_summary, created_at, expires_at
                FROM approval_requests
                WHERE id = ?;
                """,
                (approval_id,),
            ).fetchone()
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return ApprovalRequest(
        id=str(row["id"]),
        conversation_id=int(row["conversation_id"]) if row["conversation_id"] is not None else None,
        tool_call_id=str(row["tool_call_id"]),
        tool_name=str(row["tool_name"]),
        arguments_sha256=str(row["arguments_sha256"]),
        status=str(row["status"]),
        safe_summary=str(row["safe_summary"]),
        created_at=str(row["created_at"]),
        expires_at=str(row["expires_at"]),
    )


def get_approval(settings, approval_id: str) -> ApprovalRecord | None:
    with connection_scope(settings) as connection:
        row = connection.execute("SELECT * FROM approval_requests WHERE id = ?;", (approval_id,)).fetchone()
    return _row_to_record(row) if row else None


def mark_executing(settings, approval_id: str) -> int:
    with connection_scope(settings) as connection:
        cursor = connection.execute(
            """
            UPDATE approval_requests
            SET status = 'executing',
                executing_at = CURRENT_TIMESTAMP
            WHERE id = ?
              AND status = 'pending'
              AND expires_at > CURRENT_TIMESTAMP;
            """,
            (approval_id,),
        )
        connection.commit()
        return int(cursor.rowcount)


def mark_rejected(settings, approval_id: str) -> int:
    with connection_scope(settings) as connection:
        cursor = connection.execute(
            """
            UPDATE approval_requests
            SET status = 'rejected',
                completed_at = CURRENT_TIMESTAMP
            WHERE id = ?
              AND status = 'pending'
              AND expires_at > CURRENT_TIMESTAMP;
            """,
            (approval_id,),
        )
        connection.commit()
        return int(cursor.rowcount)


def finalize_approval(
    settings,
    *,
    approval_id: str,
    status: str,
    error_code: str | None = None,
    execution_result: dict | None = None,
) -> None:
    payload = json.dumps(execution_result, ensure_ascii=False) if execution_result is not None else None
    with connection_scope(settings) as connection:
        connection.execute(
            """
            UPDATE approval_requests
            SET status = ?,
                completed_at = CURRENT_TIMESTAMP,
                error_code = ?,
                execution_result_json = ?
            WHERE id = ?;
            """,
            (status, error_code, payload, approval_id),
        )
        connection.commit()
