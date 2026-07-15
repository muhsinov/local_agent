import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import FakeOllamaClient, build_settings


def make_client(tmp_path: Path, **overrides):
    overrides.setdefault("DIRECT_VECTOR_MUTATIONS_ENABLED", False)
    overrides.setdefault("DIRECT_DOCUMENT_DELETE_ENABLED", False)
    settings = build_settings(tmp_path, LOCAL_CONTROL_PLANE_ENABLED=True, **overrides)
    app = create_app(settings)
    app.state.ollama_client = FakeOllamaClient()
    return TestClient(app), settings


def bootstrap(client: TestClient):
    response = client.post(
        "/session/bootstrap",
        headers={"host": "localhost:8000", "origin": "http://localhost:8000"},
    )
    assert response.status_code == 200
    return response.json()["csrf_token"]


def local_headers(csrf: str | None = None) -> dict[str, str]:
    headers = {"host": "localhost:8000", "origin": "http://localhost:8000"}
    if csrf is not None:
        headers["x-csrf-token"] = csrf
    return headers


def test_host_and_origin_validation(tmp_path):
    client, _ = make_client(tmp_path)
    with client:
        assert client.get("/health", headers={"host": "localhost:8000"}).status_code == 200
        assert client.get("/health", headers={"host": "127.0.0.1:8000"}).status_code == 200
        assert client.get("/health", headers={"host": "[::1]:8000"}).status_code == 200
        assert client.get("/health", headers={"host": "localhost.evil.test:8000"}).json()["detail"]["code"] == "LOCAL_HOST_DENIED"
        assert client.get("/health", headers={"host": "8.8.8.8:8000"}).json()["detail"]["code"] == "LOCAL_HOST_DENIED"
        assert client.post("/session/bootstrap", headers={"host": "localhost:8000", "origin": "http://evil.test:8000"}).json()["detail"]["code"] == "LOCAL_ORIGIN_DENIED"


def test_bootstrap_cookie_and_csrf_are_memory_only(tmp_path):
    client, settings = make_client(tmp_path)
    with client:
        csrf = bootstrap(client)
        assert csrf not in client.cookies.get("local_agent_session", "")
        with settings.resolved_database_path.open("rb") as handle:
            assert csrf.encode() not in handle.read()
        assert client.cookies.get("local_agent_session")


def test_mutations_require_session_and_csrf(tmp_path):
    client, _ = make_client(tmp_path)
    with client:
        no_session = client.post("/chat", headers={"host": "localhost:8000"}, json={"message": "hi"})
        assert no_session.json()["detail"]["code"] == "LOCAL_SESSION_REQUIRED"
        csrf = bootstrap(client)
        missing = client.post("/chat", headers=local_headers(), json={"message": "hi"})
        assert missing.json()["detail"]["code"] == "CSRF_TOKEN_REQUIRED"
        invalid = client.post("/chat", headers={**local_headers("bad"), "x-csrf-token": "bad"}, json={"message": "hi"})
        assert invalid.json()["detail"]["code"] == "CSRF_TOKEN_INVALID"
        valid = client.post("/chat", headers=local_headers(csrf), json={"message": "hi"})
        assert valid.status_code == 200


def test_direct_mutations_are_disabled_without_side_effect(tmp_path, monkeypatch):
    client, settings = make_client(tmp_path)
    called = {"rebuild": False}
    monkeypatch.setattr("app.api.vector_search.rebuild_vector_index", lambda *args, **kwargs: called.__setitem__("rebuild", True))
    with client:
        csrf = bootstrap(client)
        for path, method in [
            ("/vector-index/rebuild", "post"),
            ("/documents/1/index", "post"),
            ("/documents/1?confirm=true", "delete"),
        ]:
            response = getattr(client, method)(path, headers=local_headers(csrf))
            assert response.status_code == 403
            assert response.json()["detail"]["code"] == "DIRECT_ACTION_DISABLED"
    assert called["rebuild"] is False
    assert settings.direct_vector_mutations_enabled is False


def test_enabled_direct_mutation_still_requires_csrf(tmp_path):
    client, _ = make_client(tmp_path, DIRECT_VECTOR_MUTATIONS_ENABLED=True)
    with client:
        assert client.post("/vector-index/rebuild", headers={"host": "localhost:8000"}).json()["detail"]["code"] == "LOCAL_SESSION_REQUIRED"
        csrf = bootstrap(client)
        assert client.post("/vector-index/rebuild", headers=local_headers()).json()["detail"]["code"] == "CSRF_TOKEN_REQUIRED"


def test_non_browser_api_token_is_opt_in_and_never_audit_value(tmp_path):
    token = "t" * 32
    client, settings = make_client(tmp_path, LOCAL_ALLOW_NON_BROWSER_CLIENTS=True, LOCAL_API_TOKEN=token)
    with client:
        denied = client.post("/chat", headers={"host": "localhost:8000"}, json={"message": "hi"})
        assert denied.json()["detail"]["code"] == "LOCAL_SESSION_REQUIRED"
        allowed = client.post("/chat", headers={"host": "localhost:8000", "authorization": f"Bearer {token}"}, json={"message": "hi"})
        assert allowed.status_code == 200
        with settings.resolved_database_path.open("rb") as handle:
            assert token.encode() not in handle.read()


def test_cors_is_explicit_and_audit_fields_are_safe(tmp_path):
    client, settings = make_client(tmp_path)
    with client:
        response = client.options(
            "/chat",
            headers={"host": "localhost:8000", "origin": "http://localhost:8000", "access-control-request-method": "POST"},
        )
        assert response.headers.get("access-control-allow-origin") == "http://localhost:8000"
        csrf = bootstrap(client)
        client.post("/chat", headers={**local_headers(csrf), "x-sensitive": "secret"}, json={"message": "private body"})
    import sqlite3

    with sqlite3.connect(settings.resolved_database_path) as connection:
        rows = connection.execute("SELECT action, arguments FROM audit_logs").fetchall()
    raw = " ".join(json.dumps(row) for row in rows)
    assert "secret" not in raw
    assert "private body" not in raw
    assert "local_session_create" in raw
