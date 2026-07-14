import asyncio
import multiprocessing
import time
from dataclasses import asdict
from multiprocessing.connection import Connection
from pathlib import Path
from typing import Any, Callable

import psutil

from app.api.errors import ApiError
from app.config import Settings
from app.documents.extractor import extract_document
from app.documents.models import ExtractedDocument


ProcessFactory = Callable[..., multiprocessing.process.BaseProcess]
MemoryReader = Callable[[int], int | None]
SleepAwaitable = Callable[[float], Any]

_PROCESSING_MESSAGE = "Hujjatni qayta ishlashda xatolik yuz berdi."
_TIMEOUT_MESSAGE = "Hujjatni qayta ishlash vaqti tugadi."
_MEMORY_MESSAGE = "Hujjatni qayta ishlash xotira limitidan oshdi."
_ALLOWED_STATUSES = {"ready", "no_text"}


def _worker_main(connection: Connection, file_path: str, file_type: str, settings_data: dict[str, Any]) -> None:
    """Run extraction in a spawned child process and send a safe result back."""

    try:
        settings = Settings(**settings_data)
        extracted = extract_document(Path(file_path), file_type, settings)
        connection.send({"ok": True, "result": asdict(extracted)})
    except ApiError as exc:
        connection.send(
            {
                "ok": False,
                "error": {
                    "status_code": exc.status_code,
                    "code": exc.code,
                    "message": exc.message,
                    "extra": exc.extra,
                },
            }
        )
    except Exception:
        connection.send(
            {
                "ok": False,
                "error": {
                    "status_code": 500,
                    "code": "DOCUMENT_PROCESSING_ERROR",
                    "message": _PROCESSING_MESSAGE,
                    "extra": None,
                },
            }
        )
    finally:
        connection.close()


def _default_memory_reader(pid: int) -> int | None:
    """Return the child RSS in bytes when available."""

    try:
        return int(psutil.Process(pid).memory_info().rss)
    except (psutil.Error, ProcessLookupError):
        return None


def _safe_processing_error() -> ApiError:
    return ApiError(500, "DOCUMENT_PROCESSING_ERROR", _PROCESSING_MESSAGE)


def _parse_extracted_document_payload(payload: Any) -> ExtractedDocument:
    if not isinstance(payload, dict):
        raise _safe_processing_error()
    text = payload.get("text")
    char_count = payload.get("char_count")
    page_count = payload.get("page_count")
    status = payload.get("status")
    warning_code = payload.get("warning_code")
    if not isinstance(text, str):
        raise _safe_processing_error()
    if not isinstance(char_count, int) or char_count < 0 or char_count != len(text):
        raise _safe_processing_error()
    if status not in _ALLOWED_STATUSES:
        raise _safe_processing_error()
    if page_count is not None and (not isinstance(page_count, int) or page_count < 0):
        raise _safe_processing_error()
    if warning_code is not None and not isinstance(warning_code, str):
        raise _safe_processing_error()
    return ExtractedDocument(
        text=text,
        char_count=char_count,
        page_count=page_count,
        status=status,
        warning_code=warning_code,
    )


def _parse_api_error_payload(payload: Any) -> ApiError:
    if not isinstance(payload, dict):
        raise _safe_processing_error()
    status_code = payload.get("status_code")
    code = payload.get("code")
    message = payload.get("message")
    extra = payload.get("extra")
    if not isinstance(status_code, int) or not isinstance(code, str) or not isinstance(message, str):
        raise _safe_processing_error()
    if extra is not None and not isinstance(extra, dict):
        raise _safe_processing_error()
    return ApiError(status_code, code, message, extra)


def _parse_worker_payload(payload: Any) -> ExtractedDocument:
    if not isinstance(payload, dict):
        raise _safe_processing_error()
    ok = payload.get("ok")
    if not isinstance(ok, bool):
        raise _safe_processing_error()
    if ok:
        return _parse_extracted_document_payload(payload.get("result"))
    raise _parse_api_error_payload(payload.get("error"))


class ExtractionSupervisor:
    """Supervise the spawned extraction worker with shared sync/async logic."""

    def __init__(
        self,
        file_path: Path,
        file_type: str,
        settings: Settings,
        *,
        process_factory: ProcessFactory | None = None,
        memory_reader: MemoryReader | None = None,
    ) -> None:
        context = multiprocessing.get_context("spawn")
        parent_connection, child_connection = context.Pipe(duplex=False)
        process_builder = process_factory or context.Process
        self.parent_connection = parent_connection
        self.child_connection = child_connection
        self.process = process_builder(
            target=_worker_main,
            args=(child_connection, str(file_path), file_type, settings.model_dump()),
        )
        self.memory_reader = memory_reader or _default_memory_reader
        self.deadline = time.monotonic() + settings.document_extraction_timeout_seconds
        self.memory_limit_bytes = settings.document_extraction_memory_mb * 1024 * 1024
        self._started = False
        self._finished = False
        self._closed = False
        self._terminated = False

    def start(self) -> None:
        if self._started:
            return
        self.process.start()
        self._started = True
        self.child_connection.close()

    def is_alive(self) -> bool:
        if not self._started or self._finished:
            return False
        return self.process.is_alive()

    def _join_bounded(self, timeout: float = 5.0) -> None:
        if not self._started or self._finished:
            return
        self.process.join(timeout)
        if not self.process.is_alive():
            self._finished = True

    def _recv_payload(self) -> Any:
        try:
            return self.parent_connection.recv()
        except (EOFError, BrokenPipeError, OSError, ValueError):
            raise _safe_processing_error() from None

    def _poll_payload_ready(self) -> bool:
        try:
            return bool(self.parent_connection.poll(0))
        except (EOFError, BrokenPipeError, OSError):
            return False

    def _check_limits(self) -> None:
        if time.monotonic() >= self.deadline:
            self.terminate()
            raise ApiError(500, "DOCUMENT_EXTRACTION_TIMEOUT", _TIMEOUT_MESSAGE)
        if self.process.pid is not None:
            rss = self.memory_reader(self.process.pid)
            if rss is not None and rss > self.memory_limit_bytes:
                self.terminate()
                raise ApiError(500, "DOCUMENT_EXTRACTION_MEMORY_LIMIT", _MEMORY_MESSAGE)

    def step(self) -> ExtractedDocument | None:
        if self._poll_payload_ready():
            payload = self._recv_payload()
            self._join_bounded()
            return _parse_worker_payload(payload)
        if not self.is_alive():
            self._join_bounded()
            if self._poll_payload_ready():
                payload = self._recv_payload()
                return _parse_worker_payload(payload)
            raise _safe_processing_error()
        self._check_limits()
        return None

    def terminate(self, timeout: float = 5.0) -> None:
        if not self._started or self._terminated:
            return
        self._terminated = True
        if self.process.is_alive():
            self.process.terminate()
        self.process.join(timeout)
        if self.process.is_alive():
            self.process.kill()
            self.process.join(timeout)
        if not self.process.is_alive():
            self._finished = True

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self.parent_connection.close()
        finally:
            try:
                self.child_connection.close()
            except OSError:
                return

    async def start_async(self) -> None:
        await asyncio.to_thread(self.start)

    async def is_alive_async(self) -> bool:
        return await asyncio.to_thread(self.is_alive)

    async def step_async(self) -> ExtractedDocument | None:
        return await asyncio.to_thread(self.step)

    async def terminate_async(self) -> None:
        await asyncio.to_thread(self.terminate)

    async def close_async(self) -> None:
        await asyncio.to_thread(self.close)


def extract_document_isolated(
    file_path: Path,
    file_type: str,
    settings: Settings,
    *,
    process_factory: ProcessFactory | None = None,
    memory_reader: MemoryReader | None = None,
    poll_interval_seconds: float = 0.05,
) -> ExtractedDocument:
    """Run document extraction in a spawned worker with timeout and RSS limits."""

    supervisor = ExtractionSupervisor(
        file_path,
        file_type,
        settings,
        process_factory=process_factory,
        memory_reader=memory_reader,
    )
    try:
        supervisor.start()
        while True:
            result = supervisor.step()
            if result is not None:
                return result
            if poll_interval_seconds > 0:
                time.sleep(poll_interval_seconds)
    finally:
        if supervisor.is_alive():
            supervisor.terminate()
        supervisor.close()


async def extract_document_isolated_async(
    file_path: Path,
    file_type: str,
    settings: Settings,
    *,
    process_factory: ProcessFactory | None = None,
    memory_reader: MemoryReader | None = None,
    poll_interval_seconds: float = 0.05,
    sleep: SleepAwaitable | None = None,
) -> ExtractedDocument:
    """Run document extraction without blocking the event loop."""

    supervisor = ExtractionSupervisor(
        file_path,
        file_type,
        settings,
        process_factory=process_factory,
        memory_reader=memory_reader,
    )
    sleeper = sleep or asyncio.sleep
    try:
        await supervisor.start_async()
        while True:
            result = await supervisor.step_async()
            if result is not None:
                return result
            await sleeper(poll_interval_seconds)
    except asyncio.CancelledError:
        await asyncio.shield(supervisor.terminate_async())
        raise
    finally:
        if await supervisor.is_alive_async():
            await asyncio.shield(supervisor.terminate_async())
        await asyncio.shield(supervisor.close_async())
