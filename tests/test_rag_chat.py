import sqlite3

from fastapi.testclient import TestClient

import app.api.chat as chat_api
from app.main import create_app
from app.rag.models import RagContext, RagPreparationResult, RagSource
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


def test_chat_returns_prompt_too_large_before_ollama(monkeypatch, tmp_path) -> None:
    settings = build_settings(tmp_path, RAG_ENABLED=True, RAG_PROMPT_MAX_CHARS=4000, RAG_RESERVED_ANSWER_TOKENS=512)
    fake_client = FakeOllamaClient()
    app = create_app(settings)
    app.state.ollama_client = fake_client

    async def oversized_prepare(self, **kwargs):
        return RagPreparationResult(
            enabled=True,
            used=True,
            fallback=False,
            context=RagContext(
                context_text="x" * 5000,
                sources=[
                    RagSource(
                        citation="[1]",
                        chunk_id=1,
                        document_id=1,
                        file_name="doc.txt",
                        chunk_index=1,
                        score=0.9,
                        start_char=0,
                        end_char=10,
                        excerpt="x" * 50,
                    )
                ],
                generation_id="gen",
                retrieved_count=1,
                context_chars=5000,
            ),
        )

    monkeypatch.setattr(chat_api.RagService, "prepare", oversized_prepare)
    with TestClient(app) as client:
        response = client.post("/chat", json={"message": "Salom", "use_rag": True})

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "RAG_PROMPT_TOO_LARGE"
    assert fake_client.captured_messages == []
    with sqlite3.connect(settings.resolved_database_path) as connection:
        count = connection.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    assert count == 0


def test_non_rag_chat_respects_answer_reserve(monkeypatch, tmp_path) -> None:
    settings = build_settings(tmp_path, RAG_ENABLED=False, RAG_PROMPT_MAX_CHARS=2200, RAG_RESERVED_ANSWER_TOKENS=512)
    fake_client = FakeOllamaClient()
    app = create_app(settings)
    app.state.ollama_client = fake_client

    with TestClient(app) as client:
        response = client.post("/chat", json={"message": "Salom", "use_rag": False})

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "RAG_PROMPT_TOO_LARGE"
    assert fake_client.captured_messages == []


def test_chat_response_sources_match_prompt_context(monkeypatch, tmp_path) -> None:
    settings = build_settings(tmp_path, RAG_ENABLED=True)
    fake_client = FakeOllamaClient()
    app = create_app(settings)
    app.state.ollama_client = fake_client
    source = RagSource(
        citation="[1]",
        chunk_id=1,
        document_id=1,
        file_name="doc.txt",
        chunk_index=1,
        score=0.9,
        start_char=0,
        end_char=10,
        excerpt="dalil",
    )

    async def prepared(self, **kwargs):
        return RagPreparationResult(
            enabled=True,
            used=True,
            fallback=False,
            context=RagContext(
                context_text="[1]\nFile: doc.txt\nChunk: 1\nContent:\ndalil",
                sources=[source],
                generation_id="gen",
                retrieved_count=1,
                context_chars=len("[1]\nFile: doc.txt\nChunk: 1\nContent:\ndalil"),
            ),
        )

    monkeypatch.setattr(chat_api.RagService, "prepare", prepared)
    with TestClient(app) as client:
        response = client.post("/chat", json={"message": "Savol", "use_rag": True})

    assert response.status_code == 200
    payload = response.json()
    assert payload["sources"] == [
        {
            "citation": "[1]",
            "chunk_id": 1,
            "document_id": 1,
            "file_name": "doc.txt",
            "chunk_index": 1,
            "score": 0.9,
            "start_char": 0,
            "end_char": 10,
            "excerpt": "dalil",
        }
    ]
    assert "[1]\nFile: doc.txt\nChunk: 1\nContent:\ndalil" in fake_client.captured_messages[-1][1]["content"]
