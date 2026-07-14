from dataclasses import dataclass
from typing import Any

import httpx

from app.config import Settings
from app.llm.exceptions import (
    OllamaInvalidResponseError,
    OllamaModelNotFoundError,
    OllamaTimeoutError,
    OllamaUnavailableError,
)


SYSTEM_PROMPT = (
    "You are a local AI assistant running on the user's computer.\n"
    "Answer concisely and accurately.\n"
    "Reply in the same language as the user unless asked otherwise.\n"
    "Do not claim to have used tools, files, or the internet.\n"
    "You cannot read local files, browse the internet, use tools, or perform RAG in this phase."
)


@dataclass
class OllamaModel:
    """Normalized Ollama model entry."""

    name: str
    model: str | None = None


@dataclass
class OllamaUsage:
    """Token usage summary returned by Ollama."""

    prompt_tokens: int | None
    completion_tokens: int | None


@dataclass
class OllamaChatResult:
    """Parsed non-streaming Ollama chat response."""

    content: str
    usage: OllamaUsage


class OllamaClient:
    """Small async client for the local Ollama HTTP API."""

    def __init__(
        self,
        settings: Settings,
        transport: httpx.AsyncBaseTransport | None = None,
        async_client: httpx.AsyncClient | None = None,
    ) -> None:
        base_url = settings.ollama_base_url.rstrip("/")
        timeout = httpx.Timeout(
            connect=min(5.0, float(settings.request_timeout_seconds)),
            read=float(settings.request_timeout_seconds),
            write=float(settings.request_timeout_seconds),
            pool=min(5.0, float(settings.request_timeout_seconds)),
        )
        self._settings = settings
        if async_client is not None:
            self._client = async_client
            self._owns_client = False
        else:
            self._client = httpx.AsyncClient(base_url=base_url, timeout=timeout, transport=transport)
            self._owns_client = True

    async def get_models(self) -> list[OllamaModel]:
        """Return the models exposed by the local Ollama server."""

        payload = await self._request_json("GET", "/api/tags")
        raw_models = payload.get("models")
        if not isinstance(raw_models, list):
            raise OllamaInvalidResponseError("Ollama models ro'yxati noto'g'ri formatda qaytdi.")

        models: list[OllamaModel] = []
        for item in raw_models:
            if not isinstance(item, dict):
                raise OllamaInvalidResponseError("Ollama models elementi noto'g'ri formatda qaytdi.")

            name = item.get("name")
            model = item.get("model")
            if not isinstance(name, str) or not name.strip():
                raise OllamaInvalidResponseError("Ollama model nomi bo'sh yoki mavjud emas.")

            models.append(OllamaModel(name=name.strip(), model=model.strip() if isinstance(model, str) else None))

        return models

    async def is_model_installed(self, model_name: str) -> bool:
        """Check whether the configured model is available locally."""

        for model in await self.get_models():
            for candidate in (model.name, model.model):
                if candidate and self._matches_model_name(candidate, model_name):
                    return True
        return False

    async def chat(self, messages: list[dict[str, str]]) -> OllamaChatResult:
        """Send a non-streaming chat request to the configured Ollama model."""

        payload = await self._request_json(
            "POST",
            "/api/chat",
            model_not_found_on_404=True,
            json={
                "model": self._settings.ollama_model,
                "messages": messages,
                "stream": False,
                "think": self._settings.ollama_think,
                "keep_alive": self._settings.ollama_keep_alive,
                "options": {
                    "temperature": self._settings.ollama_temperature,
                    "num_ctx": self._settings.ollama_num_ctx,
                    "num_predict": self._settings.ollama_num_predict,
                },
            },
        )
        message = payload.get("message")
        if not isinstance(message, dict):
            raise OllamaInvalidResponseError("Ollama chat javobi noto'g'ri formatda qaytdi.")

        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise OllamaInvalidResponseError("Ollama bo'sh assistant javobini qaytardi.")

        return OllamaChatResult(
            content=content.strip(),
            usage=OllamaUsage(
                prompt_tokens=self._optional_int(payload.get("prompt_eval_count")),
                completion_tokens=self._optional_int(payload.get("eval_count")),
            ),
        )

    async def close(self) -> None:
        """Close the underlying HTTP client."""

        if self._owns_client:
            await self._client.aclose()

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        model_not_found_on_404: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any]:
        try:
            response = await self._client.request(method, path, **kwargs)
        except httpx.TimeoutException as exc:
            raise OllamaTimeoutError("Ollama javobi vaqtida kelmadi.") from exc
        except httpx.HTTPError as exc:
            raise OllamaUnavailableError("Ollama serveriga ulanib bo'lmadi.") from exc

        if response.status_code == 404:
            if model_not_found_on_404 and self._is_model_not_found_response(response):
                raise OllamaModelNotFoundError("So'ralgan Ollama modeli topilmadi.")
            raise OllamaUnavailableError("Ollama serveri so'rovni bajara olmadi.")
        if response.status_code >= 400:
            raise OllamaUnavailableError("Ollama serveri so'rovni bajara olmadi.")

        try:
            payload = response.json()
        except ValueError as exc:
            raise OllamaInvalidResponseError("Ollama noto'g'ri JSON javob qaytardi.") from exc

        if not isinstance(payload, dict):
            raise OllamaInvalidResponseError("Ollama javobi JSON object bo'lishi kerak.")
        return payload

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, int):
            raise OllamaInvalidResponseError("Ollama usage qiymatlari noto'g'ri formatda qaytdi.")
        if value < 0:
            raise OllamaInvalidResponseError("Ollama usage qiymatlari manfiy bo'lishi mumkin emas.")
        return value

    @staticmethod
    def _matches_model_name(candidate: str, target: str) -> bool:
        normalized_candidate = candidate.strip().lower()
        normalized_target = target.strip().lower()
        return normalized_candidate == normalized_target or normalized_candidate.startswith(f"{normalized_target}-")

    @staticmethod
    def _is_model_not_found_response(response: httpx.Response) -> bool:
        try:
            payload = response.json()
        except ValueError:
            return False
        if not isinstance(payload, dict):
            return False
        error = payload.get("error")
        return isinstance(error, str) and "model" in error.lower() and "not found" in error.lower()
