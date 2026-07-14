from pathlib import Path

import pytest

from app.api.errors import ApiError
from app.documents.validator import normalize_extension
from app.security.filename import sanitize_original_filename
from app.security.path_validator import resolve_within


def test_filename_sanitizes_path_traversal() -> None:
    assert sanitize_original_filename("..\\..\\secret.txt", 180) == "secret.txt"


def test_filename_rejects_empty_or_control_names() -> None:
    with pytest.raises(ApiError):
        sanitize_original_filename("..", 180)
    with pytest.raises(ApiError):
        sanitize_original_filename("bad\x00name.txt", 180)


def test_path_validator_blocks_escape(tmp_path: Path) -> None:
    with pytest.raises(ApiError):
        resolve_within(tmp_path, "../outside.txt")


def test_path_validator_allows_safe_relative_path(tmp_path: Path) -> None:
    resolved = resolve_within(tmp_path, "nested/file.txt")
    assert resolved == (tmp_path / "nested" / "file.txt").resolve()


def test_normalize_extension_rejects_hidden_executable() -> None:
    with pytest.raises(ApiError):
        normalize_extension("invoice.pdf.exe")
