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
        if key
        in {
            "document_id",
            "file_type",
            "size_bytes",
            "status",
            "warning_code",
            "generation_id",
            "document_count",
            "chunk_count",
            "embedding_model",
            "embedding_dimension",
            "result_count",
            "top_k",
            "filtered_document_count",
            "execution_time_ms",
            "context_chars",
            "retrieval_ms",
            "citation_count",
            "invalid_citation_count",
            "prompt_input_chars",
            "prompt_input_limit_chars",
            "reserved_answer_chars",
            "tool_name",
            "truncated",
            "iteration",
            "error_code",
            "success",
            "call_count",
            "iterations",
            "final_status",
            "approval_id",
            "conversation_id",
            "expired",
            "argument_hash_prefix",
            "method",
            "route_template",
            "reason_code",
            "browser",
            "session_present",
            "origin_present",
            "host_category",
            "session_reused",
            "session_created",
            "request_id",
            "status_code",
            "rate_limit_group",
            "limit",
            "retry_after_seconds",
            "draining",
            "component",
        }
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
