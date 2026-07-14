import asyncio

import pytest

from app.rag.exceptions import RagError
from app.rag.models import RetrievedChunk
from app.rag.rag_service import RagService
from app.rag.operation_coordinator import VectorOperationCoordinator
from tests.conftest import build_settings


def fake_results():
    return (
        [
            RetrievedChunk(
                chunk_id=1,
                document_id=1,
                file_name="doc.txt",
                chunk_index=1,
                text="agent xavfsizligi haqida matn",
                score=0.9,
                start_char=0,
                end_char=20,
            )
        ],
        "gen",
        "model",
        5,
    )


def test_rag_service_disabled(tmp_path) -> None:
    settings = build_settings(tmp_path)
    service = RagService(settings, VectorOperationCoordinator(), search_function=lambda *args, **kwargs: fake_results())
    result = asyncio.run(service.prepare(query="savol", document_ids=None, use_rag=False, available_context_chars=100))
    assert result.enabled is False
    assert result.used is False


def test_rag_service_fallback_on_empty_results(tmp_path) -> None:
    settings = build_settings(tmp_path)
    service = RagService(settings, VectorOperationCoordinator(), search_function=lambda *args, **kwargs: ([], "gen", "model", 1))
    result = asyncio.run(service.prepare(query="savol", document_ids=None, use_rag=True, available_context_chars=100))
    assert result.fallback is True


def test_rag_service_strict_requires_sources(tmp_path) -> None:
    settings = build_settings(tmp_path, RAG_REQUIRE_SOURCES=True)
    service = RagService(settings, VectorOperationCoordinator(), search_function=lambda *args, **kwargs: ([], "gen", "model", 1))
    with pytest.raises(RagError) as exc:
        asyncio.run(service.prepare(query="savol", document_ids=None, use_rag=True, available_context_chars=100))
    assert exc.value.code == "RAG_NO_RELEVANT_SOURCES"


def test_rag_service_uses_rag_max_top_k_for_candidates(tmp_path) -> None:
    settings = build_settings(tmp_path, RAG_TOP_K=2, RAG_MAX_TOP_K=6, RAG_MAX_SOURCES=4, RAG_CONTEXT_OVERLAP_DEDUP=True)
    seen: dict[str, int] = {}

    def search(*args, **kwargs):
        seen["top_k"] = kwargs["top_k"]
        return fake_results()

    service = RagService(settings, VectorOperationCoordinator(), search_function=search)
    result = asyncio.run(service.prepare(query="savol", document_ids=None, use_rag=True, available_context_chars=200))
    assert result.used is True
    assert seen["top_k"] == 6
