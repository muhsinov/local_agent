from pathlib import Path

from app.api.errors import ApiError


def resolve_within(base_directory: Path, relative_path: str | Path) -> Path:
    """Resolve a relative path and ensure it stays within the base directory."""

    base = base_directory.resolve()
    candidate = Path(relative_path)
    if candidate.is_absolute():
        raise ApiError(500, "DOCUMENT_STORAGE_ERROR", "Hujjat storage yo'li noto'g'ri.")
    text = str(candidate)
    if text.startswith("\\\\") or ":" in text:
        raise ApiError(500, "DOCUMENT_STORAGE_ERROR", "Hujjat storage yo'li noto'g'ri.")
    resolved = (base / candidate).resolve()
    try:
        resolved.relative_to(base)
    except ValueError as exc:
        raise ApiError(500, "DOCUMENT_STORAGE_ERROR", "Hujjat storage yo'li noto'g'ri.") from exc
    return resolved
