import sqlite3

from fastapi.testclient import TestClient

from app.services.document_service import create_document, find_document_by_sha256, get_document, list_documents
from tests.conftest import FakeOllamaClient, build_test_app, build_settings


def test_document_service_create_and_get(tmp_path) -> None:
    settings = build_settings(tmp_path)
    app, _ = build_test_app(tmp_path, FakeOllamaClient())
    with TestClient(app):
        document = create_document(
            settings,
            file_name="note.txt",
            file_path="a.txt",
            file_type="txt",
            size_bytes=5,
            sha256="abc",
            status="ready",
            text_path="a.txt",
            char_count=5,
            page_count=None,
            warning_code=None,
        )

    loaded = get_document(settings, document.id)
    assert loaded is not None
    assert loaded.file_name == "note.txt"


def test_document_service_find_duplicate_by_hash(tmp_path) -> None:
    settings = build_settings(tmp_path)
    app, _ = build_test_app(tmp_path, FakeOllamaClient())
    with TestClient(app):
        created = create_document(
            settings,
            file_name="note.txt",
            file_path="a.txt",
            file_type="txt",
            size_bytes=5,
            sha256="abc",
            status="ready",
            text_path="a.txt",
            char_count=5,
            page_count=None,
            warning_code=None,
        )
    duplicate = find_document_by_sha256(settings, "abc")
    assert duplicate is not None
    assert duplicate.id == created.id


def test_document_service_list_orders_desc(tmp_path) -> None:
    settings = build_settings(tmp_path)
    app, _ = build_test_app(tmp_path, FakeOllamaClient())
    with TestClient(app):
        create_document(
            settings,
            file_name="one.txt",
            file_path="one.txt",
            file_type="txt",
            size_bytes=1,
            sha256="1",
            status="ready",
            text_path="one.txt",
            char_count=1,
            page_count=None,
            warning_code=None,
        )
        create_document(
            settings,
            file_name="two.txt",
            file_path="two.txt",
            file_type="txt",
            size_bytes=2,
            sha256="2",
            status="ready",
            text_path="two.txt",
            char_count=2,
            page_count=None,
            warning_code=None,
        )
    items = list_documents(settings, limit=100, offset=0)
    assert items[0].file_name == "two.txt"
