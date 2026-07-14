import json
from pathlib import Path

from app.rag.index_manager import ensure_vector_directories, reconcile_vector_index
from tests.conftest import build_settings
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
