from fastapi.testclient import TestClient

from app.database import initialize_database
from app.main import create_app
from app.services.document_service import create_document
from tests.conftest import FakeEmbeddingModel, FakeOllamaClient, build_settings


def _seed_document(settings) -> int:
    settings.resolved_upload_directory.mkdir(parents=True, exist_ok=True)
    settings.resolved_extracted_text_directory.mkdir(parents=True, exist_ok=True)
    (settings.resolved_upload_directory / "doc.txt").write_text("agent security matni", encoding="utf-8")
    (settings.resolved_extracted_text_directory / "doc.txt").write_text("agent security matni", encoding="utf-8")
    document = create_document(
        settings,
        file_name="doc.txt",
        file_path="doc.txt",
        file_type="txt",
        size_bytes=20,
        sha256="sha-doc",
        status="ready",
        text_path="doc.txt",
        char_count=20,
        page_count=None,
        warning_code=None,
    )
    return document.id


def test_vector_api_rebuild_status_and_search(monkeypatch, tmp_path) -> None:
    settings = build_settings(tmp_path, EMBEDDING_DIMENSION=64)
    initialize_database(settings)
    document_id = _seed_document(settings)
    app = create_app(settings)
    app.state.ollama_client = FakeOllamaClient()
    fake_embedding = FakeEmbeddingModel()
    monkeypatch.setattr("app.rag.index_manager.SentenceTransformerEmbeddingModel", lambda settings: fake_embedding)
    monkeypatch.setattr("app.rag.search_service.SentenceTransformerEmbeddingModel", lambda settings: fake_embedding)

    with TestClient(app) as client:
        rebuild_response = client.post("/vector-index/rebuild")
        status_response = client.get("/vector-index/status")
        search_response = client.post("/vector-search", json={"query": "agent security", "top_k": 1})
        document_response = client.post(f"/documents/{document_id}/index")

    assert rebuild_response.status_code == 200
    assert status_response.status_code == 200
    assert search_response.status_code == 200
    assert document_response.status_code == 200
    assert search_response.json()["results"]
