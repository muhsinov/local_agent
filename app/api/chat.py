import asyncio
import sqlite3
from time import perf_counter

from fastapi import APIRouter, Request

from app.agent.errors import AgentError
from app.agent.loop import AgentLoop
from app.agent.policy import ToolPolicy
from app.agent.prompt import TOOL_AGENT_SYSTEM_PROMPT, render_tool_definitions
from app.agent.registry import build_default_registry
from app.api.errors import ApiError
from app.llm.ollama_client import SYSTEM_PROMPT
from app.llm.exceptions import (
    OllamaInvalidResponseError,
    OllamaModelNotFoundError,
    OllamaTimeoutError,
    OllamaUnavailableError,
)
from app.rag.citation import extract_citation_numbers, normalize_citations
from app.rag.exceptions import RagError
from app.rag.prompt_builder import RAG_SYSTEM_PROMPT, build_chat_messages, calculate_prompt_budget
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
    registry = build_default_registry(settings, request.app.state.vector_operation_coordinator)
    policy = ToolPolicy(settings, registry)
    try:
        use_tools = policy.should_use_tools(message=payload.message, use_tools=payload.use_tools)
    except AgentError as exc:
        raise ApiError(exc.status_code, exc.code, exc.message) from exc
    system_prompt = TOOL_AGENT_SYSTEM_PROMPT if use_tools else (RAG_SYSTEM_PROMPT if rag_enabled else SYSTEM_PROMPT)
    rag_service = RagService(settings, request.app.state.vector_operation_coordinator)
    try:
        prompt_budget = calculate_prompt_budget(
            system_prompt=system_prompt,
            user_message=payload.message,
            configured_prompt_max_chars=settings.rag_prompt_max_chars,
            ollama_num_ctx=settings.ollama_num_ctx,
            reserved_answer_tokens=max(settings.rag_reserved_answer_tokens, settings.ollama_num_predict),
            chars_per_token_estimate=settings.rag_chars_per_token_estimate,
            reserve_document_wrapper=rag_enabled,
        )
    except RagError as exc:
        raise ApiError(exc.status_code, exc.code, exc.message) from exc
    available_context_chars = prompt_budget.available_context_chars
    if use_tools:
        available_context_chars = max(0, available_context_chars - len(render_tool_definitions(registry.definitions())))
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

    client = request.app.state.ollama_client
    semaphore = request.app.state.chat_semaphore

    async def ollama_call(messages: list[dict[str, str]]):
        acquired = False
        try:
            await asyncio.wait_for(semaphore.acquire(), timeout=settings.chat_busy_timeout_seconds)
            acquired = True
        except TimeoutError:
            raise ApiError(429, "AGENT_BUSY", "Agent hozir band. Bir ozdan keyin qayta urinib ko'ring.") from None
        try:
            if not await client.is_model_installed(settings.ollama_model):
                raise ApiError(503, "OLLAMA_MODEL_NOT_FOUND", "Kerakli Ollama modeli o'rnatilmagan.")
            return await client.chat(messages)
        finally:
            if acquired:
                semaphore.release()

    started_at = perf_counter()
    tool_call_summaries: list[dict] = []
    returned_sources = rag_result.context.sources if rag_result.context else []
    rag_generation_id = rag_result.context.generation_id if rag_result.context else None
    rag_context_chars = rag_result.context.context_chars if rag_result.context else 0
    rag_retrieved_count = rag_result.context.retrieved_count if rag_result.context else 0
    try:
        if use_tools:
            loop = AgentLoop(settings, registry, policy)
            try:
                agent_result = await loop.run(
                    user_message=payload.message,
                    history=history,
                    context_text=rag_result.context.context_text if rag_result.context else None,
                    max_input_chars=prompt_budget.max_input_chars,
                    ollama_call=ollama_call,
                )
            except AgentError as exc:
                raise ApiError(exc.status_code, exc.code, exc.message) from exc
            normalized_answer = agent_result.answer
            result_prompt_tokens = agent_result.prompt_tokens
            result_completion_tokens = agent_result.completion_tokens
            if not agent_result.rag_context_included:
                returned_sources = []
                rag_generation_id = None
                rag_context_chars = 0
                rag_retrieved_count = 0
            tool_call_summaries = [
                {
                    "id": item.id,
                    "name": item.name,
                    "ok": item.ok,
                    "execution_time_ms": item.execution_time_ms,
                    "iteration": item.iteration,
                    "error_code": item.error_code,
                }
                for item in agent_result.tool_calls
            ]
        else:
            try:
                messages = build_chat_messages(
                    system_prompt=RAG_SYSTEM_PROMPT if rag_result.context else system_prompt,
                    user_message=payload.message,
                    history=history,
                    context_text=rag_result.context.context_text if rag_result.context else None,
                    max_chars=prompt_budget.max_input_chars,
                )
            except RagError as exc:
                raise ApiError(exc.status_code, exc.code, exc.message) from exc
            result = await ollama_call(messages)
            normalized_answer = result.content
            result_prompt_tokens = result.usage.prompt_tokens
            result_completion_tokens = result.usage.completion_tokens

        invalid_citations_removed = 0
        citations_present = False
        if returned_sources:
            normalized_answer, invalid_citations_removed, citations_present = normalize_citations(
                normalized_answer,
                len(returned_sources),
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

    execution_time_ms = int((perf_counter() - started_at) * 1000)
    sources = returned_sources
    write_rag_chat_audit(
        settings,
        rag_enabled=rag_enabled,
        rag_used=bool(sources),
        fallback=rag_result.fallback,
        source_count=len(sources),
        context_chars=rag_context_chars,
        retrieval_ms=retrieval_ms,
        citation_count=len(extract_citation_numbers(normalized_answer)),
        invalid_citation_count=invalid_citations_removed,
        generation_id=rag_generation_id,
        prompt_input_chars=0 if use_tools else sum(len(message["content"]) for message in messages),
        prompt_input_limit_chars=prompt_budget.max_input_chars,
        reserved_answer_chars=prompt_budget.reserved_answer_chars,
    )
    return ChatResponse(
        conversation_id=conversation_id,
        answer=normalized_answer,
        model=settings.ollama_model,
        sources=[RagSourceResponse(**source.__dict__) for source in sources],
        tool_calls=tool_call_summaries,
        execution_time_ms=execution_time_ms,
        usage=UsageSummary(
            prompt_tokens=result_prompt_tokens,
            completion_tokens=result_completion_tokens,
        ),
        rag=RagMetadataResponse(
            enabled=rag_enabled,
            used=bool(sources),
            fallback=rag_result.fallback,
            generation_id=rag_generation_id,
            retrieved_count=rag_retrieved_count,
            context_chars=rag_context_chars,
            citations_present=citations_present,
            invalid_citations_removed=invalid_citations_removed,
        ),
    )
