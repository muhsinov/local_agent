import os
from pathlib import Path
from uuid import uuid4

from app.security.path_validator import resolve_within


def build_internal_filename(extension: str) -> str:
    """Build a storage-safe internal filename."""

    return f"{uuid4().hex}{extension}"


def write_atomic_text(target_path: Path, text: str) -> None:
    """Write UTF-8 text atomically."""

    part_path = target_path.with_suffix(target_path.suffix + ".part")
    with open(part_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(part_path, target_path)


def safe_unlink(path: Path) -> None:
    """Delete a file if it exists."""

    try:
        path.unlink(missing_ok=True)
    except FileNotFoundError:
        return


def build_relative_storage_path(relative_directory: Path, filename: str) -> str:
    """Return a project-relative storage path."""

    if relative_directory.is_absolute():
        return filename
    return str(relative_directory / filename).replace("\\", "/")


def resolve_storage_path(base_directory: Path, relative_path: str | Path) -> Path:
    """Resolve a stored relative path within the expected base directory."""

    candidate = Path(relative_path)
    if len(candidate.parts) <= 1:
        return resolve_within(base_directory, candidate)
    if base_directory.name in candidate.parts[:-1]:
        start_index = candidate.parts.index(base_directory.name)
        return resolve_within(base_directory.parent, Path(*candidate.parts[start_index:]))
    return resolve_within(base_directory.parent, candidate)
