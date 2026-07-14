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
