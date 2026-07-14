from pathlib import Path

from app.api.errors import ApiError


def sanitize_original_filename(filename: str, max_length: int) -> str:
    """Validate and sanitize the user-facing original filename."""

    candidate = Path(filename).name.strip()
    if not candidate or candidate in {".", ".."}:
        raise ApiError(422, "INVALID_FILENAME", "Fayl nomi noto'g'ri.")
    if len(candidate) > max_length:
        raise ApiError(422, "INVALID_FILENAME", "Fayl nomi juda uzun.")
    if any(ord(char) < 32 for char in candidate):
        raise ApiError(422, "INVALID_FILENAME", "Fayl nomi nazorat belgilarini saqlay olmaydi.")
    return candidate
