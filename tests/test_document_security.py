from pathlib import Path

import pytest

from app.api.errors import ApiError
from app.documents.storage import resolve_storage_path
from app.documents.validator import normalize_extension
from app.security.filename import sanitize_original_filename
from app.security.path_validator import resolve_within
from tests.conftest import build_settings


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


def test_resolve_storage_path_allows_filename_only(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    resolved = resolve_storage_path(settings.resolved_upload_directory, "safe.txt")
    assert resolved == (settings.resolved_upload_directory / "safe.txt").resolve()


def test_resolve_storage_path_allows_project_relative_when_base_matches_project_root() -> None:
    settings = build_settings(Path("unused"), UPLOAD_DIRECTORY=Path("data/uploads"), EXTRACTED_TEXT_DIRECTORY=Path("data/extracted"))
    resolved = resolve_storage_path(settings.resolved_upload_directory, "data/uploads/safe.txt")
    assert resolved == (settings.resolved_upload_directory / "safe.txt").resolve()


def test_resolve_storage_path_blocks_upload_to_extracted_sibling(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    with pytest.raises(ApiError):
        resolve_storage_path(settings.resolved_upload_directory, "../extracted/evil.txt")


def test_resolve_storage_path_blocks_extracted_to_upload_sibling(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    with pytest.raises(ApiError):
        resolve_storage_path(settings.resolved_extracted_text_directory, "../uploads/evil.txt")


def test_resolve_storage_path_blocks_absolute_windows_path(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    with pytest.raises(ApiError):
        resolve_storage_path(settings.resolved_upload_directory, "C:/temp/evil.txt")


def test_resolve_storage_path_blocks_unc_path(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    with pytest.raises(ApiError):
        resolve_storage_path(settings.resolved_upload_directory, "\\\\server\\share\\evil.txt")


def test_resolve_storage_path_blocks_symlink_escape(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    link = settings.resolved_upload_directory / "linked"
    settings.resolved_upload_directory.mkdir(parents=True, exist_ok=True)
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Symlink creation unavailable on this system.")
    with pytest.raises(ApiError):
        resolve_storage_path(settings.resolved_upload_directory, "linked/escape.txt")
