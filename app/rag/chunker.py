import hashlib
from typing import Iterable

from app.rag.exceptions import RagError
from app.rag.models import TextChunk


SENTENCE_BOUNDARIES = (".", "!", "?", "۔", "؟")


def _sanitize_text(text: str) -> str:
    return text.replace("\ufeff", "").replace("\u2060", "").strip()


def _normalized_chunk_hash(text: str) -> str:
    normalized = " ".join(text.split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _last_index(text: str, markers: Iterable[str], start: int, stop: int) -> int:
    best = -1
    for marker in markers:
        position = text.rfind(marker, start, stop)
        if position > best:
            best = position + len(marker)
    return best


def _find_boundary(text: str, start: int, target_end: int, min_end: int) -> int:
    hard_end = min(len(text), target_end)
    candidates = (
        _last_index(text, ("\n\n",), min_end, hard_end),
        _last_index(text, ("\n",), min_end, hard_end),
        _last_index(text, SENTENCE_BOUNDARIES, min_end, hard_end),
        _last_index(text, (" ", "\t"), min_end, hard_end),
    )
    for candidate in candidates:
        if candidate >= min_end:
            return candidate
    return hard_end


def chunk_text(
    *,
    document_id: int,
    text: str,
    chunk_size: int,
    overlap: int,
    min_chunk_chars: int,
    max_chunks: int,
) -> list[TextChunk]:
    source_text = _sanitize_text(text)
    if not source_text:
        raise RagError(422, "DOCUMENT_HAS_NO_TEXT", "Hujjat ichida indexlash uchun matn topilmadi.")

    chunks: list[TextChunk] = []
    start = 0
    text_length = len(source_text)

    while start < text_length:
        if len(chunks) >= max_chunks:
            raise RagError(
                422,
                "DOCUMENT_CHUNK_LIMIT_EXCEEDED",
                "Hujjat uchun ruxsat etilgan chunk limiti oshib ketdi.",
            )

        target_end = min(text_length, start + chunk_size)
        min_end = min(text_length, start + min_chunk_chars)
        end = _find_boundary(source_text, start, target_end, min_end)
        if end <= start:
            end = min(text_length, start + chunk_size)
        raw_segment = source_text[start:end]
        stripped = raw_segment.strip()
        if not stripped:
            start = max(start + 1, end)
            continue

        leading_trim = len(raw_segment) - len(raw_segment.lstrip())
        trailing_trim = len(raw_segment) - len(raw_segment.rstrip())
        actual_start = start + leading_trim
        actual_end = end - trailing_trim
        chunk_text_value = source_text[actual_start:actual_end]
        chunk = TextChunk(
            document_id=document_id,
            chunk_index=len(chunks),
            text=chunk_text_value,
            start_char=actual_start,
            end_char=actual_end,
            char_count=len(chunk_text_value),
            content_sha256=_normalized_chunk_hash(chunk_text_value),
        )
        chunks.append(chunk)
        if actual_end >= text_length:
            break

        next_start = max(actual_end - overlap, actual_start + 1)
        if next_start <= start:
            next_start = start + 1
        start = next_start

    if len(chunks) >= 2 and chunks[-1].char_count < min_chunk_chars:
        previous = chunks[-2]
        last = chunks[-1]
        merged_text = source_text[previous.start_char:last.end_char].strip()
        chunks[-2] = TextChunk(
            document_id=document_id,
            chunk_index=previous.chunk_index,
            text=merged_text,
            start_char=previous.start_char,
            end_char=last.end_char,
            char_count=len(merged_text),
            content_sha256=_normalized_chunk_hash(merged_text),
        )
        chunks.pop()

    return chunks
