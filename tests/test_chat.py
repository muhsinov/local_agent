import asyncio
import sqlite3

import pytest
from fastapi.testclient import TestClient

import app.api.chat as chat_api
import app.main as app_main
from app.llm.ollama_client import OllamaChatResult, OllamaUsage
from app.main import create_app
from app.services.conversation_service import save_exchange
from tests.conftest import (
    FakeOllamaClient,
    OllamaInvalidResponseError,
    OllamaTimeoutError,
    OllamaUnavailableError,
    build_test_app,
)


def test_chat_creates_new_conversation_and_returns_response(tmp_path) -> None:
    fake_client = FakeOllamaClient(
        chat_result=OllamaChatResult(
            content="Salom. Men shu kompyuterda ishlayotgan lokal AI assistentman.",
            usage=OllamaUsage(prompt_tokens=25, completion_tokens=42),
        )
    )
    app, settings = build_test_app(tmp_path, fake_client)

    with TestClient(app) as client:
        response = client.post("/chat", json={"message": "Salom, o'zingni tanishtir"})

    payload = response.json()
    assert response.status_code == 200
    assert payload["conversation_id"] == 1
    assert payload["model"] == settings.ollama_model
    assert payload["sources"] == []
    assert payload["tool_calls"] == []
    assert payload["usage"] == {"prompt_tokens": 25, "completion_tokens": 42}
    assert payload["rag"]["fallback"] is True


def test_chat_writes_user_and_assistant_messages_to_sqlite(tmp_path) -> None:
    app, settings = build_test_app(tmp_path, FakeOllamaClient())

    with TestClient(app) as client:
        response = client.post("/chat", json={"message": "Salom"})

    conversation_id = response.json()["conversation_id"]
    with sqlite3.connect(settings.resolved_database_path) as connection:
        rows = connection.execute(
            "SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY id;",
            (conversation_id,),
        ).fetchall()

    assert rows == [
        ("user", "Salom"),
        ("assistant", "Salom. Men lokal AI assistentman."),
    ]


def test_chat_continues_existing_conversation(tmp_path) -> None:
    fake_client = FakeOllamaClient()
    app, settings = build_test_app(tmp_path, fake_client)

    with TestClient(app):
        conversation_id = save_exchange(settings, None, "Birinchi savol", "Birinchi javob")

    with TestClient(app) as client:
        response = client.post(
            "/chat",
            json={"message": "Ikkinchi savol", "conversation_id": conversation_id},
        )

    assert response.status_code == 200
    assert response.json()["conversation_id"] == conversation_id


def test_chat_sends_recent_history_to_ollama(tmp_path) -> None:
    fake_client = FakeOllamaClient()
    app, settings = build_test_app(tmp_path, fake_client)

    with TestClient(app):
        conversation_id = save_exchange(settings, None, "Oldingi savol", "Oldingi javob")

    with TestClient(app) as client:
        response = client.post(
            "/chat",
            json={"message": "Yangi savol", "conversation_id": conversation_id},
        )

    assert response.status_code == 200
    messages = fake_client.captured_messages[-1]
    assert messages[0]["role"] == "system"
    assert messages[1:] == [
        {"role": "user", "content": "Oldingi savol"},
        {"role": "assistant", "content": "Oldingi javob"},
        {"role": "user", "content": "Yangi savol"},
    ]


def test_chat_history_limit_is_applied(tmp_path) -> None:
    fake_client = FakeOllamaClient()
    app, settings = build_test_app(tmp_path, fake_client, CHAT_HISTORY_MESSAGES=2)

    with TestClient(app):
        conversation_id = save_exchange(settings, None, "1", "a")
        save_exchange(settings, conversation_id, "2", "b")
        save_exchange(settings, conversation_id, "3", "c")

    with TestClient(app) as client:
        response = client.post(
            "/chat",
            json={"message": "4", "conversation_id": conversation_id},
        )

    assert response.status_code == 200
    messages = fake_client.captured_messages[-1]
    assert messages[1:] == [
        {"role": "user", "content": "3"},
        {"role": "assistant", "content": "c"},
        {"role": "user", "content": "4"},
    ]


def test_chat_returns_404_for_missing_conversation(tmp_path) -> None:
    app, _ = build_test_app(tmp_path, FakeOllamaClient())

    with TestClient(app) as client:
        response = client.post("/chat", json={"message": "Salom", "conversation_id": 999})

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "CONVERSATION_NOT_FOUND"


def test_chat_rejects_empty_message(tmp_path) -> None:
    app, _ = build_test_app(tmp_path, FakeOllamaClient())

    with TestClient(app) as client:
        response = client.post("/chat", json={"message": "   "})

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "VALIDATION_ERROR"


def test_chat_rejects_too_long_message(tmp_path) -> None:
    app, _ = build_test_app(tmp_path, FakeOllamaClient(), MAX_CHAT_MESSAGE_CHARS=100)

    with TestClient(app) as client:
        response = client.post("/chat", json={"message": "x" * 101})

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "VALIDATION_ERROR"


def test_chat_returns_503_when_model_is_missing(tmp_path) -> None:
    app, _ = build_test_app(tmp_path, FakeOllamaClient(models=[]))

    with TestClient(app) as client:
        response = client.post("/chat", json={"message": "Salom"})

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "OLLAMA_MODEL_NOT_FOUND"


def test_chat_returns_503_when_ollama_is_unreachable(tmp_path) -> None:
    app, _ = build_test_app(tmp_path, FakeOllamaClient(models_error=OllamaUnavailableError("offline")))

    with TestClient(app) as client:
        response = client.post("/chat", json={"message": "Salom"})

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "OLLAMA_UNAVAILABLE"


def test_chat_returns_504_when_ollama_times_out(tmp_path) -> None:
    app, _ = build_test_app(tmp_path, FakeOllamaClient(chat_error=OllamaTimeoutError("slow")))

    with TestClient(app) as client:
        response = client.post("/chat", json={"message": "Salom"})

    assert response.status_code == 504
    assert response.json()["detail"]["code"] == "OLLAMA_TIMEOUT"


def test_chat_returns_502_for_invalid_ollama_response(tmp_path) -> None:
    app, _ = build_test_app(tmp_path, FakeOllamaClient(chat_error=OllamaInvalidResponseError("bad")))

    with TestClient(app) as client:
        response = client.post("/chat", json={"message": "Salom"})

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "OLLAMA_INVALID_RESPONSE"


def test_chat_does_not_write_partial_exchange_on_error(tmp_path) -> None:
    fake_client = FakeOllamaClient(chat_error=OllamaTimeoutError("slow"))
    app, settings = build_test_app(tmp_path, fake_client)

    with TestClient(app):
        conversation_id = save_exchange(settings, None, "Eski savol", "Eski javob")

    with TestClient(app) as client:
        response = client.post(
            "/chat",
            json={"message": "Yangi savol", "conversation_id": conversation_id},
        )

    with sqlite3.connect(settings.resolved_database_path) as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM messages WHERE conversation_id = ?;",
            (conversation_id,),
        ).fetchone()[0]

    assert response.status_code == 504
    assert count == 2


def test_chat_usage_fields_can_be_null(tmp_path) -> None:
    app, _ = build_test_app(
        tmp_path,
        FakeOllamaClient(
            chat_result=OllamaChatResult(
                content="Javob",
                usage=OllamaUsage(prompt_tokens=None, completion_tokens=None),
            )
        ),
    )

    with TestClient(app) as client:
        response = client.post("/chat", json={"message": "Salom"})

    assert response.status_code == 200
    assert response.json()["usage"] == {"prompt_tokens": None, "completion_tokens": None}


def test_chat_uses_temporary_database_only(tmp_path) -> None:
    app, settings = build_test_app(tmp_path, FakeOllamaClient())

    with TestClient(app) as client:
        response = client.post("/chat", json={"message": "Salom"})

    assert response.status_code == 200
    assert settings.resolved_database_path.exists()
    assert str(settings.resolved_database_path).startswith(str(tmp_path))


def test_chat_maps_database_error_from_lookup(monkeypatch, tmp_path) -> None:
    app, _ = build_test_app(tmp_path, FakeOllamaClient())

    def broken_exists(*args, **kwargs):
        raise sqlite3.OperationalError("db down")

    monkeypatch.setattr(chat_api, "conversation_exists", broken_exists)

    with TestClient(app) as client:
        response = client.post("/chat", json={"message": "Salom", "conversation_id": 1})

    assert response.status_code == 500
    assert response.json() == {
        "detail": {
            "code": "DATABASE_ERROR",
            "message": "Lokal database operatsiyasini bajarib bo'lmadi.",
        }
    }


def test_chat_maps_database_error_from_save(monkeypatch, tmp_path) -> None:
    app, _ = build_test_app(tmp_path, FakeOllamaClient())

    def broken_save(*args, **kwargs):
        raise sqlite3.OperationalError("db down")

    monkeypatch.setattr(chat_api, "save_exchange", broken_save)

    with TestClient(app) as client:
        response = client.post("/chat", json={"message": "Salom"})

    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "DATABASE_ERROR"


def test_chat_returns_agent_busy_when_semaphore_times_out(tmp_path) -> None:
    class BlockingSemaphore:
        async def acquire(self):
            await asyncio.sleep(0.05)

        def release(self):
            pass

    app, _ = build_test_app(tmp_path, FakeOllamaClient(), CHAT_BUSY_TIMEOUT_SECONDS=1)
    app.state.chat_semaphore = BlockingSemaphore()
    app.state.settings.chat_busy_timeout_seconds = 0.001

    with TestClient(app) as client:
        response = client.post("/chat", json={"message": "Salom"})

    assert response.status_code == 429
    assert response.json() == {
        "detail": {
            "code": "AGENT_BUSY",
            "message": "Agent hozir band. Bir ozdan keyin qayta urinib ko'ring.",
        }
    }


def test_chat_releases_semaphore_after_exception(tmp_path) -> None:
    app, _ = build_test_app(tmp_path, FakeOllamaClient(chat_error=OllamaTimeoutError("slow")))

    with TestClient(app) as client:
        first = client.post("/chat", json={"message": "Salom"})
        second = client.post("/chat", json={"message": "Yana salom"})

    assert first.status_code == 504
    assert second.status_code == 504


def test_lifespan_closes_created_ollama_client_on_startup_failure(monkeypatch, tmp_path) -> None:
    fake_client = FakeOllamaClient()
    settings = build_test_app(tmp_path, FakeOllamaClient())[1]

    def fake_factory(settings):
        return fake_client

    def fail_init(settings):
        raise RuntimeError("boom")

    monkeypatch.setattr(app_main, "OllamaClient", fake_factory)
    monkeypatch.setattr(app_main, "initialize_database", fail_init)

    app = create_app(settings)
    with pytest.raises(RuntimeError):
        with TestClient(app):
            pass

    assert fake_client.closed is True


def test_lifespan_does_not_close_injected_ollama_client(tmp_path) -> None:
    fake_client = FakeOllamaClient()
    app, _ = build_test_app(tmp_path, fake_client)

    with TestClient(app):
        pass

    assert fake_client.closed is False
