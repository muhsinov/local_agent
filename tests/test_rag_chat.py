from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import FakeOllamaClient, build_settings


def test_chat_use_rag_false_remains_backward_compatible(tmp_path) -> None:
    settings = build_settings(tmp_path)
    app = create_app(settings)
    app.state.ollama_client = FakeOllamaClient()
    with TestClient(app) as client:
        response = client.post("/chat", json={"message": "Salom", "use_rag": False})
    assert response.status_code == 200
    payload = response.json()
    assert payload["sources"] == []
    assert payload["rag"]["enabled"] is False


def test_chat_rag_fallback_when_index_missing(tmp_path) -> None:
    settings = build_settings(tmp_path, RAG_ENABLED=True)
    app = create_app(settings)
    app.state.ollama_client = FakeOllamaClient()
    with TestClient(app) as client:
        response = client.post("/chat", json={"message": "Salom", "use_rag": True})
    assert response.status_code == 200
    assert response.json()["rag"]["fallback"] is True
