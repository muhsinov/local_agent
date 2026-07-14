from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI
import numpy as np

from app.config import Settings
from app.llm.exceptions import (
    OllamaInvalidResponseError,
    OllamaModelNotFoundError,
    OllamaTimeoutError,
    OllamaUnavailableError,
)
from app.llm.ollama_client import OllamaChatResult, OllamaModel, OllamaUsage
from app.main import create_app


@dataclass
class FakeOllamaClient:
    models: list[OllamaModel] | None = None
    chat_result: OllamaChatResult | None = None
    models_error: Exception | None = None
    chat_error: Exception | None = None
    captured_messages: list[list[dict[str, str]]] | None = None
    closed: bool = False

    def __post_init__(self) -> None:
        if self.models is None:
            self.models = [OllamaModel(name="qwen3:1.7b", model="qwen3:1.7b")]
        if self.chat_result is None:
            self.chat_result = OllamaChatResult(
                content="Salom. Men lokal AI assistentman.",
                usage=OllamaUsage(prompt_tokens=12, completion_tokens=18),
            )
        if self.captured_messages is None:
            self.captured_messages = []

    async def get_models(self) -> list[OllamaModel]:
        if self.models_error is not None:
            raise self.models_error
        return list(self.models or [])

    async def is_model_installed(self, model_name: str) -> bool:
        models = await self.get_models()
        normalized_target = model_name.strip().lower()
        for model in models:
            for candidate in (model.name, model.model):
                if candidate:
                    normalized_candidate = candidate.strip().lower()
                    if (
                        normalized_candidate == normalized_target
                        or normalized_candidate.startswith(f"{normalized_target}-")
                    ):
                        return True
        return False

    async def chat(self, messages: list[dict[str, str]]) -> OllamaChatResult:
        self.captured_messages.append(messages)
        if self.chat_error is not None:
            raise self.chat_error
        return self.chat_result

    async def close(self) -> None:
        self.closed = True


@dataclass
class FakeEmbeddingModel:
    dimension: int = 64
    closed: bool = False

    def _vectorize(self, texts: list[str]) -> np.ndarray:
        rows: list[list[float]] = []
        for text in texts:
            normalized = text.strip()
            base = float(sum(ord(char) for char in normalized) or 1)
            seed = [
                base % 97,
                float(len(normalized) or 1),
                float(normalized.count("a") + normalized.count("A") + 1),
                float(normalized.count(" ") + 1),
            ]
            row = seed + [float((base + index) % 17 + 1) for index in range(self.dimension - len(seed))]
            rows.append(row[: self.dimension])
        array = np.asarray(rows, dtype=np.float32)
        norms = np.linalg.norm(array, axis=1, keepdims=True)
        return array / norms

    def encode_documents(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, 4), dtype=np.float32)
        return self._vectorize(texts)

    def encode_query(self, text: str) -> np.ndarray:
        return self._vectorize([text])

    def get_dimension(self) -> int:
        return 4

    def close(self) -> None:
        self.closed = True


def build_settings(tmp_path: Path, **overrides: object) -> Settings:
    values = {
        "DATABASE_PATH": tmp_path / "test_local_agent.db",
        "UPLOAD_DIRECTORY": tmp_path / "uploads",
        "EXTRACTED_TEXT_DIRECTORY": tmp_path / "extracted",
        "VECTOR_STORE_DIRECTORY": tmp_path / "vector_store",
    }
    values.update(overrides)
    return Settings(**values)


def build_test_app(tmp_path: Path, fake_client: FakeOllamaClient, **overrides: object) -> tuple[FastAPI, Settings]:
    settings = build_settings(tmp_path, **overrides)
    app = create_app(settings)
    app.state.ollama_client = fake_client
    return app, settings


__all__ = [
    "FakeEmbeddingModel",
    "FakeOllamaClient",
    "OllamaInvalidResponseError",
    "OllamaModelNotFoundError",
    "OllamaTimeoutError",
    "OllamaUnavailableError",
    "build_settings",
    "build_test_app",
]
