from app.rag.models import RagContext, RagSource, RetrievedChunk


MIN_MEANINGFUL_EXCERPT_CHARS = 24


def _escape_block(text: str) -> str:
    return text.replace("<", "&lt;").replace(">", "&gt;").strip()


def _deduplicate_excerpt(previous: str, current: str) -> str:
    max_overlap = min(len(previous), len(current), 200)
    for size in range(max_overlap, 20, -1):
        if previous.endswith(current[:size]):
            return current[size:].lstrip()
    return current


def _build_block(
    *,
    citation: str,
    file_name: str,
    chunk_index: int,
    excerpt: str,
    include_file_name: bool,
    include_chunk_index: bool,
) -> str:
    lines = [citation]
    if include_file_name:
        lines.append(f"File: {file_name}")
    if include_chunk_index:
        lines.append(f"Chunk: {chunk_index}")
    lines.append("Content:")
    lines.append(excerpt)
    return "\n".join(lines)


def _truncate_to_budget(text: str, budget: int) -> str:
    if budget <= 0:
        return ""
    return text[:budget].rstrip()


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
    previous_document_id: int | None = None
    previous_chunk_index: int | None = None
    previous_excerpt = ""

    for chunk in ordered:
        if chunk.chunk_id in seen_chunk_ids or len(sources) >= max_sources:
            continue
        seen_chunk_ids.add(chunk.chunk_id)
        excerpt = _escape_block(chunk.text)[:max_chunk_chars].strip()
        if (
            deduplicate_overlap
            and previous_excerpt
            and previous_document_id == chunk.document_id
            and previous_chunk_index is not None
            and abs(previous_chunk_index - chunk.chunk_index) <= 1
        ):
            excerpt = _deduplicate_excerpt(previous_excerpt, excerpt)
        if not excerpt.strip():
            continue

        citation = f"[{len(sources) + 1}]"
        block = _build_block(
            citation=citation,
            file_name=chunk.file_name,
            chunk_index=chunk.chunk_index,
            excerpt=excerpt,
            include_file_name=include_file_name,
            include_chunk_index=include_chunk_index,
        )
        separator_len = 2 if parts else 0
        remaining_budget = max_context_chars - (len("\n\n".join(parts)) + separator_len)
        if remaining_budget <= 0:
            break
        if len(block) > remaining_budget:
            header = _build_block(
                citation=citation,
                file_name=chunk.file_name,
                chunk_index=chunk.chunk_index,
                excerpt="",
                include_file_name=include_file_name,
                include_chunk_index=include_chunk_index,
            )
            excerpt_budget = remaining_budget - len(header)
            if excerpt_budget < MIN_MEANINGFUL_EXCERPT_CHARS:
                continue
            excerpt = _truncate_to_budget(excerpt, min(max_chunk_chars, excerpt_budget))
            if len(excerpt) < MIN_MEANINGFUL_EXCERPT_CHARS:
                continue
            block = _build_block(
                citation=citation,
                file_name=chunk.file_name,
                chunk_index=chunk.chunk_index,
                excerpt=excerpt,
                include_file_name=include_file_name,
                include_chunk_index=include_chunk_index,
            )
            if len(block) > remaining_budget:
                excerpt = _truncate_to_budget(excerpt, excerpt_budget - (len(block) - remaining_budget))
                if len(excerpt) < MIN_MEANINGFUL_EXCERPT_CHARS:
                    continue
                block = _build_block(
                    citation=citation,
                    file_name=chunk.file_name,
                    chunk_index=chunk.chunk_index,
                    excerpt=excerpt,
                    include_file_name=include_file_name,
                    include_chunk_index=include_chunk_index,
                )
            if len(block) > remaining_budget:
                continue

        parts.append(block)
        previous_document_id = chunk.document_id
        previous_chunk_index = chunk.chunk_index
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
