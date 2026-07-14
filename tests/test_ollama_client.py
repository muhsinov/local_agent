import asyncio
import json

import httpx
import pytest

from app.llm.exceptions import (
    OllamaInvalidResponseError,
    OllamaModelNotFoundError,
    OllamaTimeoutError,
    OllamaUnavailableError,
)
from app.llm.ollama_client import OllamaClient
from tests.conftest import build_settings


def make_transport(handler):
    return httpx.MockTransport(handler)


def test_get_models_parses_normal_response(tmp_path) -> None:
    settings = build_settings(tmp_path)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/tags"
        return httpx.Response(200, json={"models": [{"name": "qwen3:1.7b", "model": "qwen3:1.7b"}]})

    client = OllamaClient(settings, transport=make_transport(handler))
    models = asyncio.run(client.get_models())
    asyncio.run(client.close())

    assert len(models) == 1
    assert models[0].name == "qwen3:1.7b"


def test_is_model_installed_matches_exact_name(tmp_path) -> None:
    settings = build_settings(tmp_path)
    client = OllamaClient(
        settings,
        transport=make_transport(lambda _: httpx.Response(200, json={"models": [{"name": "qwen3:1.7b"}]})),
    )
    assert asyncio.run(client.is_model_installed("qwen3:1.7b")) is True
    asyncio.run(client.close())


def test_is_model_installed_matches_allowed_suffix(tmp_path) -> None:
    settings = build_settings(tmp_path)
    client = OllamaClient(
        settings,
        transport=make_transport(lambda _: httpx.Response(200, json={"models": [{"name": "qwen3:1.7b-latest"}]})),
    )
    assert asyncio.run(client.is_model_installed("qwen3:1.7b")) is True
    asyncio.run(client.close())


def test_is_model_installed_rejects_other_models(tmp_path) -> None:
    settings = build_settings(tmp_path)
    client = OllamaClient(
        settings,
        transport=make_transport(lambda _: httpx.Response(200, json={"models": [{"name": "qwen3:4b"}]})),
    )
    assert asyncio.run(client.is_model_installed("qwen3:1.7b")) is False
    asyncio.run(client.close())


def test_get_models_maps_timeout(tmp_path) -> None:
    settings = build_settings(tmp_path)

    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow")

    client = OllamaClient(settings, transport=make_transport(handler))
    with pytest.raises(OllamaTimeoutError):
        asyncio.run(client.get_models())
    asyncio.run(client.close())


def test_get_models_maps_connection_error(tmp_path) -> None:
    settings = build_settings(tmp_path)

    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline")

    client = OllamaClient(settings, transport=make_transport(handler))
    with pytest.raises(OllamaUnavailableError):
        asyncio.run(client.get_models())
    asyncio.run(client.close())


def test_get_models_404_is_not_model_missing(tmp_path) -> None:
    settings = build_settings(tmp_path)
    client = OllamaClient(settings, transport=make_transport(lambda _: httpx.Response(404, json={"error": "missing"})))
    with pytest.raises(OllamaUnavailableError):
        asyncio.run(client.get_models())
    asyncio.run(client.close())


def test_get_models_rejects_invalid_json(tmp_path) -> None:
    settings = build_settings(tmp_path)
    client = OllamaClient(settings, transport=make_transport(lambda _: httpx.Response(200, text="{bad")))
    with pytest.raises(OllamaInvalidResponseError):
        asyncio.run(client.get_models())
    asyncio.run(client.close())


def test_get_models_rejects_invalid_structure(tmp_path) -> None:
    settings = build_settings(tmp_path)
    client = OllamaClient(settings, transport=make_transport(lambda _: httpx.Response(200, json={"models": {}})))
    with pytest.raises(OllamaInvalidResponseError):
        asyncio.run(client.get_models())
    asyncio.run(client.close())


def test_chat_parses_valid_response(tmp_path) -> None:
    settings = build_settings(tmp_path)

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "message": {"content": "Salom"},
                "prompt_eval_count": 11,
                "eval_count": 22,
            },
        )

    client = OllamaClient(settings, transport=make_transport(handler))
    result = asyncio.run(client.chat([{"role": "user", "content": "Salom"}]))
    asyncio.run(client.close())

    assert result.content == "Salom"
    assert result.usage.prompt_tokens == 11
    assert result.usage.completion_tokens == 22


def test_chat_rejects_empty_assistant_content(tmp_path) -> None:
    settings = build_settings(tmp_path)
    client = OllamaClient(
        settings,
        transport=make_transport(lambda _: httpx.Response(200, json={"message": {"content": "   "}})),
    )
    with pytest.raises(OllamaInvalidResponseError):
        asyncio.run(client.chat([{"role": "user", "content": "Salom"}]))
    asyncio.run(client.close())


def test_chat_maps_model_not_found_404(tmp_path) -> None:
    settings = build_settings(tmp_path)
    client = OllamaClient(
        settings,
        transport=make_transport(lambda _: httpx.Response(404, json={"error": "model qwen3:1.7b not found"})),
    )
    with pytest.raises(OllamaModelNotFoundError):
        asyncio.run(client.chat([{"role": "user", "content": "Salom"}]))
    asyncio.run(client.close())


def test_chat_rejects_unrelated_404_as_unavailable(tmp_path) -> None:
    settings = build_settings(tmp_path)
    client = OllamaClient(
        settings,
        transport=make_transport(lambda _: httpx.Response(404, json={"error": "route missing"})),
    )
    with pytest.raises(OllamaUnavailableError):
        asyncio.run(client.chat([{"role": "user", "content": "Salom"}]))
    asyncio.run(client.close())


def test_chat_usage_fields_can_be_missing(tmp_path) -> None:
    settings = build_settings(tmp_path)
    client = OllamaClient(
        settings,
        transport=make_transport(lambda _: httpx.Response(200, json={"message": {"content": "Javob"}})),
    )
    result = asyncio.run(client.chat([{"role": "user", "content": "Salom"}]))
    asyncio.run(client.close())

    assert result.usage.prompt_tokens is None
    assert result.usage.completion_tokens is None


def test_chat_rejects_boolean_usage_values(tmp_path) -> None:
    settings = build_settings(tmp_path)
    client = OllamaClient(
        settings,
        transport=make_transport(
            lambda _: httpx.Response(
                200,
                json={"message": {"content": "Javob"}, "prompt_eval_count": True},
            )
        ),
    )
    with pytest.raises(OllamaInvalidResponseError):
        asyncio.run(client.chat([{"role": "user", "content": "Salom"}]))
    asyncio.run(client.close())


def test_chat_rejects_negative_usage_values(tmp_path) -> None:
    settings = build_settings(tmp_path)
    client = OllamaClient(
        settings,
        transport=make_transport(
            lambda _: httpx.Response(
                200,
                json={"message": {"content": "Javob"}, "prompt_eval_count": -1},
            )
        ),
    )
    with pytest.raises(OllamaInvalidResponseError):
        asyncio.run(client.chat([{"role": "user", "content": "Salom"}]))
    asyncio.run(client.close())


def test_chat_payload_contains_expected_options(tmp_path) -> None:
    settings = build_settings(tmp_path)
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json={"message": {"content": "Javob"}})

    client = OllamaClient(settings, transport=make_transport(handler))
    asyncio.run(client.chat([{"role": "user", "content": "Salom"}]))
    asyncio.run(client.close())

    assert captured["payload"]["stream"] is False
    assert captured["payload"]["think"] is False
    assert captured["payload"]["keep_alive"] == settings.ollama_keep_alive
    assert captured["payload"]["options"]["temperature"] == settings.ollama_temperature
    assert captured["payload"]["options"]["num_ctx"] == settings.ollama_num_ctx
    assert captured["payload"]["options"]["num_predict"] == settings.ollama_num_predict
