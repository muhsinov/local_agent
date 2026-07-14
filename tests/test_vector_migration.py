import sqlite3

from app.database import SCHEMA_VERSION, initialize_database
from tests.conftest import build_settings


def test_vector_state_singleton_created_for_empty_database(tmp_path) -> None:
    settings = build_settings(tmp_path)
    initialize_database(settings)
    connection = sqlite3.connect(settings.resolved_database_path)
    row = connection.execute(
        "SELECT status, active_generation, dirty, chunk_count, document_count FROM vector_index_state WHERE id = 1;"
    ).fetchone()
    version = connection.execute("PRAGMA user_version;").fetchone()[0]
    connection.close()
    assert row == ("empty", None, 0, 0, 0)
    assert version == SCHEMA_VERSION
