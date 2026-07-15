from fastapi.testclient import TestClient

from app.main import create_app
from app.services.document_service import create_document
from tests.conftest import FakeOllamaClient, build_settings


def test_chat_tool_mode_returns_safe_tool_summary(tmp_path) -> None:
    settings = build_settings(tmp_path, TOOLS_ENABLED=True)
    app = create_app(settings)
    app.state.ollama_client = FakeOllamaClient(
        chat_result=type(
            "Result",
            (),
            {"content": '{"type":"final","answer":"done"}', "usage": type("Usage", (), {"prompt_tokens": 1, "completion_tokens": 1})()},
        )()
    )
    with TestClient(app) as client:
        response = client.post("/chat", json={"message": "system ma'lumotini ko'rsat", "use_tools": True})
    assert response.status_code == 200
    assert response.json()["tool_calls"] == []
