import asyncio
import hashlib
import os
import sqlite3
from pathlib import Path
from time import perf_counter

from fastapi import APIRouter, File, Query, Request, UploadFile, status

from app.api.errors import ApiError
from app.config import Settings
from app.database import connection_scope
from app.documents.isolated_extraction import extract_document_isolated_async
from app.documents.models import DocumentRecord
from app.documents.storage import (
    build_atomic_part_path,
    build_internal_filename,
    build_quarantine_path,
    build_relative_storage_path,
    cleanup_paths,
    read_text_preview,
    resolve_storage_path,
    safe_unlink,
    write_atomic_text,
)
from app.documents.validator import normalize_extension, validate_file_signature
from app.schemas.documents import DocumentListResponse, DocumentMetadataResponse, DocumentPreviewResponse
from app.security.filename import sanitize_original_filename
from app.services.audit_service import write_audit_log
from app.services.document_service import (
    create_document,
    delete_document_record,
    get_document,
    list_documents,
)


router = APIRouter(prefix="/documents", tags=["documents"])


def _to_metadata(record: DocumentRecord) -> DocumentMetadataResponse:
    return DocumentMetadataResponse(
        id=record.id,
        file_name=record.file_name,
        file_type=record.file_type,
        size_bytes=record.size_bytes,
        status=record.status,
        char_count=record.char_count,
        page_count=record.page_count,
        warning_code=record.warning_code,
        indexed=record.indexed,
        created_at=record.created_at,
    )


def _database_error() -> ApiError:
    return ApiError(500, "DATABASE_ERROR", "Lokal database operatsiyasini bajarib bo'lmadi.")


def _storage_error(message: str = "Hujjat storage operatsiyasini bajarib bo'lmadi.") -> ApiError:
    return ApiError(500, "DOCUMENT_STORAGE_ERROR", message)


def _load_document_or_404(settings: Settings, document_id: int) -> DocumentRecord:
    try:
        document = get_document(settings, document_id)
    except sqlite3.Error:
        raise _database_error() from None
    if document is None:
        raise ApiError(404, "DOCUMENT_NOT_FOUND", "Hujjat topilmadi.")
    return document


def _cleanup_upload_artifacts(*paths: Path | None) -> None:
    cleanup_paths(list(paths))


def _restore_quarantine(source: Path | None, target: Path | None) -> bool:
    if source is None or target is None or not source.exists():
        return True
    try:
        os.replace(source, target)
        return True
    except OSError:
        print("Document cleanup failed.")
        return False


@router.post("/upload", response_model=DocumentMetadataResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(request: Request, file: UploadFile = File(...)) -> DocumentMetadataResponse:
    settings: Settings = request.app.state.settings
    semaphore = request.app.state.document_semaphore
    started_at = perf_counter()
    acquired = False
    raw_final_path: Path | None = None
    raw_part_path: Path | None = None
    text_final_path: Path | None = None
    text_part_path: Path | None = None
    sha256 = hashlib.sha256()
    total_bytes = 0

    try:
        original_name = sanitize_original_filename(file.filename or "", settings.max_original_filename_chars)
        extension, file_type = normalize_extension(original_name)
        internal_filename = build_internal_filename(extension)
        raw_relative_path = build_relative_storage_path(settings.upload_directory, internal_filename)
        raw_final_path = resolve_storage_path(settings.resolved_upload_directory, raw_relative_path)
        raw_part_path = build_atomic_part_path(raw_final_path)

        try:
            with open(raw_part_path, "wb") as output_handle:
                while True:
                    chunk = await file.read(settings.upload_chunk_size_kb * 1024)
                    if not chunk:
                        break
                    total_bytes += len(chunk)
                    if total_bytes > settings.max_file_size_mb * 1024 * 1024:
                        raise ApiError(413, "FILE_TOO_LARGE", "Fayl hajmi limitdan oshdi.")
                    sha256.update(chunk)
                    output_handle.write(chunk)
                output_handle.flush()
                os.fsync(output_handle.fileno())
        except ApiError:
            raise
        except OSError:
            raise _storage_error() from None

        await asyncio.to_thread(validate_file_signature, raw_part_path, file_type, settings)
        sha256_hex = sha256.hexdigest()

        try:
            os.replace(raw_part_path, raw_final_path)
        except OSError:
            raise _storage_error() from None

        try:
            await asyncio.wait_for(semaphore.acquire(), timeout=settings.document_busy_timeout_seconds)
            acquired = True
        except TimeoutError:
            raise ApiError(
                429,
                "DOCUMENT_PROCESSOR_BUSY",
                "Hujjat protsessori hozir band. Keyinroq qayta urinib ko'ring.",
            ) from None

        try:
            extracted = await extract_document_isolated_async(raw_final_path, file_type, settings)
        except asyncio.CancelledError:
            _cleanup_upload_artifacts(text_part_path, text_final_path, raw_part_path, raw_final_path)
            raise
        except ApiError:
            raise
        except OSError:
            raise _storage_error() from None
        except Exception:
            raise ApiError(500, "DOCUMENT_PROCESSING_ERROR", "Hujjatni qayta ishlashda xatolik yuz berdi.") from None

        text_internal_name = f"{Path(internal_filename).stem}.txt"
        text_relative_path = build_relative_storage_path(settings.extracted_text_directory, text_internal_name)
        text_final_path = resolve_storage_path(settings.resolved_extracted_text_directory, text_relative_path)
        text_part_path = build_atomic_part_path(text_final_path)

        try:
            write_atomic_text(text_final_path, extracted.text)
        except OSError:
            raise _storage_error() from None

        try:
            record = create_document(
                settings,
                file_name=original_name,
                file_path=raw_relative_path,
                file_type=file_type,
                size_bytes=total_bytes,
                sha256=sha256_hex,
                status=extracted.status,
                text_path=text_relative_path,
                char_count=extracted.char_count,
                page_count=extracted.page_count,
                warning_code=extracted.warning_code,
            )
        except ApiError:
            raise
        except Exception:
            raise _database_error() from None
        write_audit_log(
            settings,
            action="document_upload",
            status=record.status,
            arguments={
                "document_id": record.id,
                "file_type": record.file_type,
                "size_bytes": record.size_bytes,
                "status": record.status,
                "warning_code": record.warning_code,
            },
            execution_time_ms=int((perf_counter() - started_at) * 1000),
        )
        return _to_metadata(record)
    except asyncio.CancelledError:
        _cleanup_upload_artifacts(text_part_path, text_final_path, raw_part_path, raw_final_path)
        raise
    except ApiError:
        _cleanup_upload_artifacts(text_part_path, text_final_path, raw_part_path, raw_final_path)
        raise
    except sqlite3.Error:
        _cleanup_upload_artifacts(text_part_path, text_final_path, raw_part_path, raw_final_path)
        raise _database_error() from None
    except OSError:
        _cleanup_upload_artifacts(text_part_path, text_final_path, raw_part_path, raw_final_path)
        raise _storage_error() from None
    finally:
        if acquired:
            semaphore.release()
        try:
            await file.close()
        except Exception:
            print("Document cleanup failed.")


@router.get("", response_model=DocumentListResponse)
def get_documents(
    request: Request,
    limit: int = Query(default=50, ge=1),
    offset: int = Query(default=0, ge=0),
) -> DocumentListResponse:
    settings: Settings = request.app.state.settings
    try:
        items = [_to_metadata(item) for item in list_documents(settings, limit, offset)]
    except sqlite3.Error:
        raise _database_error() from None
    return DocumentListResponse(items=items, limit=min(limit, settings.max_document_list_limit), offset=offset)


@router.get("/{document_id}", response_model=DocumentMetadataResponse)
def get_document_metadata(request: Request, document_id: int) -> DocumentMetadataResponse:
    settings: Settings = request.app.state.settings
    return _to_metadata(_load_document_or_404(settings, document_id))


@router.get("/{document_id}/text", response_model=DocumentPreviewResponse)
def get_document_text_preview(
    request: Request,
    document_id: int,
    limit: int = Query(default=5000, ge=1),
) -> DocumentPreviewResponse:
    settings: Settings = request.app.state.settings
    if limit > settings.document_preview_chars:
        raise ApiError(422, "VALIDATION_ERROR", "Preview limiti ruxsat etilgan qiymatdan oshdi.")
    document = _load_document_or_404(settings, document_id)
    if not document.text_path:
        return DocumentPreviewResponse(
            document_id=document.id,
            text="",
            returned_chars=0,
            total_chars=document.char_count,
            truncated=False,
        )
    try:
        text_path = resolve_storage_path(settings.resolved_extracted_text_directory, document.text_path)
        preview = read_text_preview(text_path, limit)
    except FileNotFoundError:
        raise _storage_error("Hujjat storage fayli topilmadi.") from None
    except OSError:
        raise _storage_error("Hujjat storage faylini o'qib bo'lmadi.") from None
    return DocumentPreviewResponse(
        document_id=document.id,
        text=preview,
        returned_chars=len(preview),
        total_chars=document.char_count,
        truncated=document.char_count > len(preview),
    )


@router.delete("/{document_id}", response_model=dict)
def delete_document(request: Request, document_id: int, confirm: bool = Query(default=False)) -> dict:
    settings: Settings = request.app.state.settings
    if not settings.direct_document_delete_enabled:
        write_audit_log(settings, action="direct_action_denied", status="DIRECT_ACTION_DISABLED", arguments={"document_id": document_id})
        raise ApiError(403, "DIRECT_ACTION_DISABLED", "Direct document delete o'chirilgan.")
    if not confirm:
        raise ApiError(400, "CONFIRMATION_REQUIRED", "Delete uchun confirm=true kerak.")

    document = _load_document_or_404(settings, document_id)
    raw_path = resolve_storage_path(settings.resolved_upload_directory, document.file_path)
    text_path = resolve_storage_path(settings.resolved_extracted_text_directory, document.text_path) if document.text_path else None
    if not raw_path.exists() or (text_path and not text_path.exists()):
        raise _storage_error("Hujjat storage holati noto'g'ri.")

    raw_quarantine = build_quarantine_path(raw_path)
    text_quarantine = build_quarantine_path(text_path) if text_path else None
    raw_renamed = False
    text_renamed = False

    try:
        try:
            os.replace(raw_path, raw_quarantine)
            raw_renamed = True
            if text_path and text_quarantine:
                os.replace(text_path, text_quarantine)
                text_renamed = True
        except OSError:
            if raw_renamed:
                _restore_quarantine(raw_quarantine, raw_path)
            raise _storage_error("Hujjat storage operatsiyasini bajarib bo'lmadi.") from None

        with connection_scope(settings) as connection:
            connection.execute("BEGIN;")
            try:
                deleted = delete_document_record(connection, document_id)
                if not deleted:
                    raise ApiError(404, "DOCUMENT_NOT_FOUND", "Hujjat topilmadi.")
                connection.commit()
            except Exception:
                connection.rollback()
                raise
    except ApiError:
        if text_renamed:
            _restore_quarantine(text_quarantine, text_path)
        if raw_renamed:
            _restore_quarantine(raw_quarantine, raw_path)
        raise
    except sqlite3.Error:
        restored_ok = True
        if text_renamed:
            restored_ok = _restore_quarantine(text_quarantine, text_path) and restored_ok
        if raw_renamed:
            restored_ok = _restore_quarantine(raw_quarantine, raw_path) and restored_ok
        if not restored_ok:
            print("Document cleanup failed.")
        raise _database_error() from None

    cleanup_pending = False
    try:
        safe_unlink(raw_quarantine)
        if text_quarantine:
            safe_unlink(text_quarantine)
    except OSError:
        cleanup_pending = True

    write_audit_log(
        settings,
        action="document_delete",
        status="deleted_cleanup_pending" if cleanup_pending else "deleted",
        arguments={
            "document_id": document.id,
            "file_type": document.file_type,
            "size_bytes": document.size_bytes,
            "status": "deleted_cleanup_pending" if cleanup_pending else "deleted",
            "warning_code": document.warning_code,
        },
    )
    return {"ok": True}
