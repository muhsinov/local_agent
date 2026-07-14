from fastapi.testclient import TestClient

from app.llm.ollama_client import OllamaModel
from tests.conftest import (
    FakeOllamaClient,
    OllamaInvalidResponseError,
    OllamaModelNotFoundError,
    OllamaTimeoutError,
    OllamaUnavailableError,
    build_test_app,
)


def test_model_status_reports_installed_model(tmp_path) -> None:
    app, _ = build_test_app(
        tmp_path,
        FakeOllamaClient(models=[OllamaModel(name="qwen3:1.7b", model="qwen3:1.7b-latest")]),
    )

    with TestClient(app) as client:
        response = client.get("/model/status")

    assert response.status_code == 200
    assert response.json() == {
        "ollama": "ok",
        "model": "qwen3:1.7b",
        "installed": True,
    }


def test_model_status_reports_missing_model(tmp_path) -> None:
    app, _ = build_test_app(
        tmp_path,
        FakeOllamaClient(models=[OllamaModel(name="llama3:8b", model="llama3:8b")]),
    )

    with TestClient(app) as client:
        response = client.get("/model/status")

    assert response.status_code == 200
    assert response.json() == {
        "ollama": "ok",
        "model": "qwen3:1.7b",
        "installed": False,
    }


def test_model_status_reports_unreachable_ollama(tmp_path) -> None:
    app, _ = build_test_app(
        tmp_path,
        FakeOllamaClient(models_error=OllamaUnavailableError("offline")),
    )

    with TestClient(app) as client:
        response = client.get("/model/status")

    assert response.status_code == 503
    assert response.json() == {
        "ollama": "unreachable",
        "model": "qwen3:1.7b",
        "installed": False,
    }


def test_model_status_handles_invalid_json_response(tmp_path) -> None:
    app, _ = build_test_app(
        tmp_path,
        FakeOllamaClient(models_error=OllamaInvalidResponseError("bad json")),
    )

    with TestClient(app) as client:
        response = client.get("/model/status")

    assert response.status_code == 502
    assert response.json() == {
        "detail": {
            "code": "OLLAMA_INVALID_RESPONSE",
            "message": "Ollama noto'g'ri javob qaytardi.",
        }
    }


def test_model_status_maps_timeout(tmp_path) -> None:
    app, _ = build_test_app(tmp_path, FakeOllamaClient(models_error=OllamaTimeoutError("slow")))

    with TestClient(app) as client:
        response = client.get("/model/status")

    assert response.status_code == 504
    assert response.json() == {
        "detail": {
            "code": "OLLAMA_TIMEOUT",
            "message": "Ollama javobi kutish vaqtidan oshdi.",
        }
    }


def test_model_status_maps_unexpected_model_not_found(tmp_path) -> None:
    app, _ = build_test_app(tmp_path, FakeOllamaClient(models_error=OllamaModelNotFoundError("weird")))

    with TestClient(app) as client:
        response = client.get("/model/status")

    assert response.status_code == 502
    assert response.json() == {
        "detail": {
            "code": "OLLAMA_INVALID_RESPONSE",
            "message": "Ollama noto'g'ri javob qaytardi.",
        }
    }
