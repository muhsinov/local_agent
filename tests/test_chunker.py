import pytest

from app.rag.chunker import chunk_text
from app.rag.exceptions import RagError


def test_chunker_rejects_empty_text() -> None:
    with pytest.raises(RagError) as exc:
        chunk_text(
            document_id=1,
            text="   \n\t",
            chunk_size=200,
            overlap=0,
            min_chunk_chars=20,
            max_chunks=10,
        )
    assert exc.value.code == "DOCUMENT_HAS_NO_TEXT"


def test_chunker_is_deterministic_for_unicode_text() -> None:
    text = "Salom dunyo.\n\nBu ikkinchi paragraf. Привет мир. 😀 Emoji ham bor."
    first = chunk_text(document_id=7, text=text, chunk_size=28, overlap=5, min_chunk_chars=10, max_chunks=20)
    second = chunk_text(document_id=7, text=text, chunk_size=28, overlap=5, min_chunk_chars=10, max_chunks=20)
    assert first == second
    assert all(chunk.char_count == len(chunk.text) for chunk in first)
    assert all(chunk.start_char >= 0 for chunk in first)
    assert all(chunk.end_char > chunk.start_char for chunk in first)


def test_chunker_prefers_paragraph_and_line_boundaries() -> None:
    text = "A" * 30 + "\n\n" + "B" * 30 + "\n" + "C" * 30
    chunks = chunk_text(document_id=1, text=text, chunk_size=40, overlap=0, min_chunk_chars=10, max_chunks=10)
    assert chunks[0].text.endswith("A" * 30)
    assert chunks[1].text.startswith("B")


def test_chunker_enforces_chunk_limit() -> None:
    with pytest.raises(RagError) as exc:
        chunk_text(document_id=3, text="x" * 1000, chunk_size=20, overlap=0, min_chunk_chars=20, max_chunks=2)
    assert exc.value.code == "DOCUMENT_CHUNK_LIMIT_EXCEEDED"
