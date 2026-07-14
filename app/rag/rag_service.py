from app.api.errors import ApiError
from app.rag.context_builder import build_rag_context
from app.rag.exceptions import RagError
from app.rag.models import RagPreparationResult
from app.rag.search_service import semantic_search


class RagService:
    def __init__(self, settings, coordinator, search_function=semantic_search) -> None:
        self._settings = settings
        self._coordinator = coordinator
        self._search_function = search_function

    async def prepare(
        self,
        *,
        query: str,
        document_ids: list[int] | None,
        use_rag: bool,
        available_context_chars: int,
    ) -> RagPreparationResult:
        if not use_rag:
            return RagPreparationResult(enabled=False, used=False, fallback=False, context=None)
        retrieval_top_k = min(
            self._settings.rag_max_top_k,
            max(self._settings.rag_top_k, self._settings.rag_max_sources),
        )
        if self._settings.rag_context_overlap_dedup:
            retrieval_top_k = self._settings.rag_max_top_k
        try:
            results, generation_id, _, _ = await self._coordinator.run(
                self._search_function,
                self._settings,
                query=query,
                top_k=retrieval_top_k,
                document_ids=document_ids,
                score_override=self._settings.rag_min_score,
                acquire_timeout_seconds=self._settings.rag_busy_timeout_seconds,
            )
        except TimeoutError as exc:
            if self._settings.rag_allow_fallback_without_index and not self._settings.rag_require_sources:
                return RagPreparationResult(enabled=True, used=False, fallback=True, context=None)
            raise ApiError(429, "VECTOR_INDEX_BUSY", "Vector index hozir band. Keyinroq qayta urinib ko'ring.") from exc
        except RagError as exc:
            if exc.code == "VECTOR_INDEX_CORRUPT":
                raise
            if exc.code in {"VECTOR_INDEX_EMPTY", "VECTOR_INDEX_NOT_READY", "EMBEDDING_MODEL_UNAVAILABLE"}:
                if self._settings.rag_allow_fallback_without_index and not self._settings.rag_require_sources:
                    return RagPreparationResult(enabled=True, used=False, fallback=True, context=None)
            raise

        if not results:
            if self._settings.rag_require_sources:
                raise RagError(422, "RAG_NO_RELEVANT_SOURCES", "Relevant source topilmadi.")
            return RagPreparationResult(enabled=True, used=False, fallback=True, context=None)

        context = build_rag_context(
            chunks=results,
            max_context_chars=min(self._settings.rag_max_context_chars, available_context_chars),
            max_chunk_chars=self._settings.rag_max_chunk_chars,
            max_sources=self._settings.rag_max_sources,
            deduplicate_overlap=self._settings.rag_context_overlap_dedup,
            generation_id=generation_id,
            include_file_name=self._settings.rag_include_file_name,
            include_chunk_index=self._settings.rag_include_chunk_index,
        )
        if not context.sources:
            if self._settings.rag_require_sources:
                raise RagError(422, "RAG_NO_RELEVANT_SOURCES", "Relevant source topilmadi.")
            return RagPreparationResult(enabled=True, used=False, fallback=True, context=None)
        return RagPreparationResult(enabled=True, used=True, fallback=False, context=context)
