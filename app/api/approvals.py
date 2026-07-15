import asyncio
import json

from fastapi import APIRouter, Request, Response

from app.agent.registry import build_default_registry
from app.approval.errors import ApprovalError
from app.approval.executor import ApprovalExecutor
from app.approval.repository import get_approval_result_message, get_approval_result_sources
from app.approval.service import ApprovalService
from app.api.errors import ApiError
from app.llm.exceptions import (
    OllamaInvalidResponseError,
    OllamaModelNotFoundError,
    OllamaTimeoutError,
    OllamaUnavailableError,
)
from app.schemas.approval import ApprovalDecisionRequest, ApprovalResultResponse, ApprovalStatusResponse
from app.schemas.rag import RagMetadataResponse, RagSourceResponse
from app.services.audit_service import write_audit_log


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


def _result_response(settings, result) -> ApprovalResultResponse:
    approval = result["approval"]
    rag_result = result.get("rag_result")
    usage = result.get("usage")
    if rag_result is not None:
        context = rag_result.context
        sources = [RagSourceResponse(**source.__dict__) for source in context.sources] if context else []
        rag = RagMetadataResponse(
            enabled=rag_result.enabled,
            used=bool(context and context.sources),
            fallback=rag_result.fallback,
            generation_id=context.generation_id if context else None,
            retrieved_count=context.retrieved_count if context else 0,
            context_chars=context.context_chars if context else 0,
            citations_present=rag_result.citations_present,
            invalid_citations_removed=rag_result.invalid_citations_removed,
        )
    else:
        sources_data = get_approval_result_sources(settings, approval)
        sources = [RagSourceResponse(**source) for source in sources_data]
        try:
            metadata = json.loads(approval.execution_result_json or "{}")
        except json.JSONDecodeError:
            metadata = {}
        rag = RagMetadataResponse(
            enabled=approval.use_rag,
            used=bool(sources),
            fallback=approval.use_rag and not sources,
            generation_id=metadata.get("generation_id"),
            retrieved_count=len(sources),
            context_chars=0,
            citations_present=bool(metadata.get("citations_present", False)),
            invalid_citations_removed=int(metadata.get("invalid_citations_removed", 0)),
        )
    return ApprovalResultResponse(
        approval_id=approval.id,
        status=approval.status,
        conversation_id=result.get("conversation_id", approval.conversation_id),
        answer=result.get("answer"),
        sources=sources,
        rag=rag,
        usage={
            "prompt_tokens": usage.prompt_tokens if usage else None,
            "completion_tokens": usage.completion_tokens if usage else None,
        },
        error_code=approval.error_code,
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


@router.post("/{approval_id}/approve", response_model=ApprovalResultResponse)
async def approve_approval(
    request: Request,
    approval_id: str,
    payload: ApprovalDecisionRequest,
    response: Response,
) -> ApprovalResultResponse:
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
    return _result_response(settings, result)


@router.post("/{approval_id}/result", response_model=ApprovalResultResponse)
def get_approval_result(
    request: Request,
    approval_id: str,
    payload: ApprovalDecisionRequest,
    response: Response,
) -> ApprovalResultResponse:
    settings = request.app.state.settings
    service = ApprovalService(settings)
    coordinator = request.app.state.approval_operation_coordinator
    origin = request.headers.get("origin") or request.headers.get("referer")
    try:
        approval = service.validate_nonce_and_origin(approval_id, payload.nonce, origin, coordinator.active_ids())
    except ApprovalError as exc:
        raise ApiError(exc.status_code, exc.code, exc.message) from exc
    if approval.status == "pending":
        raise ApiError(409, "APPROVAL_NOT_PENDING", "Approval hali bajarilmagan.")
    if approval.status == "expired":
        raise ApiError(409, "APPROVAL_EXPIRED", "Approval muddati tugagan.")
    if approval.status in {"failed", "rejected"}:
        raise ApiError(409, "APPROVAL_ALREADY_USED", "Approval avval yakunlangan.")
    if approval.status == "executing":
        response.status_code = 202
        write_audit_log(
            settings,
            action="approval_result",
            status="executing",
            arguments={
                "approval_id": approval.id,
                "tool_name": approval.tool_name,
                "conversation_id": approval.conversation_id,
                "status": "executing",
            },
        )
        return _result_response(settings, {"approval": approval, "answer": None, "conversation_id": approval.conversation_id})
    answer = get_approval_result_message(settings, approval)
    if answer is None:
        raise ApiError(500, "APPROVAL_RESULT_UNAVAILABLE", "Approval final javobi topilmadi.")
    write_audit_log(
        settings,
        action="approval_result",
        status="executed",
        arguments={
            "approval_id": approval.id,
            "tool_name": approval.tool_name,
            "conversation_id": approval.conversation_id,
            "status": "executed",
            "result_count": len(get_approval_result_sources(settings, approval)),
        },
    )
    return _result_response(
        settings,
        {"approval": approval, "answer": answer, "conversation_id": approval.conversation_id},
    )
