import sqlite3

from fastapi.testclient import TestClient

from app.services.conversation_service import conversation_exists, get_recent_messages, save_exchange
from tests.conftest import FakeOllamaClient, build_test_app, build_settings


def test_save_exchange_creates_conversation_and_messages(tmp_path) -> None:
    settings = build_settings(tmp_path)
    app, _ = build_test_app(tmp_path, FakeOllamaClient())

    with TestClient(app):
        conversation_id = save_exchange(
            settings=settings,
            conversation_id=None,
            user_message="Bu yangi conversation uchun juda uzun sarlavha bo'lishi mumkin, shuning uchun uni kesish kerak.",
            assistant_message="Javob saqlandi.",
        )

    assert conversation_exists(settings, conversation_id)

    with sqlite3.connect(settings.resolved_database_path) as connection:
        title = connection.execute(
            "SELECT title FROM conversations WHERE id = ?;",
            (conversation_id,),
        ).fetchone()[0]
        message_count = connection.execute(
            "SELECT COUNT(*) FROM messages WHERE conversation_id = ?;",
            (conversation_id,),
        ).fetchone()[0]

    assert len(title) <= 80
    assert message_count == 2


def test_get_recent_messages_returns_chronological_history(tmp_path) -> None:
    settings = build_settings(tmp_path)
    app, _ = build_test_app(tmp_path, FakeOllamaClient())

    with TestClient(app):
        conversation_id = save_exchange(settings, None, "Birinchi savol", "Birinchi javob")
        save_exchange(settings, conversation_id, "Ikkinchi savol", "Ikkinchi javob")

    history = get_recent_messages(settings, conversation_id, 4)

    assert history == [
        {"role": "user", "content": "Birinchi savol"},
        {"role": "assistant", "content": "Birinchi javob"},
        {"role": "user", "content": "Ikkinchi savol"},
        {"role": "assistant", "content": "Ikkinchi javob"},
    ]


def test_get_recent_messages_respects_limit(tmp_path) -> None:
    settings = build_settings(tmp_path)
    app, _ = build_test_app(tmp_path, FakeOllamaClient())

    with TestClient(app):
        conversation_id = save_exchange(settings, None, "1", "a")
        save_exchange(settings, conversation_id, "2", "b")
        save_exchange(settings, conversation_id, "3", "c")

    history = get_recent_messages(settings, conversation_id, 2)

    assert history == [
        {"role": "user", "content": "3"},
        {"role": "assistant", "content": "c"},
    ]
