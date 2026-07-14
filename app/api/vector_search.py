import asyncio

from fastapi import APIRouter, Request

from app.api.errors import ApiError
from app.rag.exceptions import RagError
from app.rag.index_manager import get_vector_index_status, rebuild_vector_index
from app.rag.search_service import semantic_search
from app.schemas.vector_search import (
    VectorIndexRebuildResponse,
    VectorIndexStatusResponse,
    VectorSearchRequest,
    VectorSearchResponse,
    VectorSearchResultResponse,
)
from app.services.audit_service import write_audit_log
from app.services.document_service import get_document


router = APIRouter(tags=["vector"])


def _raise_rag_error(exc: RagError) -> None:
    raise ApiError(exc.status_code, exc.code, exc.message) from exc


async def _acquire(semaphore, timeout_seconds: int) -> None:
    try:
        await asyncio.wait_for(semaphore.acquire(), timeout=timeout_seconds)
    except TimeoutError as exc:
        raise ApiError(429, "VECTOR_INDEX_BUSY", "Vector index hozir band. Keyinroq qayta urinib ko'ring.") from exc


@router.post("/documents/{document_id}/index", response_model=VectorIndexRebuildResponse)
async def index_document(request: Request, document_id: int) -> VectorIndexRebuildResponse:
    settings = request.app.state.settings
    document = get_document(settings, document_id)
    if document is None:
        raise ApiError(404, "DOCUMENT_NOT_FOUND", "Hujjat topilmadi.")
    if document.status != "ready" or document.char_count <= 0 or not document.text_path:
        raise ApiError(422, "DOCUMENT_HAS_NO_TEXT", "Tanlangan hujjat indexlash uchun tayyor emas.")
    semaphore = request.app.state.vector_index_semaphore
    await _acquire(semaphore, settings.vector_index_busy_timeout_seconds)
    try:
        try:
            state = await asyncio.to_thread(rebuild_vector_index, settings, requested_document_id=document_id)
        except RagError as exc:
            _raise_rag_error(exc)
        write_audit_log(
            settings,
            action="vector_index_rebuild",
            status=state.status,
            arguments={
                "generation_id": state.active_generation,
                "document_count": state.document_count,
                "chunk_count": state.chunk_count,
                "embedding_model": state.embedding_model,
                "embedding_dimension": state.embedding_dimension,
                "status": state.status,
            },
        )
        return VectorIndexRebuildResponse(generation_id=state.active_generation, **state.__dict__)
    finally:
        semaphore.release()


@router.post("/vector-index/rebuild", response_model=VectorIndexRebuildResponse)
async def rebuild_index(request: Request) -> VectorIndexRebuildResponse:
    settings = request.app.state.settings
    semaphore = request.app.state.vector_index_semaphore
    await _acquire(semaphore, settings.vector_index_busy_timeout_seconds)
    try:
        try:
            state = await asyncio.to_thread(rebuild_vector_index, settings)
        except RagError as exc:
            _raise_rag_error(exc)
        write_audit_log(
            settings,
            action="vector_index_rebuild",
            status=state.status,
            arguments={
                "generation_id": state.active_generation,
                "document_count": state.document_count,
                "chunk_count": state.chunk_count,
                "embedding_model": state.embedding_model,
                "embedding_dimension": state.embedding_dimension,
                "status": state.status,
            },
        )
        return VectorIndexRebuildResponse(generation_id=state.active_generation, **state.__dict__)
    finally:
        semaphore.release()


@router.get("/vector-index/status", response_model=VectorIndexStatusResponse)
def vector_index_status(request: Request) -> VectorIndexStatusResponse:
    settings = request.app.state.settings
    state = get_vector_index_status(settings)
    return VectorIndexStatusResponse(**state.__dict__)


@router.post("/vector-search", response_model=VectorSearchResponse)
async def vector_search(request: Request, payload: VectorSearchRequest) -> VectorSearchResponse:
    settings = request.app.state.settings
    if payload.top_k > settings.vector_search_max_k:
        raise ApiError(422, "VALIDATION_ERROR", "top_k ruxsat etilgan qiymatdan oshdi.")
    semaphore = request.app.state.vector_index_semaphore
    await _acquire(semaphore, settings.vector_index_busy_timeout_seconds)
    try:
        try:
            results, generation_id, model_name, execution_time_ms = await asyncio.to_thread(
                semantic_search,
                settings,
                query=payload.query,
                top_k=payload.top_k,
                document_ids=payload.document_ids,
            )
        except RagError as exc:
            _raise_rag_error(exc)
        write_audit_log(
            settings,
            action="vector_search",
            status="ok",
            arguments={
                "result_count": len(results),
                "top_k": payload.top_k,
                "filtered_document_count": len(payload.document_ids or []),
                "execution_time_ms": execution_time_ms,
            },
            execution_time_ms=execution_time_ms,
        )
        return VectorSearchResponse(
            query=payload.query.strip(),
            results=[VectorSearchResultResponse(**result.__dict__) for result in results],
            generation_id=generation_id,
            embedding_model=model_name,
            execution_time_ms=execution_time_ms,
        )
    finally:
        semaphore.release()
