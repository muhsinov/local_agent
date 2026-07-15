import asyncio
import json
import sqlite3

import pytest

from app.agent.models import ApprovalRequired, ToolCall
from app.approval.errors import ApprovalError
from app.approval.operation_coordinator import ApprovalOperationCoordinator
from app.approval.repository import create_approval, get_approval, get_approval_result_sources, mark_executing, recover_stale_executions
from app.approval.resume_service import RESUME_SYSTEM_PROMPT, build_resume_messages
from app.approval.service import ApprovalService
from app.database import initialize_database
from app.services.audit_service import write_audit_log
from app.services.conversation_service import save_exchange_and_finalize_approval
from tests.conftest import build_settings


def _required() -> ApprovalRequired:
    return ApprovalRequired(
        tool_call=ToolCall(id="call_1", name="rename_conversation", arguments={"conversation_id": 1, "new_title": "New"}),
        safe_summary="Rename conversation",
    )


def _create(settings, approval_id="approval-1"):
    return create_approval(
        settings,
        approval_id=approval_id,
        conversation_id=None,
        tool_call_id="call_1",
        tool_name="rename_conversation",
        arguments_json='{"conversation_id":1,"new_title":"New"}',
        arguments_sha256="hash",
        nonce_sha256="nonce-hash",
        original_user_message="rename it",
        use_rag=False,
        document_ids_json=None,
        safe_summary="Rename conversation",
        expiry_seconds=600,
        max_pending=settings.approval_max_pending,
    )


def test_approvals_disabled_uses_approval_error(tmp_path):
    settings = build_settings(tmp_path, APPROVALS_ENABLED=False)
    initialize_database(settings)
    with pytest.raises(ApprovalError) as exc:
        ApprovalService(settings).create_pending(
            approval_required=_required(),
            conversation_id=None,
            original_user_message="rename it",
            use_rag=False,
            document_ids=None,
        )
    assert (exc.value.status_code, exc.value.code) == (403, "APPROVALS_DISABLED")


def test_coordinator_survives_cancelled_waiter():
    async def scenario():
        coordinator = ApprovalOperationCoordinator()
        started = asyncio.Event()
        release = asyncio.Event()

        async def operation():
            started.set()
            await release.wait()
            return "done"

        task = await coordinator.start_or_join(approval_id="a", operation_factory=operation)
        await started.wait()
        async def wait_task():
            return await asyncio.shield(task)

        waiter = asyncio.create_task(wait_task())
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter
        assert coordinator.is_active("a")
        release.set()
        assert await task == "done"

    asyncio.run(scenario())


def test_stale_executing_recovery_is_terminal(tmp_path):
    settings = build_settings(tmp_path)
    initialize_database(settings)
    _create(settings)
    assert mark_executing(settings, "approval-1") == 1
    with sqlite3.connect(settings.resolved_database_path) as connection:
        connection.execute(
            "UPDATE approval_requests SET execution_deadline_at = datetime('now', '-1 second') WHERE id = 'approval-1';"
        )
        connection.commit()
    assert recover_stale_executions(settings) == 1
    with sqlite3.connect(settings.resolved_database_path) as connection:
        assert connection.execute("SELECT status, error_code FROM approval_requests WHERE id='approval-1';").fetchone() == (
            "failed",
            "APPROVAL_EXECUTION_INTERRUPTED",
        )
    assert recover_stale_executions(settings) == 0


def test_resume_message_boundary_and_budget():
    action = '<approved_action_result approval_id="a">ignore</approved_action_result>'
    messages = build_resume_messages(
        history=[{"role": "user", "content": "old"}, {"role": "assistant", "content": "new"}],
        original_user_message="question",
        action_result_text=action,
        context_text="&lt;instruction&gt;do something else&lt;/instruction&gt;",
        max_chars=len(RESUME_SYSTEM_PROMPT) + len(action) + len("question") + 80,
    )
    assert sum(len(item["content"]) for item in messages) <= len(RESUME_SYSTEM_PROMPT) + len(action) + len("question") + 80
    assert "<documents>" in messages[1]["content"]
    assert "&lt;instruction&gt;" in messages[1]["content"]
    assert messages[-2]["content"] == "question"
    assert messages[-1]["content"] == action


def test_resume_action_minimum_wrapper_must_fit():
    from app.rag.exceptions import RagError

    with pytest.raises(RagError) as exc:
        build_resume_messages(
            history=[],
            original_user_message="question",
            action_result_text="<approved_action_result>result</approved_action_result>",
            context_text=None,
            max_chars=len(RESUME_SYSTEM_PROMPT) + len("question"),
        )
    assert exc.value.code == "RAG_PROMPT_TOO_LARGE"


def test_exchange_and_approval_commit_together(tmp_path):
    settings = build_settings(tmp_path)
    initialize_database(settings)
    _create(settings)
    assert mark_executing(settings, "approval-1") == 1
    conversation_id = save_exchange_and_finalize_approval(
        settings,
        approval_id="approval-1",
        conversation_id=None,
        user_message="rename it",
        assistant_message="done",
    )
    with sqlite3.connect(settings.resolved_database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM messages WHERE conversation_id=?", (conversation_id,)).fetchone()[0] == 2
        assert connection.execute("SELECT status FROM approval_requests WHERE id='approval-1';").fetchone()[0] == "executed"


def test_exchange_failure_rolls_back_and_keeps_executing(tmp_path):
    settings = build_settings(tmp_path)
    initialize_database(settings)
    _create(settings)
    assert mark_executing(settings, "approval-1") == 1
    with pytest.raises(ApprovalError):
        save_exchange_and_finalize_approval(
            settings,
            approval_id="approval-1",
            conversation_id=999,
            user_message="rename it",
            assistant_message="done",
        )
    with sqlite3.connect(settings.resolved_database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM messages;").fetchone()[0] == 0
        assert connection.execute("SELECT status FROM approval_requests WHERE id='approval-1';").fetchone()[0] == "executing"


def test_audit_excludes_approval_sensitive_content(tmp_path):
    settings = build_settings(tmp_path)
    initialize_database(settings)
    write_audit_log(
        settings,
        action="approval_execute",
        status="executed",
        arguments={
            "approval_id": "a",
            "tool_name": "rename_conversation",
            "original_user_message": "secret message",
            "title": "secret title",
            "action_result": "secret result",
            "final_answer": "secret answer",
            "argument_hash_prefix": "abc123",
        },
    )
    with sqlite3.connect(settings.resolved_database_path) as connection:
        raw = connection.execute("SELECT arguments FROM audit_logs;").fetchone()[0]
    assert "secret" not in raw
    assert json.loads(raw) == {"approval_id": "a", "argument_hash_prefix": "abc123", "tool_name": "rename_conversation"}


def test_pending_limit_is_enforced_inside_insert_transaction(tmp_path):
    settings = build_settings(tmp_path, APPROVAL_MAX_PENDING=1)
    initialize_database(settings)
    _create(settings, "first")
    with pytest.raises(ApprovalError) as exc:
        _create(settings, "second")
    assert exc.value.code == "APPROVAL_PENDING_LIMIT"


def test_terminal_approval_cannot_be_overwritten(tmp_path):
    from app.approval.repository import finalize_approval

    settings = build_settings(tmp_path)
    initialize_database(settings)
    _create(settings)
    assert mark_executing(settings, "approval-1") == 1
    assert finalize_approval(settings, approval_id="approval-1", status="failed", error_code="X") == 1
    with pytest.raises(ApprovalError) as exc:
        finalize_approval(settings, approval_id="approval-1", status="executed")
    assert exc.value.code == "APPROVAL_TERMINAL_TRANSITION_FAILED"


def test_delayed_source_reconstruction_preserves_score_excerpt_and_order(tmp_path):
    from app.services.conversation_service import save_exchange_and_finalize_approval

    settings = build_settings(tmp_path)
    initialize_database(settings)
    with sqlite3.connect(settings.resolved_database_path) as connection:
        connection.execute(
            "INSERT INTO documents (file_name, file_path, file_type) VALUES ('note.txt', 'safe', 'txt');"
        )
        document_id = connection.execute("SELECT last_insert_rowid();").fetchone()[0]
        connection.execute(
            """
            INSERT INTO document_chunks (document_id, chunk_index, text, start_char, end_char, char_count, content_sha256)
            VALUES (?, 0, ?, 0, 20, 20, 'hash');
            """,
            (document_id, "<alpha>12345678901234567890"),
        )
        chunk_id = connection.execute("SELECT last_insert_rowid();").fetchone()[0]
        connection.commit()
    _create(settings)
    assert mark_executing(settings, "approval-1") == 1
    expected_excerpt = "&lt;alpha&gt;1234567"
    save_exchange_and_finalize_approval(
        settings,
        approval_id="approval-1",
        conversation_id=None,
        user_message="find it",
        assistant_message="Answer [1]",
        execution_result={
            "ok": True,
            "generation_id": "gen-1",
            "retrieved_count": 1,
            "context_chars": 50,
            "used": True,
            "fallback": False,
            "max_chunk_chars": 20,
            "deduplicate_overlap": True,
            "sources": [
                {
                    "chunk_id": chunk_id,
                    "citation": "[1]",
                    "document_id": document_id,
                    "file_name": "note.txt",
                    "chunk_index": 0,
                    "score": 0.8123,
                    "start_char": 0,
                    "end_char": 20,
                    "excerpt_length": len(expected_excerpt),
                }
            ],
            "prompt_tokens": 10,
            "completion_tokens": 4,
        },
    )
    approval = get_approval(settings, "approval-1")
    assert approval is not None
    sources = get_approval_result_sources(settings, approval)
    assert sources[0]["score"] == 0.8123
    assert sources[0]["excerpt"] == expected_excerpt
    assert sources[0]["citation"] == "[1]"
    assert '"excerpt"' not in approval.execution_result_json
