import asyncio
from time import perf_counter

from fastapi import APIRouter, Request

from app.api.errors import ApiError
from app.llm.exceptions import (
    OllamaInvalidResponseError,
    OllamaModelNotFoundError,
    OllamaTimeoutError,
    OllamaUnavailableError,
)
from app.llm.ollama_client import SYSTEM_PROMPT
from app.schemas.chat import ChatRequest, ChatResponse, UsageSummary
from app.services.conversation_service import (
    conversation_exists,
    get_recent_messages,
    save_exchange,
)


router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(request: Request, payload: ChatRequest) -> ChatResponse:
    """Send a message to the local Ollama model and persist the exchange."""

    settings = request.app.state.settings
    if len(payload.message) > settings.max_chat_message_chars:
        raise ApiError(
            status_code=422,
            code="VALIDATION_ERROR",
            message=f"Xabar uzunligi {settings.max_chat_message_chars} belgidan oshmasligi kerak.",
        )

    if payload.conversation_id is not None and not conversation_exists(settings, payload.conversation_id):
        raise ApiError(
            status_code=404,
            code="CONVERSATION_NOT_FOUND",
            message="Conversation topilmadi.",
        )

    semaphore = request.app.state.chat_semaphore
    acquired = False
    try:
        await asyncio.wait_for(semaphore.acquire(), timeout=settings.chat_busy_timeout_seconds)
        acquired = True
    except TimeoutError:
        raise ApiError(
            status_code=429,
            code="AGENT_BUSY",
            message="Agent hozir band. Bir ozdan keyin qayta urinib ko'ring.",
        ) from None

    client = request.app.state.ollama_client
    started_at = perf_counter()
    try:
        if not await client.is_model_installed(settings.ollama_model):
            raise ApiError(
                status_code=503,
                code="OLLAMA_MODEL_NOT_FOUND",
                message="Kerakli Ollama modeli o'rnatilmagan.",
            )

        history = []
        if payload.conversation_id is not None:
            history = get_recent_messages(settings, payload.conversation_id, settings.chat_history_messages)

        messages = [{"role": "system", "content": SYSTEM_PROMPT}, *history, {"role": "user", "content": payload.message}]
        result = await client.chat(messages)
        conversation_id = save_exchange(
            settings=settings,
            conversation_id=payload.conversation_id,
            user_message=payload.message,
            assistant_message=result.content,
        )
    except ApiError:
        raise
    except OllamaModelNotFoundError:
        raise ApiError(
            status_code=503,
            code="OLLAMA_MODEL_NOT_FOUND",
            message="Kerakli Ollama modeli o'rnatilmagan.",
        ) from None
    except OllamaUnavailableError:
        raise ApiError(
            status_code=503,
            code="OLLAMA_UNAVAILABLE",
            message="Ollama serveriga ulanib bo'lmadi.",
        ) from None
    except OllamaTimeoutError:
        raise ApiError(
            status_code=504,
            code="OLLAMA_TIMEOUT",
            message="Ollama javobi kutish vaqtidan oshdi.",
        ) from None
    except OllamaInvalidResponseError:
        raise ApiError(
            status_code=502,
            code="OLLAMA_INVALID_RESPONSE",
            message="Ollama noto'g'ri javob qaytardi.",
        ) from None
    finally:
        if acquired:
            semaphore.release()

    execution_time_ms = int((perf_counter() - started_at) * 1000)
    return ChatResponse(
        conversation_id=conversation_id,
        answer=result.content,
        model=settings.ollama_model,
        sources=[],
        tool_calls=[],
        execution_time_ms=execution_time_ms,
        usage=UsageSummary(
            prompt_tokens=result.usage.prompt_tokens,
            completion_tokens=result.usage.completion_tokens,
        ),
    )
