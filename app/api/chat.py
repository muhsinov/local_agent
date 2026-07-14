import asyncio
import sqlite3
from time import perf_counter

from fastapi import APIRouter, Request

from app.api.errors import ApiError
from app.llm.exceptions import (
    OllamaInvalidResponseError,
    OllamaModelNotFoundError,
    OllamaTimeoutError,
    OllamaUnavailableError,
)
from app.rag.citation import extract_citation_numbers, normalize_citations
from app.rag.exceptions import RagError
from app.rag.prompt_builder import RAG_SYSTEM_PROMPT, build_chat_messages, compute_available_context_chars
from app.rag.rag_service import RagService
from app.schemas.chat import ChatRequest, ChatResponse, UsageSummary
from app.schemas.rag import RagMetadataResponse, RagSourceResponse
from app.services.conversation_service import conversation_exists, get_recent_messages, save_exchange
from app.services.rag_audit_service import write_rag_chat_audit


router = APIRouter(tags=["chat"])


def _database_error() -> ApiError:
    return ApiError(500, "DATABASE_ERROR", "Lokal database operatsiyasini bajarib bo'lmadi.")


@router.post("/chat", response_model=ChatResponse)
async def chat(request: Request, payload: ChatRequest) -> ChatResponse:
    settings = request.app.state.settings
    if len(payload.message) > settings.max_chat_message_chars:
        raise ApiError(
            status_code=422,
            code="VALIDATION_ERROR",
            message=f"Xabar uzunligi {settings.max_chat_message_chars} belgidan oshmasligi kerak.",
        )

    try:
        if payload.conversation_id is not None and not conversation_exists(settings, payload.conversation_id):
            raise ApiError(status_code=404, code="CONVERSATION_NOT_FOUND", message="Conversation topilmadi.")
    except ApiError:
        raise
    except (sqlite3.Error, RuntimeError):
        raise _database_error() from None

    history: list[dict[str, str]] = []
    try:
        if payload.conversation_id is not None:
            history = get_recent_messages(settings, payload.conversation_id, settings.chat_history_messages)
    except (sqlite3.Error, RuntimeError):
        raise _database_error() from None

    rag_enabled = settings.rag_enabled if payload.use_rag is None else payload.use_rag
    rag_service = RagService(settings, request.app.state.vector_operation_coordinator)
    available_context_chars = 0
    if rag_enabled:
        try:
            available_context_chars = compute_available_context_chars(
                system_prompt=RAG_SYSTEM_PROMPT,
                user_message=payload.message,
                max_chars=settings.rag_prompt_max_chars,
            )
        except RagError as exc:
            raise ApiError(exc.status_code, exc.code, exc.message) from exc
    rag_started = perf_counter()
    try:
        rag_result = await rag_service.prepare(
            query=payload.message,
            document_ids=payload.document_ids,
            use_rag=rag_enabled,
            available_context_chars=available_context_chars,
        )
    except RagError as exc:
        raise ApiError(exc.status_code, exc.code, exc.message) from exc
    retrieval_ms = int((perf_counter() - rag_started) * 1000)

    try:
        messages = build_chat_messages(
            user_message=payload.message,
            history=history,
            context_text=rag_result.context.context_text if rag_result.context else None,
            max_chars=settings.rag_prompt_max_chars,
        )
    except RagError as exc:
        raise ApiError(exc.status_code, exc.code, exc.message) from exc

    semaphore = request.app.state.chat_semaphore
    acquired = False
    try:
        await asyncio.wait_for(semaphore.acquire(), timeout=settings.chat_busy_timeout_seconds)
        acquired = True
    except TimeoutError:
        raise ApiError(429, "AGENT_BUSY", "Agent hozir band. Bir ozdan keyin qayta urinib ko'ring.") from None

    client = request.app.state.ollama_client
    started_at = perf_counter()
    try:
        if not await client.is_model_installed(settings.ollama_model):
            raise ApiError(503, "OLLAMA_MODEL_NOT_FOUND", "Kerakli Ollama modeli o'rnatilmagan.")
        result = await client.chat(messages)
        normalized_answer = result.content
        invalid_citations_removed = 0
        citations_present = False
        if rag_result.context is not None:
            normalized_answer, invalid_citations_removed, citations_present = normalize_citations(
                result.content,
                len(rag_result.context.sources),
            )
        conversation_id = save_exchange(
            settings=settings,
            conversation_id=payload.conversation_id,
            user_message=payload.message,
            assistant_message=normalized_answer,
        )
    except ApiError:
        raise
    except OllamaModelNotFoundError:
        raise ApiError(503, "OLLAMA_MODEL_NOT_FOUND", "Kerakli Ollama modeli o'rnatilmagan.") from None
    except OllamaUnavailableError:
        raise ApiError(503, "OLLAMA_UNAVAILABLE", "Ollama serveriga ulanib bo'lmadi.") from None
    except OllamaTimeoutError:
        raise ApiError(504, "OLLAMA_TIMEOUT", "Ollama javobi kutish vaqtidan oshdi.") from None
    except OllamaInvalidResponseError:
        raise ApiError(502, "OLLAMA_INVALID_RESPONSE", "Ollama noto'g'ri javob qaytardi.") from None
    except (sqlite3.Error, RuntimeError):
        raise _database_error() from None
    finally:
        if acquired:
            semaphore.release()

    execution_time_ms = int((perf_counter() - started_at) * 1000)
    sources = rag_result.context.sources if rag_result.context else []
    write_rag_chat_audit(
        settings,
        rag_enabled=rag_enabled,
        rag_used=rag_result.used,
        fallback=rag_result.fallback,
        source_count=len(sources),
        context_chars=rag_result.context.context_chars if rag_result.context else 0,
        retrieval_ms=retrieval_ms,
        citation_count=len(extract_citation_numbers(normalized_answer)),
        invalid_citation_count=invalid_citations_removed,
        generation_id=rag_result.context.generation_id if rag_result.context else None,
    )
    return ChatResponse(
        conversation_id=conversation_id,
        answer=normalized_answer,
        model=settings.ollama_model,
        sources=[RagSourceResponse(**source.__dict__) for source in sources],
        tool_calls=[],
        execution_time_ms=execution_time_ms,
        usage=UsageSummary(
            prompt_tokens=result.usage.prompt_tokens,
            completion_tokens=result.usage.completion_tokens,
        ),
        rag=RagMetadataResponse(
            enabled=rag_enabled,
            used=rag_result.used,
            fallback=rag_result.fallback,
            generation_id=rag_result.context.generation_id if rag_result.context else None,
            retrieved_count=rag_result.context.retrieved_count if rag_result.context else 0,
            context_chars=rag_result.context.context_chars if rag_result.context else 0,
            citations_present=citations_present,
            invalid_citations_removed=invalid_citations_removed,
        ),
    )
