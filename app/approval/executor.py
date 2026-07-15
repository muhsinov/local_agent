import asyncio
import json
import sqlite3
from time import perf_counter

from app.agent.errors import AgentError
from app.approval.errors import ApprovalError
from app.approval.repository import finalize_approval, get_approval, mark_executing
from app.approval.resume_service import ApprovalResumeService, render_approved_action_result
from app.approval.security import canonicalize_arguments, hash_text
from app.rag.rag_service import RagService
from app.services.audit_service import write_audit_log
from app.services.conversation_service import save_exchange


class ApprovalExecutor:
    def __init__(self, settings, registry, vector_coordinator) -> None:
        self._settings = settings
        self._registry = registry
        self._vector_coordinator = vector_coordinator

    async def approve(self, *, approval_id: str, nonce: str, service, origin_or_referer: str | None, ollama_call):
        approval = service.validate_nonce_and_origin(approval_id, nonce, origin_or_referer)
        affected = mark_executing(self._settings, approval_id)
        if affected != 1:
            refreshed = get_approval(self._settings, approval_id)
            if refreshed is None:
                raise ApprovalError(404, "APPROVAL_NOT_FOUND", "Approval topilmadi.")
            if refreshed.status == "expired":
                raise ApprovalError(409, "APPROVAL_EXPIRED", "Approval muddati tugagan.")
            if refreshed.status in {"executed", "rejected", "failed"}:
                raise ApprovalError(409, "APPROVAL_ALREADY_USED", "Approval avval ishlatilgan.")
            raise ApprovalError(409, "APPROVAL_NOT_PENDING", "Approval pending holatda emas.")

        started = perf_counter()
        tool = self._registry.get(approval.tool_name)
        try:
            if hash_text(canonicalize_arguments(json.loads(approval.arguments_json))) != approval.arguments_sha256:
                raise ApprovalError(409, "APPROVAL_ARGUMENTS_MISMATCH", "Approval argumentlari mos emas.")
            arguments = tool.input_model.model_validate(json.loads(approval.arguments_json))
            execute_timeout = min(self._settings.approval_execution_timeout_seconds, tool.definition.timeout_seconds)
            action_result = await asyncio.wait_for(
                tool.execute_with_approval(arguments, self._settings, coordinator=self._vector_coordinator),
                timeout=execute_timeout,
            )
            result_block = render_approved_action_result(
                approval_id=approval.id,
                tool_name=approval.tool_name,
                content=action_result,
                ok=True,
            )
            resume = ApprovalResumeService(self._settings, RagService(self._settings, self._vector_coordinator))
            final_answer, usage, rag_result = await resume.build_final_answer(
                approval=approval,
                action_result_text=result_block,
                ollama_call=ollama_call,
            )
            conversation_id = save_exchange(
                settings=self._settings,
                conversation_id=approval.conversation_id,
                user_message=approval.original_user_message,
                assistant_message=final_answer,
            )
            finalize_approval(
                self._settings,
                approval_id=approval.id,
                status="executed",
                execution_result={"ok": True},
            )
            write_audit_log(
                self._settings,
                action="approval_execute",
                status="executed",
                arguments={
                    "approval_id": approval.id,
                    "tool_name": approval.tool_name,
                    "conversation_id": conversation_id,
                    "status": "executed",
                    "argument_hash_prefix": approval.arguments_sha256[:12],
                    "execution_time_ms": int((perf_counter() - started) * 1000),
                },
                execution_time_ms=int((perf_counter() - started) * 1000),
            )
            return {
                "approval": get_approval(self._settings, approval.id),
                "conversation_id": conversation_id,
                "answer": final_answer,
                "usage": usage,
                "rag_result": rag_result,
            }
        except ApprovalError as exc:
            finalize_approval(self._settings, approval_id=approval.id, status="failed", error_code=exc.code)
            raise
        except AgentError as exc:
            finalize_approval(self._settings, approval_id=approval.id, status="failed", error_code=exc.code)
            raise ApprovalError(exc.status_code, exc.code, exc.message) from exc
        except TimeoutError as exc:
            finalize_approval(
                self._settings,
                approval_id=approval.id,
                status="failed",
                error_code="APPROVAL_EXECUTION_TIMEOUT",
            )
            raise ApprovalError(504, "APPROVAL_EXECUTION_TIMEOUT", "Approval bajarilishi timeout bo'ldi.") from exc
        except sqlite3.Error as exc:
            finalize_approval(self._settings, approval_id=approval.id, status="failed", error_code="DATABASE_ERROR")
            raise ApprovalError(500, "DATABASE_ERROR", "Lokal database operatsiyasini bajarib bo'lmadi.") from exc
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            finalize_approval(
                self._settings,
                approval_id=approval.id,
                status="failed",
                error_code="APPROVAL_EXECUTION_ERROR",
            )
            raise ApprovalError(500, "APPROVAL_EXECUTION_ERROR", "Approval bajarilmadi.") from exc
