from app.rag.models import RagContext, RagSource, RetrievedChunk


def _escape_block(text: str) -> str:
    return text.replace("<", "&lt;").replace(">", "&gt;").strip()


def _deduplicate_excerpt(previous: str, current: str) -> str:
    max_overlap = min(len(previous), len(current), 200)
    for size in range(max_overlap, 20, -1):
        if previous.endswith(current[:size]):
            return current[size:].lstrip()
    return current


def build_rag_context(
    *,
    chunks: list[RetrievedChunk],
    max_context_chars: int,
    max_chunk_chars: int,
    max_sources: int,
    deduplicate_overlap: bool,
    generation_id: str | None = None,
    include_file_name: bool = True,
    include_chunk_index: bool = True,
) -> RagContext:
    ordered = sorted(chunks, key=lambda item: (-item.score, item.document_id, item.chunk_index, item.chunk_id))
    seen_chunk_ids: set[int] = set()
    sources: list[RagSource] = []
    parts: list[str] = []
    previous_excerpt = ""

    for chunk in ordered:
        if chunk.chunk_id in seen_chunk_ids or len(sources) >= max_sources:
            continue
        seen_chunk_ids.add(chunk.chunk_id)
        excerpt = _escape_block(chunk.text)[:max_chunk_chars].strip()
        if deduplicate_overlap and previous_excerpt:
            excerpt = _deduplicate_excerpt(previous_excerpt, excerpt)
        if not excerpt.strip():
            continue

        citation = f"[{len(sources) + 1}]"
        lines = [citation]
        if include_file_name:
            lines.append(f"File: {chunk.file_name}")
        if include_chunk_index:
            lines.append(f"Chunk: {chunk.chunk_index}")
        lines.append("Content:")
        lines.append(excerpt)
        block = "\n".join(lines)
        candidate = "\n\n".join([*parts, block]) if parts else block
        if len(candidate) > max_context_chars:
            continue

        parts.append(block)
        previous_excerpt = excerpt
        sources.append(
            RagSource(
                citation=citation,
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                file_name=chunk.file_name,
                chunk_index=chunk.chunk_index,
                score=chunk.score,
                start_char=chunk.start_char,
                end_char=chunk.end_char,
                excerpt=excerpt,
            )
        )

    context_text = "\n\n".join(parts)
    return RagContext(
        context_text=context_text,
        sources=sources,
        generation_id=generation_id,
        retrieved_count=len(ordered),
        context_chars=len(context_text),
    )
