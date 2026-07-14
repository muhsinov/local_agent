from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app.config import Settings
from app.documents.models import DocumentRecord
from app.documents.storage import resolve_storage_path
from app.rag.chunker import chunk_text
from app.rag.embedding_model import EmbeddingModel
from app.rag.exceptions import RagError
from app.rag.models import TextChunk


@dataclass(frozen=True)
class PreparedIndexBuild:
    documents: list[DocumentRecord]
    chunks: list[TextChunk]
    vectors: np.ndarray


def _read_document_text(settings: Settings, document: DocumentRecord) -> str:
    if not document.text_path or document.char_count <= 0:
        raise RagError(422, "DOCUMENT_HAS_NO_TEXT", "Hujjat ichida indexlash uchun matn topilmadi.")
    path = resolve_storage_path(settings.resolved_extracted_text_directory, document.text_path)
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise RagError(422, "DOCUMENT_HAS_NO_TEXT", "Extract qilingan hujjat matni topilmadi.") from exc
    except OSError as exc:
        raise RagError(500, "VECTOR_INDEX_STORAGE_ERROR", "Extract qilingan hujjat matnini o'qib bo'lmadi.") from exc


def build_chunks_for_documents(settings: Settings, documents: list[DocumentRecord]) -> list[TextChunk]:
    chunks: list[TextChunk] = []
    for document in documents:
        text = _read_document_text(settings, document)
        chunks.extend(
            chunk_text(
                document_id=document.id,
                text=text,
                chunk_size=settings.chunk_size_chars,
                overlap=settings.chunk_overlap_chars,
                min_chunk_chars=settings.chunk_min_chars,
                max_chunks=settings.max_chunks_per_document,
            )
        )
    return chunks


def build_embeddings(embedding_model: EmbeddingModel, chunks: list[TextChunk]) -> np.ndarray:
    texts = [chunk.text for chunk in chunks]
    return embedding_model.encode_documents(texts)


def collect_indexable_documents(connection, settings: Settings) -> list[DocumentRecord]:
    from app.services.document_service import _record_from_row

    rows = connection.execute(
        """
        SELECT *
        FROM documents
        WHERE status = 'ready'
          AND char_count > 0
          AND text_path IS NOT NULL
        ORDER BY id ASC;
        """
    ).fetchall()
    documents = [_record_from_row(row) for row in rows]
    valid_documents: list[DocumentRecord] = []
    for document in documents:
        try:
            path = resolve_storage_path(settings.resolved_extracted_text_directory, document.text_path)
        except Exception:
            continue
        if Path(path).exists():
            valid_documents.append(document)
    return valid_documents
