import asyncio
import sqlite3
import threading
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app.api.chat as chat_api
from app.agent.models import ToolDefinition
from app.agent.registry import ToolRegistry
from app.agent.tool_operation_coordinator import ToolOperationCoordinator
from app.main import create_app, ensure_runtime_directories
from app.schemas.chat import ChatRequest
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


def test_chat_cancellation_does_not_write_partial_exchange(tmp_path) -> None:
    started = threading.Event()
    release = threading.Event()

    class _Args:
        @classmethod
        def model_validate(cls, value):
            return type("Validated", (), value)()

    class SlowTool:
        input_model = _Args

        def __init__(self) -> None:
            self.definition = ToolDefinition(name="list_documents", description="x", input_schema={}, read_only=True, timeout_seconds=5)

        def execute(self, arguments, settings) -> str:
            started.set()
            release.wait(timeout=1)
            return '{"items":[]}'

    async def scenario() -> None:
        settings = build_settings(tmp_path, TOOLS_ENABLED=True)
        app = create_app(settings)
        ensure_runtime_directories(settings)
        app.state.ollama_client = FakeOllamaClient(
            chat_result=type(
                "Result",
                (),
                {
                    "content": '{"type":"tool_call","calls":[{"id":"call_1","name":"list_documents","arguments":{}}]}',
                    "usage": type("Usage", (), {"prompt_tokens": 1, "completion_tokens": 1})(),
                },
            )()
        )
        app.state.chat_semaphore = asyncio.Semaphore(1)
        app.state.vector_operation_coordinator = SimpleNamespace()
        app.state.tool_operation_coordinator = ToolOperationCoordinator()
        registry = ToolRegistry()
        registry.register(SlowTool())

        original_registry_builder = chat_api.build_default_registry
        original_audit_writer = chat_api.write_rag_chat_audit
        chat_api.build_default_registry = lambda settings, coordinator: registry
        chat_api.write_rag_chat_audit = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("audit should not run"))
        request = SimpleNamespace(app=app)
        try:
            task = asyncio.create_task(chat_api.chat(request, ChatRequest(message="hujjatlar", use_tools=True, use_rag=False)))
            while not started.is_set():
                await asyncio.sleep(0.001)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            with sqlite3.connect(settings.resolved_database_path) as connection:
                count = connection.execute("SELECT COUNT(*) FROM messages;").fetchone()[0]
            assert count == 0
        finally:
            chat_api.build_default_registry = original_registry_builder
            chat_api.write_rag_chat_audit = original_audit_writer
            release.set()
            await app.state.tool_operation_coordinator.shutdown(timeout_seconds=0.2)

    asyncio.run(scenario())


def test_chat_async_tool_cancellation_does_not_write_partial_exchange(tmp_path) -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    class _Args:
        @classmethod
        def model_validate(cls, value):
            return type("Validated", (), value)()

    class SlowAsyncTool:
        input_model = _Args

        def __init__(self) -> None:
            self.definition = ToolDefinition(name="search_documents", description="x", input_schema={}, read_only=True, timeout_seconds=5)

        async def execute_async(self, arguments, settings) -> str:
            started.set()
            await release.wait()
            return '{"items":[]}'

    async def scenario() -> None:
        settings = build_settings(tmp_path, TOOLS_ENABLED=True)
        app = create_app(settings)
        ensure_runtime_directories(settings)
        app.state.ollama_client = FakeOllamaClient(
            chat_result=type(
                "Result",
                (),
                {
                    "content": '{"type":"tool_call","calls":[{"id":"call_1","name":"search_documents","arguments":{}}]}',
                    "usage": type("Usage", (), {"prompt_tokens": 1, "completion_tokens": 1})(),
                },
            )()
        )
        app.state.chat_semaphore = asyncio.Semaphore(1)
        app.state.vector_operation_coordinator = SimpleNamespace()
        app.state.tool_operation_coordinator = ToolOperationCoordinator()
        registry = ToolRegistry()
        registry.register(SlowAsyncTool())

        original_registry_builder = chat_api.build_default_registry
        original_audit_writer = chat_api.write_rag_chat_audit
        chat_api.build_default_registry = lambda settings, coordinator: registry
        chat_api.write_rag_chat_audit = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("audit should not run"))
        request = SimpleNamespace(app=app)
        try:
            task = asyncio.create_task(chat_api.chat(request, ChatRequest(message="hujjatlar", use_tools=True, use_rag=False)))
            await started.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            with sqlite3.connect(settings.resolved_database_path) as connection:
                count = connection.execute("SELECT COUNT(*) FROM messages;").fetchone()[0]
            assert count == 0
        finally:
            chat_api.build_default_registry = original_registry_builder
            chat_api.write_rag_chat_audit = original_audit_writer
            release.set()

    asyncio.run(scenario())
