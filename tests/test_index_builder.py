from pathlib import Path

from app.rag.index_builder import build_chunks_for_documents
from app.documents.models import DocumentRecord
from tests.conftest import build_settings


def test_index_builder_reads_text_and_builds_chunks(tmp_path) -> None:
    settings = build_settings(tmp_path)
    settings.resolved_extracted_text_directory.mkdir(parents=True, exist_ok=True)
    text_path = settings.resolved_extracted_text_directory / "doc.txt"
    text_path.write_text("Salom dunyo. Bu test hujjatidir.\n\nYana bitta paragraf.", encoding="utf-8")
    document = DocumentRecord(
        id=1,
        file_name="doc.txt",
        file_path="uploads/doc.txt",
        file_type="txt",
        size_bytes=10,
        sha256=None,
        status="ready",
        text_path="doc.txt",
        char_count=60,
        page_count=None,
        warning_code=None,
        indexed=False,
        created_at="2026-01-01T00:00:00",
        updated_at="2026-01-01T00:00:00",
    )
    chunks = build_chunks_for_documents(settings, [document])
    assert chunks
    assert chunks[0].document_id == 1
