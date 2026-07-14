import asyncio
import hashlib
import os
import sqlite3
from pathlib import Path
from time import perf_counter

from fastapi import APIRouter, File, Query, Request, UploadFile, status
from fastapi.concurrency import run_in_threadpool

from app.api.errors import ApiError
from app.config import Settings
from app.documents.extractor import extract_document
from app.documents.models import DocumentRecord
from app.documents.storage import (
    build_internal_filename,
    build_relative_storage_path,
    resolve_storage_path,
    safe_unlink,
    write_atomic_text,
)
from app.documents.validator import normalize_extension, validate_file_signature
from app.schemas.documents import (
    DocumentListResponse,
    DocumentMetadataResponse,
    DocumentPreviewResponse,
)
from app.security.filename import sanitize_original_filename
from app.services.audit_service import write_audit_log
from app.services.document_service import (
    create_document,
    find_document_by_sha256,
    get_document,
    list_documents,
)
from app.database import connection_scope
from app.services.document_service import delete_document_record


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


@router.post("/upload", response_model=DocumentMetadataResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(request: Request, file: UploadFile = File(...)) -> DocumentMetadataResponse:
    settings: Settings = request.app.state.settings
    started_at = perf_counter()
    original_name = sanitize_original_filename(file.filename or "", settings.max_original_filename_chars)
    extension, file_type = normalize_extension(original_name)
    raw_final_path: Path | None = None
    raw_part_path: Path | None = None
    text_final_path: Path | None = None
    semaphore = request.app.state.document_semaphore
    acquired = False
    sha256 = hashlib.sha256()
    total_bytes = 0

    try:
        internal_filename = build_internal_filename(extension)
        raw_relative_path = build_relative_storage_path(settings.upload_directory, internal_filename)
        raw_final_path = resolve_storage_path(settings.resolved_upload_directory, raw_relative_path)
        raw_part_path = raw_final_path.with_suffix(raw_final_path.suffix + ".part")

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

        validate_file_signature(raw_part_path, file_type, settings)
        sha256_hex = sha256.hexdigest()
        duplicate = find_document_by_sha256(settings, sha256_hex)
        if duplicate is not None:
            raise ApiError(
                409,
                "DOCUMENT_DUPLICATE",
                "Bu hujjat avval yuklangan.",
                extra={"existing_document_id": duplicate.id},
            )

        os.replace(raw_part_path, raw_final_path)

        try:
            await asyncio.wait_for(semaphore.acquire(), timeout=settings.document_busy_timeout_seconds)
            acquired = True
        except TimeoutError:
            raise ApiError(
                429,
                "DOCUMENT_PROCESSOR_BUSY",
                "Hujjat protsessori hozir band. Keyinroq qayta urinib ko'ring.",
            ) from None

        extracted = await run_in_threadpool(extract_document, raw_final_path, file_type, settings)
        text_internal_name = f"{Path(internal_filename).stem}.txt"
        text_relative_path = build_relative_storage_path(settings.extracted_text_directory, text_internal_name)
        text_final_path = resolve_storage_path(settings.resolved_extracted_text_directory, text_relative_path)
        write_atomic_text(text_final_path, extracted.text)

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
    except ApiError:
        if text_final_path:
            safe_unlink(text_final_path)
        if raw_part_path:
            safe_unlink(raw_part_path)
        if raw_final_path:
            safe_unlink(raw_final_path)
        raise
    except sqlite3.Error:
        if text_final_path:
            safe_unlink(text_final_path)
        if raw_part_path:
            safe_unlink(raw_part_path)
        if raw_final_path:
            safe_unlink(raw_final_path)
        raise ApiError(500, "DATABASE_ERROR", "Lokal database operatsiyasini bajarib bo'lmadi.") from None
    finally:
        if acquired:
            semaphore.release()
        await file.close()


@router.get("", response_model=DocumentListResponse)
def get_documents(
    request: Request,
    limit: int = Query(default=50, ge=1),
    offset: int = Query(default=0, ge=0),
) -> DocumentListResponse:
    settings: Settings = request.app.state.settings
    items = [_to_metadata(item) for item in list_documents(settings, limit, offset)]
    return DocumentListResponse(items=items, limit=min(limit, settings.max_document_list_limit), offset=offset)


@router.get("/{document_id}", response_model=DocumentMetadataResponse)
def get_document_metadata(request: Request, document_id: int) -> DocumentMetadataResponse:
    settings: Settings = request.app.state.settings
    document = get_document(settings, document_id)
    if document is None:
        raise ApiError(404, "DOCUMENT_NOT_FOUND", "Hujjat topilmadi.")
    return _to_metadata(document)


@router.get("/{document_id}/text", response_model=DocumentPreviewResponse)
def get_document_text_preview(
    request: Request,
    document_id: int,
    limit: int = Query(default=5000, ge=1),
) -> DocumentPreviewResponse:
    settings: Settings = request.app.state.settings
    if limit > settings.document_preview_chars:
        raise ApiError(422, "VALIDATION_ERROR", "Preview limiti ruxsat etilgan qiymatdan oshdi.")
    document = get_document(settings, document_id)
    if document is None:
        raise ApiError(404, "DOCUMENT_NOT_FOUND", "Hujjat topilmadi.")
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
        text = text_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ApiError(500, "DOCUMENT_STORAGE_ERROR", "Hujjat storage fayli topilmadi.") from None
    except OSError:
        raise ApiError(500, "DOCUMENT_STORAGE_ERROR", "Hujjat storage faylini o'qib bo'lmadi.") from None
    preview = text[:limit]
    return DocumentPreviewResponse(
        document_id=document.id,
        text=preview,
        returned_chars=len(preview),
        total_chars=len(text),
        truncated=len(text) > len(preview),
    )


@router.delete("/{document_id}", response_model=dict)
def delete_document(request: Request, document_id: int, confirm: bool = Query(default=False)) -> dict:
    settings: Settings = request.app.state.settings
    if not confirm:
        raise ApiError(400, "CONFIRMATION_REQUIRED", "Delete uchun confirm=true kerak.")
    document = get_document(settings, document_id)
    if document is None:
        raise ApiError(404, "DOCUMENT_NOT_FOUND", "Hujjat topilmadi.")

    raw_path = resolve_storage_path(settings.resolved_upload_directory, document.file_path)
    text_path = resolve_storage_path(settings.resolved_extracted_text_directory, document.text_path) if document.text_path else None
    if not raw_path.exists() or (text_path and not text_path.exists()):
        raise ApiError(500, "DOCUMENT_STORAGE_ERROR", "Hujjat storage holati noto'g'ri.")

    raw_quarantine = raw_path.with_suffix(raw_path.suffix + ".delete-pending")
    text_quarantine = text_path.with_suffix(text_path.suffix + ".delete-pending") if text_path else None
    os.replace(raw_path, raw_quarantine)
    if text_path and text_quarantine:
        os.replace(text_path, text_quarantine)

    try:
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
        safe_unlink(raw_quarantine)
        if text_quarantine:
            safe_unlink(text_quarantine)
    except ApiError:
        if raw_quarantine.exists():
            os.replace(raw_quarantine, raw_path)
        if text_quarantine and text_quarantine.exists() and text_path:
            os.replace(text_quarantine, text_path)
        raise
    except sqlite3.Error:
        if raw_quarantine.exists():
            os.replace(raw_quarantine, raw_path)
        if text_quarantine and text_quarantine.exists() and text_path:
            os.replace(text_quarantine, text_path)
        raise ApiError(500, "DATABASE_ERROR", "Lokal database operatsiyasini bajarib bo'lmadi.") from None

    write_audit_log(
        settings,
        action="document_delete",
        status="deleted",
        arguments={
            "document_id": document.id,
            "file_type": document.file_type,
            "size_bytes": document.size_bytes,
            "status": "deleted",
            "warning_code": document.warning_code,
        },
    )
    return {"ok": True}
