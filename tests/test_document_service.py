import sqlite3
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

import app.services.document_service as document_service
from app.api.errors import ApiError
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


class FakeConnection:
    def __init__(self, *, fail_on_select=False, fail_on_commit=False, row_factory_error=False):
        self.rows = []
        self.fail_on_select = fail_on_select
        self.fail_on_commit = fail_on_commit
        self.row_factory_error = row_factory_error
        self.lastrowid = 0
        self.rollback_called = False

    def execute(self, query, params=()):
        normalized = " ".join(query.split()).upper()
        if normalized == "BEGIN;":
            return None
        if normalized.startswith("INSERT INTO DOCUMENTS"):
            self.lastrowid += 1
            self.rows.append(
                {
                    "id": self.lastrowid,
                    "file_name": params[0],
                    "file_path": params[1],
                    "file_type": params[2],
                    "size_bytes": params[3],
                    "sha256": params[4],
                    "status": params[5],
                    "text_path": params[6],
                    "char_count": params[7],
                    "page_count": params[8],
                    "warning_code": params[9],
                    "indexed": 0,
                    "created_at": "2026-01-01",
                    "updated_at": "2026-01-01",
                }
            )
            return type("Cursor", (), {"lastrowid": self.lastrowid})()
        if normalized.startswith("UPDATE VECTOR_INDEX_STATE"):
            return None
        if normalized.startswith("SELECT * FROM DOCUMENTS WHERE ID = ?;"):
            if self.fail_on_select:
                raise sqlite3.OperationalError("select failed")
            row = next((item for item in self.rows if item["id"] == params[0]), None)
            if row is None:
                return type("Cursor", (), {"fetchone": lambda self: None})()
            if self.row_factory_error:
                row = dict(row)
                row["char_count"] = "bad"
            return type("Cursor", (), {"fetchone": lambda self, row=row: row})()
        raise AssertionError(query)

    def commit(self):
        if self.fail_on_commit:
            raise sqlite3.OperationalError("commit failed")

    def rollback(self):
        self.rollback_called = True
        self.rows = []


@contextmanager
def fake_connection_scope(connection):
    yield connection


def test_create_document_rolls_back_on_select_failure(monkeypatch, tmp_path) -> None:
    settings = build_settings(tmp_path)
    fake_connection = FakeConnection(fail_on_select=True)
    monkeypatch.setattr(document_service, "connection_scope", lambda settings: fake_connection_scope(fake_connection))

    with pytest.raises(sqlite3.OperationalError):
        create_document(
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

    assert fake_connection.rollback_called is True
    assert fake_connection.rows == []


def test_create_document_rolls_back_on_row_parse_failure(monkeypatch, tmp_path) -> None:
    settings = build_settings(tmp_path)
    fake_connection = FakeConnection(row_factory_error=True)
    monkeypatch.setattr(document_service, "connection_scope", lambda settings: fake_connection_scope(fake_connection))

    with pytest.raises(ValueError):
        create_document(
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

    assert fake_connection.rollback_called is True
    assert fake_connection.rows == []


def test_create_document_rolls_back_on_commit_failure(monkeypatch, tmp_path) -> None:
    settings = build_settings(tmp_path)
    fake_connection = FakeConnection(fail_on_commit=True)
    monkeypatch.setattr(document_service, "connection_scope", lambda settings: fake_connection_scope(fake_connection))

    with pytest.raises(sqlite3.OperationalError):
        create_document(
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

    assert fake_connection.rollback_called is True


def test_create_document_duplicate_error_preserves_contract(tmp_path) -> None:
    settings = build_settings(tmp_path)
    app, _ = build_test_app(tmp_path, FakeOllamaClient())
    with TestClient(app):
        create_document(
            settings,
            file_name="note.txt",
            file_path="a.txt",
            file_type="txt",
            size_bytes=5,
            sha256="dup",
            status="ready",
            text_path="a.txt",
            char_count=5,
            page_count=None,
            warning_code=None,
        )

        with pytest.raises(ApiError) as exc:
            create_document(
                settings,
                file_name="note-2.txt",
                file_path="b.txt",
                file_type="txt",
                size_bytes=5,
                sha256="dup",
                status="ready",
                text_path="b.txt",
                char_count=5,
                page_count=None,
                warning_code=None,
            )

    assert exc.value.code == "DOCUMENT_DUPLICATE"
