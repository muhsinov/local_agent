import sqlite3

import pytest

from app.rag.exceptions import RagError
from app.rag.index_manager import rebuild_vector_index
from app.rag.search_service import semantic_search
from app.services.document_service import create_document
from tests.conftest import FakeEmbeddingModel, build_settings
from app.database import initialize_database


def _create_ready_document(settings, name: str, text: str) -> int:
    settings.resolved_extracted_text_directory.mkdir(parents=True, exist_ok=True)
    settings.resolved_upload_directory.mkdir(parents=True, exist_ok=True)
    (settings.resolved_upload_directory / name).write_text(text, encoding="utf-8")
    text_file = f"{name}.txt"
    (settings.resolved_extracted_text_directory / text_file).write_text(text, encoding="utf-8")
    record = create_document(
        settings,
        file_name=name,
        file_path=name,
        file_type="txt",
        size_bytes=len(text.encode("utf-8")),
        sha256=f"sha-{name}",
        status="ready",
        text_path=text_file,
        char_count=len(text),
        page_count=None,
        warning_code=None,
    )
    return record.id


def test_semantic_search_returns_results_and_filtering(tmp_path) -> None:
    settings = build_settings(tmp_path, EMBEDDING_DIMENSION=64)
    initialize_database(settings)
    first_id = _create_ready_document(settings, "first.txt", "agent xavfsizligi va himoya qoidalari")
    second_id = _create_ready_document(settings, "second.txt", "oshxona retsepti va taomlar")
    rebuild_vector_index(settings, embedding_model=FakeEmbeddingModel())
    results, generation_id, _, _ = semantic_search(
        settings,
        query="xavfsizlik qoidalari",
        top_k=2,
        document_ids=[first_id],
        embedding_model=FakeEmbeddingModel(),
    )
    assert generation_id
    assert results
    assert all(item.document_id == first_id for item in results)


def test_semantic_search_rejects_empty_index(tmp_path) -> None:
    settings = build_settings(tmp_path, EMBEDDING_DIMENSION=64)
    initialize_database(settings)
    with pytest.raises(RagError) as exc:
        semantic_search(settings, query="test", top_k=1, embedding_model=FakeEmbeddingModel())
    assert exc.value.code == "VECTOR_INDEX_EMPTY"
