import sqlite3

from fastapi.testclient import TestClient

from app.services.conversation_service import save_exchange
from tests.conftest import FakeOllamaClient, build_test_app


class SequencedOllamaClient(FakeOllamaClient):
    def __init__(self, responses):
        super().__init__()
        self._responses = list(responses)

    async def chat(self, messages):
        self.captured_messages.append(messages)
        if not self._responses:
            raise AssertionError("unexpected extra Ollama call")
        return self._responses.pop(0)


def _response(content: str):
    return type(
        "Result",
        (),
        {"content": content, "usage": type("Usage", (), {"prompt_tokens": 1, "completion_tokens": 1})()},
    )()


def test_chat_returns_approval_without_executing_write_action(tmp_path) -> None:
    client = SequencedOllamaClient(
        [_response('{"type":"tool_call","calls":[{"id":"call_1","name":"rename_conversation","arguments":{"conversation_id":1,"new_title":"Project Alpha"}}]}')]
    )
    app, settings = build_test_app(tmp_path, client, TOOLS_ENABLED=True)

    with TestClient(app):
        conversation_id = save_exchange(settings, None, "Eski", "Javob")

    with TestClient(app) as http:
        response = http.post(
            "/chat",
            json={"message": "conversation 1 nomini Project Alpha qil", "conversation_id": conversation_id, "use_tools": True},
        )

    payload = response.json()
    assert response.status_code == 200
    assert payload["approval"]["required"] is True
    assert payload["approval"]["nonce"]
    assert payload["approval"]["tool_name"] == "rename_conversation"
    assert "arguments" not in str(payload["approval"]).lower()
    with sqlite3.connect(settings.resolved_database_path) as connection:
        title = connection.execute("SELECT title FROM conversations WHERE id = ?;", (conversation_id,)).fetchone()[0]
        message_count = connection.execute("SELECT COUNT(*) FROM messages WHERE conversation_id = ?;", (conversation_id,)).fetchone()[0]
    assert title == "Eski"
    assert message_count == 2


def test_approve_rename_executes_once_and_saves_final_exchange(tmp_path) -> None:
    client = SequencedOllamaClient(
        [
            _response('{"type":"tool_call","calls":[{"id":"call_1","name":"rename_conversation","arguments":{"conversation_id":1,"new_title":"Project Alpha"}}]}'),
            _response('{"type":"final","answer":"Nom o‘zgartirildi."}'),
        ]
    )
    app, settings = build_test_app(tmp_path, client, TOOLS_ENABLED=True)

    with TestClient(app):
        conversation_id = save_exchange(settings, None, "Eski", "Javob")

    with TestClient(app) as http:
        chat_response = http.post(
            "/chat",
            json={"message": "conversation 1 nomini Project Alpha qil", "conversation_id": conversation_id, "use_tools": True},
        )
        approval = chat_response.json()["approval"]
        approve_response = http.post(f"/approvals/{approval['approval_id']}/approve", json={"nonce": approval["nonce"]})
        repeated = http.post(f"/approvals/{approval['approval_id']}/approve", json={"nonce": approval["nonce"]})

    assert approve_response.status_code == 200
    assert approve_response.json()["status"] == "executed"
    assert repeated.status_code == 409
    assert repeated.json()["detail"]["code"] == "APPROVAL_ALREADY_USED"
    with sqlite3.connect(settings.resolved_database_path) as connection:
        title = connection.execute("SELECT title FROM conversations WHERE id = ?;", (conversation_id,)).fetchone()[0]
        rows = connection.execute("SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY id;", (conversation_id,)).fetchall()
        approval_row = connection.execute(
            "SELECT status, nonce_sha256 FROM approval_requests WHERE id = ?;",
            (approval["approval_id"],),
        ).fetchone()
    assert title == "Project Alpha"
    assert rows == [
        ("user", "Eski"),
        ("assistant", "Javob"),
        ("user", "conversation 1 nomini Project Alpha qil"),
        ("assistant", "Nom o‘zgartirildi."),
    ]
    assert approval_row[0] == "executed"
    assert approval["nonce"] not in approval_row[1]


def test_reject_keeps_conversation_unchanged(tmp_path) -> None:
    client = SequencedOllamaClient(
        [_response('{"type":"tool_call","calls":[{"id":"call_1","name":"rename_conversation","arguments":{"conversation_id":1,"new_title":"Project Alpha"}}]}')]
    )
    app, settings = build_test_app(tmp_path, client, TOOLS_ENABLED=True)

    with TestClient(app):
        conversation_id = save_exchange(settings, None, "Eski", "Javob")

    with TestClient(app) as http:
        chat_response = http.post(
            "/chat",
            json={"message": "conversation 1 nomini Project Alpha qil", "conversation_id": conversation_id, "use_tools": True},
        )
        approval = chat_response.json()["approval"]
        reject_response = http.post(f"/approvals/{approval['approval_id']}/reject", json={"nonce": approval["nonce"]})

    assert reject_response.status_code == 200
    assert reject_response.json()["status"] == "rejected"
    with sqlite3.connect(settings.resolved_database_path) as connection:
        title = connection.execute("SELECT title FROM conversations WHERE id = ?;", (conversation_id,)).fetchone()[0]
        count = connection.execute("SELECT COUNT(*) FROM messages WHERE conversation_id = ?;", (conversation_id,)).fetchone()[0]
    assert title == "Eski"
    assert count == 2


def test_approve_reject_with_invalid_nonce_is_rejected(tmp_path) -> None:
    client = SequencedOllamaClient(
        [_response('{"type":"tool_call","calls":[{"id":"call_1","name":"rename_conversation","arguments":{"conversation_id":1,"new_title":"Project Alpha"}}]}')]
    )
    app, settings = build_test_app(tmp_path, client, TOOLS_ENABLED=True)

    with TestClient(app):
        conversation_id = save_exchange(settings, None, "Eski", "Javob")

    with TestClient(app) as http:
        chat_response = http.post(
            "/chat",
            json={"message": "conversation 1 nomini Project Alpha qil", "conversation_id": conversation_id, "use_tools": True},
        )
        approval = chat_response.json()["approval"]
        response = http.post(f"/approvals/{approval['approval_id']}/approve", json={"nonce": "bad"})

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "APPROVAL_INVALID_NONCE"


def test_result_endpoint_returns_exact_persisted_assistant_message(tmp_path) -> None:
    client = SequencedOllamaClient(
        [
            _response('{"type":"tool_call","calls":[{"id":"call_1","name":"rename_conversation","arguments":{"conversation_id":1,"new_title":"Project Alpha"}}]}'),
            _response('{"type":"final","answer":"Final [9]."}'),
        ]
    )
    app, settings = build_test_app(tmp_path, client, TOOLS_ENABLED=True)

    with TestClient(app):
        conversation_id = save_exchange(settings, None, "Eski", "Javob")

    with TestClient(app) as http:
        approval = http.post(
            "/chat",
            json={"message": "conversation 1 nomini Project Alpha qil", "conversation_id": conversation_id, "use_tools": True},
        ).json()["approval"]
        approve = http.post(f"/approvals/{approval['approval_id']}/approve", json={"nonce": approval["nonce"]})
        result = http.post(f"/approvals/{approval['approval_id']}/result", json={"nonce": approval["nonce"]})

    assert approve.status_code == 200
    assert result.status_code == 200
    assert result.json()["answer"] == "Final."
    assert result.json()["conversation_id"] == conversation_id
    with sqlite3.connect(settings.resolved_database_path) as connection:
        row = connection.execute(
            "SELECT conversation_id, result_message_id, status FROM approval_requests WHERE id = ?;",
            (approval["approval_id"],),
        ).fetchone()
        message = connection.execute("SELECT role, content FROM messages WHERE id = ?;", (row[1],)).fetchone()
    assert row[0] == conversation_id
    assert row[2] == "executed"
    assert message == ("assistant", "Final.")


def test_result_endpoint_rejects_wrong_nonce(tmp_path) -> None:
    client = SequencedOllamaClient(
        [_response('{"type":"tool_call","calls":[{"id":"call_1","name":"rename_conversation","arguments":{"conversation_id":1,"new_title":"Project Alpha"}}]}')]
    )
    app, settings = build_test_app(tmp_path, client, TOOLS_ENABLED=True)
    with TestClient(app) as http:
        conversation_id = save_exchange(settings, None, "Eski", "Javob")
        approval = http.post(
            "/chat",
            json={"message": "rename", "conversation_id": conversation_id, "use_tools": True},
        ).json()["approval"]
        result = http.post(f"/approvals/{approval['approval_id']}/result", json={"nonce": "bad"})
    assert result.status_code == 403
    assert result.json()["detail"]["code"] == "APPROVAL_INVALID_NONCE"
