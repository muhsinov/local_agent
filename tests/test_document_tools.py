import json

from app.database import initialize_database
from app.documents.storage import write_atomic_text
from app.services.document_service import create_document
from app.tools.document_tools import GetDocumentExcerptTool, GetDocumentMetadataTool, ListDocumentsTool
from tests.conftest import build_settings


def _seed_document(settings):
    path = settings.resolved_extracted_text_directory / "doc.txt"
    settings.resolved_extracted_text_directory.mkdir(parents=True, exist_ok=True)
    write_atomic_text(path, "salom dunyo")
    return create_document(
        settings,
        file_name="doc.txt",
        file_path="data/uploads/doc.txt",
        file_type="txt",
        size_bytes=11,
        sha256="abc",
        status="ready",
        text_path="doc.txt",
        char_count=11,
        page_count=None,
        warning_code=None,
    )


def test_document_tools_return_safe_metadata(tmp_path) -> None:
    settings = build_settings(tmp_path)
    initialize_database(settings)
    document = _seed_document(settings)
    payload = json.loads(GetDocumentMetadataTool(1).execute(type("Args", (), {"document_id": document.id})(), settings))
    assert "file_path" not in payload
    assert payload["document_id"] == document.id


def test_document_excerpt_reads_bounded_text(tmp_path) -> None:
    settings = build_settings(tmp_path)
    initialize_database(settings)
    document = _seed_document(settings)
    payload = json.loads(
        GetDocumentExcerptTool(1).execute(
            type("Args", (), {"document_id": document.id, "start_char": 0, "max_chars": 5})(),
            settings,
        )
    )
    assert payload["excerpt"] == "salom"


def test_list_documents_omits_internal_path(tmp_path) -> None:
    settings = build_settings(tmp_path)
    initialize_database(settings)
    _seed_document(settings)
    payload = json.loads(ListDocumentsTool(1).execute(type("Args", (), {"limit": 10, "offset": 0})(), settings))
    assert "file_path" not in payload[0]
