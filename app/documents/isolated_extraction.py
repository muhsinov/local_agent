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
                    "message": "Hujjatni qayta ishlashda xatolik yuz berdi.",
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


def _terminate_process(process: multiprocessing.process.BaseProcess, timeout: float = 5.0) -> None:
    """Terminate and join a child process without raising further errors."""

    if process.is_alive():
        process.terminate()
    process.join(timeout)
    if process.is_alive():
        process.kill()
        process.join(timeout)


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

    context = multiprocessing.get_context("spawn")
    parent_connection, child_connection = context.Pipe(duplex=False)
    process_builder = process_factory or context.Process
    reader = memory_reader or _default_memory_reader
    process = process_builder(
        target=_worker_main,
        args=(child_connection, str(file_path), file_type, settings.model_dump()),
    )
    try:
        process.start()
        child_connection.close()
        deadline = time.monotonic() + settings.document_extraction_timeout_seconds
        memory_limit_bytes = settings.document_extraction_memory_mb * 1024 * 1024

        while True:
            try:
                has_payload = parent_connection.poll(poll_interval_seconds)
            except (BrokenPipeError, EOFError):
                has_payload = False
            if has_payload:
                payload = parent_connection.recv()
                process.join(5)
                if payload.get("ok"):
                    return ExtractedDocument(**payload["result"])
                error = payload["error"]
                raise ApiError(error["status_code"], error["code"], error["message"], error.get("extra"))

            if not process.is_alive():
                process.join(5)
                break

            if time.monotonic() >= deadline:
                _terminate_process(process)
                raise ApiError(500, "DOCUMENT_EXTRACTION_TIMEOUT", "Hujjatni qayta ishlash vaqti tugadi.")

            if process.pid is not None:
                rss = reader(process.pid)
                if rss is not None and rss > memory_limit_bytes:
                    _terminate_process(process)
                    raise ApiError(
                        500,
                        "DOCUMENT_EXTRACTION_MEMORY_LIMIT",
                        "Hujjatni qayta ishlash xotira limitidan oshdi.",
                    )

        if parent_connection.poll():
            payload = parent_connection.recv()
            if payload.get("ok"):
                return ExtractedDocument(**payload["result"])
            error = payload["error"]
            raise ApiError(error["status_code"], error["code"], error["message"], error.get("extra"))
        raise ApiError(500, "DOCUMENT_PROCESSING_ERROR", "Hujjatni qayta ishlashda xatolik yuz berdi.")
    finally:
        parent_connection.close()
        child_connection.close()
        if process.is_alive():
            _terminate_process(process)
