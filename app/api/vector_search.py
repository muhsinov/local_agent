import sqlite3

from fastapi import APIRouter, Request

from app.api.errors import ApiError
from app.rag.exceptions import RagError
from app.rag.index_manager import get_vector_index_status, rebuild_vector_index
from app.rag.operation_coordinator import VectorOperationCoordinator
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


def _get_coordinator(request: Request) -> VectorOperationCoordinator:
    return request.app.state.vector_operation_coordinator


async def _run_vector_operation(request: Request, function, *args, **kwargs):
    settings = request.app.state.settings
    coordinator = _get_coordinator(request)
    if coordinator.is_busy():
        raise ApiError(429, "VECTOR_INDEX_BUSY", "Vector index hozir band. Keyinroq qayta urinib ko'ring.")
    try:
        return await coordinator.run(
            function,
            *args,
            acquire_timeout_seconds=settings.vector_index_busy_timeout_seconds,
            **kwargs,
        )
    except TimeoutError as exc:
        raise ApiError(429, "VECTOR_INDEX_BUSY", "Vector index hozir band. Keyinroq qayta urinib ko'ring.") from exc


def _map_database_error() -> ApiError:
    return ApiError(500, "DATABASE_ERROR", "Lokal database operatsiyasini bajarib bo'lmadi.")


@router.post("/documents/{document_id}/index", response_model=VectorIndexRebuildResponse)
async def index_document(request: Request, document_id: int) -> VectorIndexRebuildResponse:
    settings = request.app.state.settings
    if not settings.direct_vector_mutations_enabled:
        write_audit_log(settings, action="direct_action_denied", status="DIRECT_ACTION_DISABLED", arguments={"document_id": document_id})
        raise ApiError(403, "DIRECT_ACTION_DISABLED", "Direct vector mutation o'chirilgan.")
    try:
        document = get_document(settings, document_id)
    except sqlite3.Error:
        raise _map_database_error() from None
    if document is None:
        raise ApiError(404, "DOCUMENT_NOT_FOUND", "Hujjat topilmadi.")
    if document.status != "ready" or document.char_count <= 0 or not document.text_path:
        raise ApiError(422, "DOCUMENT_HAS_NO_TEXT", "Tanlangan hujjat indexlash uchun tayyor emas.")

    try:
        state = await _run_vector_operation(request, rebuild_vector_index, settings, requested_document_id=document_id)
    except ApiError:
        raise
    except RagError as exc:
        _raise_rag_error(exc)
    except sqlite3.Error:
        raise _map_database_error() from None
    except Exception:
        raise ApiError(500, "VECTOR_INDEX_ERROR", "Vector index operation bajarilmadi.") from None

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


@router.post("/vector-index/rebuild", response_model=VectorIndexRebuildResponse)
async def rebuild_index(request: Request) -> VectorIndexRebuildResponse:
    settings = request.app.state.settings
    if not settings.direct_vector_mutations_enabled:
        write_audit_log(settings, action="direct_action_denied", status="DIRECT_ACTION_DISABLED", arguments={})
        raise ApiError(403, "DIRECT_ACTION_DISABLED", "Direct vector mutation o'chirilgan.")
    try:
        state = await _run_vector_operation(request, rebuild_vector_index, settings)
    except ApiError:
        raise
    except RagError as exc:
        _raise_rag_error(exc)
    except sqlite3.Error:
        raise _map_database_error() from None
    except Exception:
        raise ApiError(500, "VECTOR_INDEX_ERROR", "Vector index operation bajarilmadi.") from None

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


@router.get("/vector-index/status", response_model=VectorIndexStatusResponse)
def vector_index_status(request: Request) -> VectorIndexStatusResponse:
    settings = request.app.state.settings
    try:
        state = get_vector_index_status(settings)
    except sqlite3.Error:
        raise _map_database_error() from None
    except RagError as exc:
        _raise_rag_error(exc)
    except Exception:
        raise ApiError(500, "VECTOR_INDEX_ERROR", "Vector index statusini olib bo'lmadi.") from None
    return VectorIndexStatusResponse(**state.__dict__)


@router.post("/vector-search", response_model=VectorSearchResponse)
async def vector_search(request: Request, payload: VectorSearchRequest) -> VectorSearchResponse:
    settings = request.app.state.settings
    if payload.top_k > settings.vector_search_max_k:
        raise ApiError(422, "VALIDATION_ERROR", "top_k ruxsat etilgan qiymatdan oshdi.")

    try:
        results, generation_id, model_name, execution_time_ms = await _run_vector_operation(
            request,
            semantic_search,
            settings,
            query=payload.query,
            top_k=payload.top_k,
            document_ids=payload.document_ids,
        )
    except ApiError:
        raise
    except RagError as exc:
        _raise_rag_error(exc)
    except sqlite3.Error:
        raise _map_database_error() from None
    except Exception:
        raise ApiError(500, "VECTOR_SEARCH_ERROR", "Semantic qidiruvni bajarib bo'lmadi.") from None

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
