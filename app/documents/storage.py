import os
from codecs import getincrementaldecoder
from pathlib import Path
from uuid import uuid4

from app.api.errors import ApiError
from app.config import PROJECT_ROOT
from app.security.path_validator import resolve_within


def build_internal_filename(extension: str) -> str:
    """Build a storage-safe internal filename."""

    return f"{uuid4().hex}{extension}"


def build_atomic_part_path(target_path: Path) -> Path:
    """Return the temporary sidecar path used for atomic writes."""

    return target_path.with_suffix(target_path.suffix + ".part")


def build_quarantine_path(target_path: Path) -> Path:
    """Return a collision-resistant quarantine filename for deletion."""

    return target_path.with_name(f"{target_path.name}.{uuid4().hex}.delete-pending")


def write_atomic_text(target_path: Path, text: str) -> None:
    """Write UTF-8 text atomically."""

    part_path = build_atomic_part_path(target_path)
    try:
        with open(part_path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(part_path, target_path)
    except Exception:
        safe_unlink(part_path)
        raise


def safe_unlink(path: Path) -> None:
    """Delete a file if it exists."""

    try:
        path.unlink(missing_ok=True)
    except FileNotFoundError:
        return


def cleanup_paths(paths: list[Path | None]) -> None:
    """Best-effort cleanup for temporary or orphaned document artifacts."""

    for path in paths:
        if path is None:
            continue
        try:
            safe_unlink(path)
        except OSError:
            print("Document cleanup failed.")


def build_relative_storage_path(relative_directory: Path, filename: str) -> str:
    """Return a project-relative storage path."""

    if relative_directory.is_absolute():
        return filename
    return str(relative_directory / filename).replace("\\", "/")


def resolve_storage_path(base_directory: Path, relative_path: str | Path) -> Path:
    """Resolve a stored relative path within the expected base directory."""

    allowed_base = base_directory.resolve()
    candidate = Path(relative_path)
    text = str(candidate)
    if candidate.is_absolute() or text.startswith("\\\\") or ":" in text:
        raise ApiError(500, "DOCUMENT_STORAGE_ERROR", "Hujjat storage yo'li noto'g'ri.")
    if len(candidate.parts) == 1:
        resolved = resolve_within(allowed_base, candidate)
    else:
        resolved = (PROJECT_ROOT / candidate).resolve()
        try:
            resolved.relative_to(allowed_base)
        except ValueError as exc:
            raise ApiError(500, "DOCUMENT_STORAGE_ERROR", "Hujjat storage yo'li noto'g'ri.") from exc
    return resolved


def read_text_preview(path: Path, char_limit: int, chunk_size: int = 4096) -> str:
    """Read only the leading UTF-8 characters needed for preview."""

    decoder = getincrementaldecoder("utf-8")()
    parts: list[str] = []
    collected = 0
    with open(path, "rb") as handle:
        while collected < char_limit:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            decoded = decoder.decode(chunk, final=False)
            if not decoded:
                continue
            remaining = char_limit - collected
            parts.append(decoded[:remaining])
            collected += min(len(decoded), remaining)
        if collected < char_limit:
            tail = decoder.decode(b"", final=True)
            if tail:
                remaining = char_limit - collected
                parts.append(tail[:remaining])
    return "".join(parts)


def cleanup_stale_quarantine_files(base_directory: Path) -> None:
    """Best-effort removal of stale quarantine files within a single storage tree."""

    base = base_directory.resolve()
    for path in base.rglob("*.delete-pending"):
        try:
            path.resolve().relative_to(base)
        except ValueError:
            continue
        try:
            safe_unlink(path)
        except OSError:
            print("Document cleanup failed.")
