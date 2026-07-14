import os
import sqlite3
from pathlib import Path

from app.config import Settings
from app.database import connection_scope
from app.documents.storage import QuarantineEntry, parse_quarantine_entry, resolve_storage_path, safe_unlink


def _normalized_path(path: Path) -> str:
    return str(path.resolve()).casefold()


def _load_referenced_storage_paths(settings: Settings) -> tuple[set[str], set[str]]:
    raw_paths: set[str] = set()
    text_paths: set[str] = set()
    with connection_scope(settings) as connection:
        rows = connection.execute("SELECT file_path, text_path FROM documents;").fetchall()
    for row in rows:
        raw_paths.add(_normalized_path(resolve_storage_path(settings.resolved_upload_directory, str(row["file_path"]))))
        if row["text_path"] is not None:
            text_paths.add(_normalized_path(resolve_storage_path(settings.resolved_extracted_text_directory, str(row["text_path"]))))
    return raw_paths, text_paths


def _restore_or_cleanup(entry: QuarantineEntry, referenced_paths: set[str]) -> None:
    normalized_original = _normalized_path(entry.original_path)
    if normalized_original in referenced_paths:
        if entry.original_path.exists():
            try:
                safe_unlink(entry.quarantine_path)
            except OSError:
                print("Document cleanup failed.")
            return
        try:
            os.replace(entry.quarantine_path, entry.original_path)
        except OSError:
            print("Document cleanup failed.")
        return
    try:
        safe_unlink(entry.quarantine_path)
    except OSError:
        print("Document cleanup failed.")


def _reconcile_directory(base_directory: Path, referenced_paths: set[str]) -> None:
    base = base_directory.resolve()
    for quarantine_path in base.rglob("*.delete-pending"):
        entry = parse_quarantine_entry(base, quarantine_path)
        if entry is None:
            continue
        _restore_or_cleanup(entry, referenced_paths)


def reconcile_document_quarantine(settings: Settings) -> None:
    """Restore or remove quarantine files using database state."""

    try:
        raw_paths, text_paths = _load_referenced_storage_paths(settings)
    except (sqlite3.Error, Exception):
        print("Document cleanup failed.")
        return
    _reconcile_directory(settings.resolved_upload_directory, raw_paths)
    _reconcile_directory(settings.resolved_extracted_text_directory, text_paths)
