from app.rag.context_builder import build_rag_context
from app.rag.models import RetrievedChunk


def make_chunk(chunk_id: int, score: float, text: str, document_id: int = 1, chunk_index: int = 0) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_id=document_id,
        file_name="doc.txt",
        chunk_index=chunk_index,
        text=text,
        score=score,
        start_char=0,
        end_char=len(text),
    )


def test_build_rag_context_is_deterministic_and_limited() -> None:
    context = build_rag_context(
        chunks=[
            make_chunk(2, 0.7, "beta", chunk_index=2),
            make_chunk(1, 0.9, "alpha", chunk_index=1),
            make_chunk(1, 0.9, "alpha", chunk_index=1),
        ],
        max_context_chars=500,
        max_chunk_chars=50,
        max_sources=2,
        deduplicate_overlap=True,
        generation_id="gen",
    )
    assert context.context_chars == len(context.context_text)
    assert [source.citation for source in context.sources] == ["[1]", "[2]"]
    assert context.sources[0].excerpt == "alpha"


def test_build_rag_context_respects_budget() -> None:
    context = build_rag_context(
        chunks=[make_chunk(1, 1.0, "x" * 500)],
        max_context_chars=20,
        max_chunk_chars=100,
        max_sources=1,
        deduplicate_overlap=False,
    )
    assert context.sources == []


def test_build_rag_context_truncates_final_excerpt_to_fit_budget() -> None:
    context = build_rag_context(
        chunks=[make_chunk(1, 1.0, "x" * 200)],
        max_context_chars=60,
        max_chunk_chars=200,
        max_sources=1,
        deduplicate_overlap=False,
        include_file_name=False,
        include_chunk_index=False,
    )
    assert len(context.sources) == 1
    assert context.context_chars == len(context.context_text)
    assert len(context.context_text) <= 60
    assert len(context.sources[0].excerpt) >= 24


def test_build_rag_context_does_not_deduplicate_across_documents() -> None:
    repeated = "common prefix " * 4
    context = build_rag_context(
        chunks=[
            make_chunk(1, 1.0, repeated + "doc1", document_id=1, chunk_index=1),
            make_chunk(2, 0.9, repeated + "doc2", document_id=2, chunk_index=2),
        ],
        max_context_chars=500,
        max_chunk_chars=200,
        max_sources=2,
        deduplicate_overlap=True,
    )
    assert context.sources[0].excerpt.startswith("common prefix")
    assert context.sources[1].excerpt.startswith("common prefix")


def test_build_rag_context_deduplicates_nearby_chunks_in_same_document() -> None:
    repeated = "common overlap " * 4
    context = build_rag_context(
        chunks=[
            make_chunk(1, 1.0, "intro " + repeated, document_id=1, chunk_index=1),
            make_chunk(2, 0.9, repeated + "second", document_id=1, chunk_index=2),
        ],
        max_context_chars=500,
        max_chunk_chars=200,
        max_sources=2,
        deduplicate_overlap=True,
    )
    assert not context.sources[1].excerpt.startswith("common overlap")
