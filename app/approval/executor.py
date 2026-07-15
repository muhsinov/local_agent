import asyncio
import json
import sqlite3
from time import perf_counter

from app.agent.errors import AgentError
from app.api.errors import ApiError
from app.approval.errors import ApprovalError
from app.approval.operation_coordinator import ApprovalOperationCoordinator
from app.approval.repository import finalize_approval, get_approval, get_approval_result_message, mark_executing
from app.approval.resume_service import ApprovalResumeService
from app.approval.security import canonicalize_arguments, hash_text
from app.rag.exceptions import RagError
from app.rag.rag_service import RagService
from app.services.audit_service import write_audit_log
from app.services.conversation_service import save_exchange_and_finalize_approval


class ApprovalExecutor:
    def __init__(self, settings, registry, vector_coordinator, approval_coordinator=None) -> None:
        self._settings = settings
        self._registry = registry
        self._vector_coordinator = vector_coordinator
        self._coordinator = approval_coordinator or ApprovalOperationCoordinator()

    async def approve(self, *, approval_id: str, nonce: str, service, origin_or_referer: str | None, ollama_call):
        approval = service.validate_nonce_and_origin(
            approval_id,
            nonce,
            origin_or_referer,
            self._coordinator.active_ids(),
        )
        affected = mark_executing(self._settings, approval_id)
        if affected != 1:
            refreshed = get_approval(self._settings, approval_id)
            if refreshed is None:
                raise ApprovalError(404, "APPROVAL_NOT_FOUND", "Approval topilmadi.")
            if refreshed.status == "expired":
                raise ApprovalError(409, "APPROVAL_EXPIRED", "Approval muddati tugagan.")
            if refreshed.status == "executing":
                return {"approval": refreshed, "answer": None, "conversation_id": refreshed.conversation_id}
            if refreshed.status in {"executed", "rejected", "failed"}:
                raise ApprovalError(409, "APPROVAL_ALREADY_USED", "Approval avval ishlatilgan.")
            raise ApprovalError(409, "APPROVAL_NOT_PENDING", "Approval pending holatda emas.")

        started = perf_counter()
        starter = asyncio.create_task(
            self._coordinator.start_or_join(
                approval_id=approval.id,
                operation_factory=lambda: self._execute_lifecycle(approval, ollama_call, started),
            )
        )
        starter.add_done_callback(self._consume_start_result)
        try:
            task = await asyncio.shield(starter)
            result = await asyncio.wait_for(
                asyncio.shield(task),
                timeout=self._settings.approval_execution_timeout_seconds,
            )
            return result
        except TimeoutError:
            if task.done():
                return task.result()
            current = get_approval(self._settings, approval.id)
            if current is not None and current.status == "executed":
                return {
                    "approval": current,
                    "conversation_id": current.conversation_id,
                    "answer": get_approval_result_message(self._settings, current),
                    "usage": None,
                    "rag_result": None,
                }
            write_audit_log(
                self._settings,
                action="approval_execute",
                status="executing",
                arguments={
                    "approval_id": approval.id,
                    "tool_name": approval.tool_name,
                    "conversation_id": approval.conversation_id,
                    "status": "executing",
                    "argument_hash_prefix": approval.arguments_sha256[:12],
                },
                execution_time_ms=int((perf_counter() - started) * 1000),
            )
            return {"approval": current or approval, "answer": None, "conversation_id": approval.conversation_id}
        except asyncio.CancelledError:
            raise

    @staticmethod
    def _consume_start_result(task: asyncio.Task) -> None:
        try:
            task.result()
        except BaseException:
            pass

    async def _execute_lifecycle(self, approval, ollama_call, started: float):
        try:
            tool = self._registry.get(approval.tool_name)
            arguments_json = json.loads(approval.arguments_json)
            canonical = canonicalize_arguments(arguments_json)
            if hash_text(canonical) != approval.arguments_sha256:
                raise ApprovalError(409, "APPROVAL_ARGUMENTS_MISMATCH", "Approval argumentlari mos emas.")
            arguments = tool.input_model.model_validate(arguments_json)
            action_result = await tool.execute_with_approval(
                arguments,
                self._settings,
                coordinator=self._vector_coordinator,
            )
            resume = ApprovalResumeService(self._settings, RagService(self._settings, self._vector_coordinator))
            final_answer, usage, rag_result = await resume.build_final_answer(
                approval=approval,
                action_result_text=action_result,
                ollama_call=ollama_call,
            )
            conversation_id = save_exchange_and_finalize_approval(
                self._settings,
                approval_id=approval.id,
                conversation_id=approval.conversation_id,
                user_message=approval.original_user_message,
                assistant_message=final_answer,
                execution_result={
                    "ok": True,
                    "generation_id": rag_result.context.generation_id if rag_result.context else None,
                    "source_chunk_ids": [source.chunk_id for source in rag_result.context.sources] if rag_result.context else [],
                    "citation_order": [source.chunk_id for source in rag_result.context.sources] if rag_result.context else [],
                    "prompt_tokens": usage.prompt_tokens,
                    "completion_tokens": usage.completion_tokens,
                    "invalid_citations_removed": rag_result.invalid_citations_removed,
                    "citations_present": rag_result.citations_present,
                },
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
        except asyncio.CancelledError:
            finalize_approval(
                self._settings,
                approval_id=approval.id,
                status="failed",
                error_code="APPROVAL_EXECUTION_INTERRUPTED",
            )
            raise
        except ApprovalError as exc:
            finalize_approval(self._settings, approval_id=approval.id, status="failed", error_code=exc.code)
            raise
        except AgentError as exc:
            finalize_approval(self._settings, approval_id=approval.id, status="failed", error_code=exc.code)
            raise ApprovalError(exc.status_code, exc.code, exc.message) from exc
        except RagError as exc:
            finalize_approval(self._settings, approval_id=approval.id, status="failed", error_code=exc.code)
            raise ApprovalError(exc.status_code, exc.code, exc.message) from exc
        except ApiError as exc:
            finalize_approval(self._settings, approval_id=approval.id, status="failed", error_code=exc.code)
            raise ApprovalError(exc.status_code, exc.code, exc.message) from exc
        except sqlite3.Error as exc:
            finalize_approval(self._settings, approval_id=approval.id, status="failed", error_code="DATABASE_ERROR")
            raise ApprovalError(500, "DATABASE_ERROR", "Lokal database operatsiyasini bajarib bo'lmadi.") from exc
        except Exception as exc:
            finalize_approval(
                self._settings,
                approval_id=approval.id,
                status="failed",
                error_code="APPROVAL_EXECUTION_ERROR",
            )
            raise ApprovalError(500, "APPROVAL_EXECUTION_ERROR", "Approval bajarilmadi.") from exc
