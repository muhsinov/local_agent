from time import perf_counter

from app.config import Settings
from app.database import connection_scope
from app.rag.embedding_model import EmbeddingModel, SentenceTransformerEmbeddingModel
from app.rag.exceptions import RagError
from app.rag.faiss_store import FaissStore
from app.rag.index_manager import _generation_dir, _index_path, _load_state, _manifest_path, _read_manifest
from app.rag.models import RetrievedChunk
from app.services.chunk_service import get_chunks_by_ids


def semantic_search(
    settings: Settings,
    *,
    query: str,
    top_k: int,
    document_ids: list[int] | None = None,
    embedding_model: EmbeddingModel | None = None,
) -> tuple[list[RetrievedChunk], str, str, int]:
    normalized_query = query.strip()
    if not normalized_query:
        raise RagError(422, "VECTOR_SEARCH_INVALID_QUERY", "Qidiruv so'rovi bo'sh bo'lishi mumkin emas.")
    if len(normalized_query) > 2000:
        raise RagError(422, "VECTOR_SEARCH_INVALID_QUERY", "Qidiruv so'rovi juda uzun.")
    started_at = perf_counter()
    with connection_scope(settings) as connection:
        state = _load_state(connection)
        if state.status == "empty":
            raise RagError(409, "VECTOR_INDEX_EMPTY", "Semantic qidiruv uchun vector index hali yaratilmagan.")
        if state.status != "ready" or state.dirty:
            raise RagError(409, "VECTOR_INDEX_NOT_READY", "Vector index qayta qurilishi kerak.")
        if not state.active_generation:
            raise RagError(409, "VECTOR_INDEX_CORRUPT", "Faol vector index generation topilmadi.")
        manifest = _read_manifest(_manifest_path(_generation_dir(settings, state.active_generation)))
        index = FaissStore().read(_index_path(_generation_dir(settings, state.active_generation)))
        if manifest.chunk_count != state.chunk_count or manifest.embedding_model != state.embedding_model:
            raise RagError(409, "VECTOR_INDEX_CORRUPT", "Vector index manifesti database holatiga mos emas.")

        owned_model = embedding_model is None
        active_model = embedding_model or SentenceTransformerEmbeddingModel(settings)
        try:
            query_vector = active_model.encode_query(normalized_query)
        finally:
            if owned_model:
                active_model.close()

        allowed_documents = sorted(set(document_ids or []))
        current_k = min(max(top_k, settings.vector_search_top_k), settings.vector_search_max_k)
        max_k = max(current_k, state.chunk_count, 1)
        while current_k <= max_k:
            batch = FaissStore().search(index, query_vector, current_k)
            filtered: list[tuple[int, float]] = []
            seen_batch: set[int] = set()
            for chunk_id, score in batch:
                if chunk_id in seen_batch:
                    continue
                seen_batch.add(chunk_id)
                if score < settings.vector_min_score:
                    continue
                filtered.append((chunk_id, score))
            chunk_map = get_chunks_by_ids(settings, [chunk_id for chunk_id, _ in filtered])
            if len(chunk_map) != len(filtered):
                raise RagError(409, "VECTOR_INDEX_CORRUPT", "Vector indexda eskirgan yoki yo'q chunk ID aniqlandi.")
            results: list[RetrievedChunk] = []
            for chunk_id, score in filtered:
                chunk = chunk_map[chunk_id]
                if allowed_documents and chunk.document_id not in allowed_documents:
                    continue
                results.append(
                    RetrievedChunk(
                        chunk_id=chunk.chunk_id,
                        document_id=chunk.document_id,
                        file_name=chunk.file_name,
                        chunk_index=chunk.chunk_index,
                        text=chunk.text,
                        score=score,
                        start_char=chunk.start_char,
                        end_char=chunk.end_char,
                    )
                )
            if len(results) >= top_k or current_k >= state.chunk_count:
                elapsed = int((perf_counter() - started_at) * 1000)
                return (
                    sorted(results, key=lambda item: item.score, reverse=True)[:top_k],
                    state.active_generation,
                    state.embedding_model or settings.embedding_model_name,
                    elapsed,
                )
            next_k = min(state.chunk_count, current_k * 2)
            if next_k == current_k:
                break
            current_k = next_k

    raise RagError(409, "VECTOR_INDEX_CORRUPT", "Vector qidiruv jarayonini yakunlab bo'lmadi.")
