import json
import sqlite3

from app.config import Settings
from app.database import connection_scope


def write_audit_log(
    settings: Settings,
    *,
    action: str,
    status: str,
    arguments: dict,
    execution_time_ms: int | None = None,
) -> None:
    """Write a safe audit log entry without exposing raw content or paths."""

    safe_arguments = {
        key: value
        for key, value in arguments.items()
        if key in {"document_id", "file_type", "size_bytes", "status", "warning_code"}
    }
    try:
        with connection_scope(settings) as connection:
            connection.execute(
                """
                INSERT INTO audit_logs (action, arguments, status, execution_time_ms)
                VALUES (?, ?, ?, ?);
                """,
                (
                    action,
                    json.dumps(safe_arguments, ensure_ascii=False),
                    status,
                    execution_time_ms,
                ),
            )
            connection.commit()
    except sqlite3.Error:
        print("Audit log yozilmadi.")
