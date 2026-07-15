import asyncio

from fastapi import APIRouter, Request, Response

from app.agent.registry import build_default_registry
from app.approval.errors import ApprovalError
from app.approval.executor import ApprovalExecutor
from app.approval.service import ApprovalService
from app.api.errors import ApiError
from app.llm.exceptions import (
    OllamaInvalidResponseError,
    OllamaModelNotFoundError,
    OllamaTimeoutError,
    OllamaUnavailableError,
)
from app.schemas.approval import ApprovalDecisionRequest, ApprovalDecisionResponse, ApprovalStatusResponse


router = APIRouter(prefix="/approvals", tags=["approvals"])


def _public_status(record) -> ApprovalStatusResponse:
    return ApprovalStatusResponse(
        approval_id=record.id,
        conversation_id=record.conversation_id,
        tool_name=record.tool_name,
        status=record.status,
        safe_summary=record.safe_summary,
        created_at=record.created_at,
        expires_at=record.expires_at,
        completed_at=record.completed_at,
        error_code=record.error_code,
    )


async def _ollama_call(request: Request, messages: list[dict[str, str]]):
    settings = request.app.state.settings
    client = request.app.state.ollama_client
    semaphore = request.app.state.chat_semaphore
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


@router.get("/{approval_id}", response_model=ApprovalStatusResponse)
def get_approval_status(request: Request, approval_id: str) -> ApprovalStatusResponse:
    service = ApprovalService(request.app.state.settings)
    try:
        coordinator = request.app.state.approval_operation_coordinator
        approval = service.get_public(approval_id, coordinator.active_ids())
    except ApprovalError as exc:
        raise ApiError(exc.status_code, exc.code, exc.message) from exc
    return _public_status(approval)


@router.post("/{approval_id}/reject", response_model=ApprovalStatusResponse)
def reject_approval(request: Request, approval_id: str, payload: ApprovalDecisionRequest) -> ApprovalStatusResponse:
    service = ApprovalService(request.app.state.settings)
    origin = request.headers.get("origin") or request.headers.get("referer")
    try:
        coordinator = request.app.state.approval_operation_coordinator
        approval = service.reject(approval_id, payload.nonce, origin, coordinator.active_ids())
    except ApprovalError as exc:
        raise ApiError(exc.status_code, exc.code, exc.message) from exc
    return _public_status(approval)


@router.post("/{approval_id}/approve", response_model=ApprovalDecisionResponse)
async def approve_approval(
    request: Request,
    approval_id: str,
    payload: ApprovalDecisionRequest,
    response: Response,
) -> ApprovalDecisionResponse:
    settings = request.app.state.settings
    service = ApprovalService(settings)
    registry = build_default_registry(settings, request.app.state.vector_operation_coordinator)
    executor = ApprovalExecutor(
        settings,
        registry,
        request.app.state.vector_operation_coordinator,
        request.app.state.approval_operation_coordinator,
    )
    origin = request.headers.get("origin") or request.headers.get("referer")
    try:
        result = await executor.approve(
            approval_id=approval_id,
            nonce=payload.nonce,
            service=service,
            origin_or_referer=origin,
            ollama_call=lambda messages: _ollama_call(request, messages),
        )
    except ApprovalError as exc:
        raise ApiError(exc.status_code, exc.code, exc.message) from exc
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
    approval = result["approval"]
    if approval.status == "executing":
        response.status_code = 202
    return ApprovalDecisionResponse(
        approval_id=approval.id,
        conversation_id=approval.conversation_id,
        tool_name=approval.tool_name,
        status=approval.status,
        safe_summary=approval.safe_summary,
        created_at=approval.created_at,
        expires_at=approval.expires_at,
        completed_at=approval.completed_at,
        error_code=approval.error_code,
        answer=result["answer"],
        conversation_id_result=result["conversation_id"],
    )
