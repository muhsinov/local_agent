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
    result = asyncio.run(service.prepare(query="savol", document_ids=None, use_rag=False))
    assert result.enabled is False
    assert result.used is False


def test_rag_service_fallback_on_empty_results(tmp_path) -> None:
    settings = build_settings(tmp_path)
    service = RagService(settings, VectorOperationCoordinator(), search_function=lambda *args, **kwargs: ([], "gen", "model", 1))
    result = asyncio.run(service.prepare(query="savol", document_ids=None, use_rag=True))
    assert result.fallback is True


def test_rag_service_strict_requires_sources(tmp_path) -> None:
    settings = build_settings(tmp_path, RAG_REQUIRE_SOURCES=True)
    service = RagService(settings, VectorOperationCoordinator(), search_function=lambda *args, **kwargs: ([], "gen", "model", 1))
    with pytest.raises(RagError) as exc:
        asyncio.run(service.prepare(query="savol", document_ids=None, use_rag=True))
    assert exc.value.code == "RAG_NO_RELEVANT_SOURCES"
