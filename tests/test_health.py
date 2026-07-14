from pathlib import Path

from fastapi.testclient import TestClient


def test_health_endpoint_returns_ok(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test_local_agent.db"))
    monkeypatch.setenv("UPLOAD_DIRECTORY", str(tmp_path / "uploads"))
    monkeypatch.setenv("VECTOR_STORE_DIRECTORY", str(tmp_path / "vector_store"))

    from app.config import get_settings
    from app.main import app

    get_settings.cache_clear()

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "app": "local-agent-demo",
        "version": "0.1.0",
        "database": "ok",
    }
