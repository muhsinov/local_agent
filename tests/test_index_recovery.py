import json
from pathlib import Path
import sqlite3

import pytest

import app.rag.index_manager as index_manager
from app.rag.exceptions import RagError
from app.rag.index_manager import ensure_vector_directories, reconcile_vector_index, rebuild_vector_index
from app.services.document_service import create_document
from tests.conftest import FakeEmbeddingModel, build_settings
from app.database import initialize_database


def test_reconcile_cleans_orphan_building_directory(tmp_path) -> None:
    settings = build_settings(tmp_path)
    initialize_database(settings)
    ensure_vector_directories(settings)
    building = settings.resolved_vector_store_directory / "generations" / "orphan.building"
    building.mkdir(parents=True, exist_ok=True)
    reconcile_vector_index(settings)
    assert not building.exists()


def test_reconcile_marks_error_for_missing_active_generation(tmp_path) -> None:
    settings = build_settings(tmp_path)
    initialize_database(settings)
    generations = settings.resolved_vector_store_directory / "generations"
    generations.mkdir(parents=True, exist_ok=True)
    with __import__("sqlite3").connect(settings.resolved_database_path) as connection:
        connection.execute(
            """
            UPDATE vector_index_state
            SET status = 'ready',
                active_generation = 'missing-gen',
                embedding_model = ?,
                embedding_dimension = 384,
                chunk_count = 1,
                document_count = 1
            WHERE id = 1;
            """,
            (settings.embedding_model_name,),
        )
        connection.commit()
    reconcile_vector_index(settings)
    with __import__("sqlite3").connect(settings.resolved_database_path) as connection:
        row = connection.execute("SELECT status, dirty FROM vector_index_state WHERE id = 1;").fetchone()
    assert row == ("error", 1)


def test_rebuild_cleans_up_on_fsync_failure(monkeypatch, tmp_path) -> None:
    settings = build_settings(tmp_path, EMBEDDING_DIMENSION=64)
    initialize_database(settings)
    settings.resolved_upload_directory.mkdir(parents=True, exist_ok=True)
    settings.resolved_extracted_text_directory.mkdir(parents=True, exist_ok=True)
    text = "agent xavfsizligi " * 20
    (settings.resolved_upload_directory / "doc.txt").write_text(text, encoding="utf-8")
    (settings.resolved_extracted_text_directory / "doc.txt").write_text(text, encoding="utf-8")
    create_document(
        settings,
        file_name="doc.txt",
        file_path="doc.txt",
        file_type="txt",
        size_bytes=len(text.encode("utf-8")),
        sha256="sha-doc",
        status="ready",
        text_path="doc.txt",
        char_count=len(text),
        page_count=None,
        warning_code=None,
    )

    def fail_fsync(path):
        raise RagError(500, "VECTOR_INDEX_STORAGE_ERROR", "Vector index faylini diskka yozib bo'lmadi.")

    monkeypatch.setattr(index_manager, "_fsync_file", fail_fsync)

    with pytest.raises(RagError) as exc:
        rebuild_vector_index(settings, embedding_model=FakeEmbeddingModel(dimension=64))

    assert exc.value.code == "VECTOR_INDEX_STORAGE_ERROR"
    generations_root = settings.resolved_vector_store_directory / "generations"
    assert not any(path.name.endswith(".building") for path in generations_root.iterdir())
    with sqlite3.connect(settings.resolved_database_path) as connection:
        chunk_count = connection.execute("SELECT COUNT(*) FROM document_chunks;").fetchone()[0]
        status = connection.execute("SELECT status, active_generation FROM vector_index_state WHERE id = 1;").fetchone()
    assert chunk_count == 0
    assert status == ("empty", None)
