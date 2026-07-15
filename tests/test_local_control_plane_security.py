import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.security.local_control_plane.session_store import LocalSessionStore
from tests.conftest import FakeOllamaClient, build_settings


def make_client(tmp_path: Path, **overrides):
    overrides.setdefault("DIRECT_VECTOR_MUTATIONS_ENABLED", False)
    overrides.setdefault("DIRECT_DOCUMENT_DELETE_ENABLED", False)
    overrides.setdefault("RUNTIME_RESILIENCE_ENABLED", True)
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
        assert client.post("/session/bootstrap", headers={"host": "localhost:8000"}).json()["detail"]["code"] == "LOCAL_ORIGIN_DENIED"


def test_bootstrap_reuses_session_and_keeps_multiple_tab_tokens():
    store = LocalSessionStore(ttl_seconds=3600, max_active=2, session_bytes=32, csrf_bytes=32, max_csrf_tokens=2)
    first = store.bootstrap(None)
    assert first is not None
    raw_session, csrf_a, _ = first
    second = store.bootstrap(raw_session)
    assert second is not None
    _, csrf_b, _ = second
    assert store.active_count() == 1
    assert store.validate(raw_session, csrf_a)
    assert store.validate(raw_session, csrf_b)
    third = store.bootstrap(raw_session)
    assert third is not None
    assert store.csrf_token_count(raw_session) == 2
    assert not store.validate(raw_session, csrf_a)
    assert store.validate(raw_session, third[1])


def test_concurrent_bootstrap_is_atomic_and_does_not_overwrite_tokens():
    store = LocalSessionStore(ttl_seconds=3600, max_active=2, session_bytes=32, csrf_bytes=32, max_csrf_tokens=16)
    initial = store.bootstrap(None)
    assert initial is not None
    raw_session = initial[0]
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(store.bootstrap, [raw_session, raw_session]))
    assert all(result is not None for result in results)
    assert store.active_count() == 1
    assert all(store.validate(raw_session, result[1]) for result in results if result is not None)


def test_new_sessions_hit_limit_but_existing_session_can_reload():
    store = LocalSessionStore(ttl_seconds=3600, max_active=2, session_bytes=32, csrf_bytes=32)
    first = store.bootstrap(None)
    second = store.bootstrap(None)
    assert first is not None and second is not None
    assert store.bootstrap(None) is None
    assert store.bootstrap(first[0]) is not None
    assert store.active_count() == 2


def test_bootstrap_cookie_and_csrf_are_memory_only(tmp_path):
    client, settings = make_client(tmp_path)
    with client:
        csrf = bootstrap(client)
        assert csrf not in client.cookies.get("local_agent_session", "")
        with settings.resolved_database_path.open("rb") as handle:
            assert csrf.encode() not in handle.read()
        assert client.cookies.get("local_agent_session")


def test_bootstrap_reuses_cookie_and_sets_no_store_headers(tmp_path):
    client, settings = make_client(tmp_path)
    with client:
        first = client.post("/session/bootstrap", headers={"host": "localhost:8000", "origin": "http://localhost:8000"})
        cookie = client.cookies.get("local_agent_session")
        second = client.post("/session/bootstrap", headers={"host": "localhost:8000", "origin": "http://localhost:8000"})
        assert client.cookies.get("local_agent_session") == cookie
        assert second.headers["cache-control"] == "no-store"
        assert second.headers["pragma"] == "no-cache"
        assert settings.local_session_max_csrf_tokens == 16
        assert first.json()["csrf_token"] != second.json()["csrf_token"]


def test_api_token_cannot_bootstrap_without_browser_origin(tmp_path):
    token = "t" * 32
    client, _ = make_client(tmp_path, LOCAL_ALLOW_NON_BROWSER_CLIENTS=True, LOCAL_API_TOKEN=token)
    with client:
        response = client.post("/session/bootstrap", headers={"host": "localhost:8000", "authorization": f"Bearer {token}"})
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "LOCAL_ORIGIN_DENIED"


def test_runtime_request_id_rate_limit_and_safe_headers(tmp_path):
    client, settings = make_client(tmp_path, RATE_LIMIT_CHAT_REQUESTS=1, SAFE_LOG_DIRECTORY=tmp_path / "logs")
    with client:
        csrf = bootstrap(client)
        first = client.post("/chat", headers={**local_headers(csrf), "x-request-id": "client-value"}, json={"message": "private chat"})
        second = client.post("/chat", headers=local_headers(csrf), json={"message": "private chat"})
        assert len(first.headers["x-request-id"]) == 32
        assert first.headers["x-request-id"] != "client-value"
        assert second.status_code == 429
        assert second.headers["retry-after"]
        assert second.headers["x-ratelimit-limit"] == "1"
        assert second.headers["x-request-id"]
        assert first.headers["x-content-type-options"] == "nosniff"
        assert first.headers["x-frame-options"] == "DENY"
    raw_log = (settings.resolved_safe_log_directory / "local-agent.jsonl").read_text(encoding="utf-8")
    assert "private chat" not in raw_log
    assert "client-value" not in raw_log


def test_invalid_csrf_does_not_consume_rate_limit_bucket(tmp_path):
    client, _ = make_client(tmp_path, RATE_LIMIT_CHAT_REQUESTS=1)
    with client:
        csrf = bootstrap(client)
        invalid = client.post("/chat", headers=local_headers("bad"), json={"message": "x"})
        valid = client.post("/chat", headers=local_headers(csrf), json={"message": "x"})
        assert invalid.status_code == 403
        assert valid.status_code == 200


def test_oversized_json_is_rejected_but_liveness_is_dependency_free(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, REQUEST_BODY_MAX_BYTES=16384)
    with client:
        csrf = bootstrap(client)
        response = client.post(
            "/chat",
            headers={**local_headers(csrf), "content-type": "application/json"},
            content=b"x" * 17000,
        )
        assert response.status_code == 413
        monkeypatch.setattr("app.api.health.check_database", lambda settings: (_ for _ in ()).throw(RuntimeError("must not run")))
        assert client.get("/live", headers={"host": "localhost:8000"}).json() == {"status": "live"}


def test_ready_and_drain_states(tmp_path):
    client, _ = make_client(tmp_path)
    with client:
        assert client.get("/ready", headers={"host": "localhost:8000"}).status_code == 200
        csrf = bootstrap(client)
        import asyncio

        asyncio.run(client._transport.app.state.runtime_lifecycle.begin_drain())
        draining = client.get("/ready", headers={"host": "localhost:8000"})
        assert draining.status_code == 503
        assert draining.json()["status"] == "draining"
        assert client.get("/vector-index/status", headers={"host": "localhost:8000"}).status_code == 200
        chat = client.post("/chat", headers=local_headers(csrf), json={"message": "late"})
        assert chat.status_code == 503
        assert chat.json()["detail"]["code"] == "SERVER_DRAINING"


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
