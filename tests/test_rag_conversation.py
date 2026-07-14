import sqlite3

from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import FakeOllamaClient, build_settings


def test_chat_does_not_store_rag_context_messages(tmp_path) -> None:
    settings = build_settings(tmp_path)
    app = create_app(settings)
    app.state.ollama_client = FakeOllamaClient()
    with TestClient(app) as client:
        response = client.post("/chat", json={"message": "Salom", "use_rag": False})
    conversation_id = response.json()["conversation_id"]
    with sqlite3.connect(settings.resolved_database_path) as connection:
        rows = connection.execute("SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY id;", (conversation_id,)).fetchall()
    assert len(rows) == 2
    assert rows[0][0] == "user"
    assert rows[1][0] == "assistant"
