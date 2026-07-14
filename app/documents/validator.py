from pathlib import Path
import zipfile

from app.api.errors import ApiError
from app.config import Settings


ALLOWED_TYPES = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".txt": "txt",
    ".md": "md",
}


def normalize_extension(filename: str) -> tuple[str, str]:
    """Return the normalized extension and file type."""

    suffix = Path(filename).suffix.lower()
    if not suffix or suffix not in ALLOWED_TYPES:
        raise ApiError(415, "UNSUPPORTED_FILE_TYPE", "Bu fayl turi qo'llab-quvvatlanmaydi.")
    stem = Path(filename).stem.lower()
    blocked_suffixes = {".exe", ".bat", ".cmd", ".ps1", ".com", ".scr", ".js", ".vbs", ".msi"}
    if any(stem.endswith(ext) for ext in blocked_suffixes):
        raise ApiError(415, "UNSUPPORTED_FILE_TYPE", "Bu fayl turi qo'llab-quvvatlanmaydi.")
    return suffix, ALLOWED_TYPES[suffix]


def validate_file_signature(file_path: Path, file_type: str, settings: Settings) -> None:
    """Validate the stored file signature against its declared type."""

    if file_type == "pdf":
        header = file_path.read_bytes()[:1024]
        if b"%PDF-" not in header:
            raise ApiError(415, "FILE_TYPE_MISMATCH", "PDF fayl signaturasi noto'g'ri.")
        return

    if file_type == "docx":
        validate_docx_archive(
            file_path,
            settings,
            structural_error_code="FILE_TYPE_MISMATCH",
            structural_error_message="DOCX fayl tuzilmasi noto'g'ri.",
            corrupt_error_code="FILE_TYPE_MISMATCH",
            corrupt_error_message="DOCX fayl ZIP konteyner emas.",
        )
        return

    raw = file_path.read_bytes()
    if b"\x00" in raw:
        raise ApiError(415, "FILE_TYPE_MISMATCH", "Matn fayl binary ma'lumot saqlaydi.")
    try:
        raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ApiError(415, "FILE_TYPE_MISMATCH", "Matn fayl UTF-8 emas.") from exc


def validate_docx_archive(
    file_path: Path,
    settings: Settings,
    *,
    structural_error_code: str = "INVALID_DOCX",
    structural_error_message: str = "DOCX fayl tuzilmasi to'liq emas.",
    corrupt_error_code: str = "INVALID_DOCX",
    corrupt_error_message: str = "DOCX faylni ochib bo'lmadi.",
) -> None:
    """Run DOCX ZIP safety checks before parsing."""

    try:
        with zipfile.ZipFile(file_path) as archive:
            required_content_types = False
            required_document_xml = False
            total_uncompressed = 0
            entry_count = 0
            for info in archive.infolist():
                entry_count += 1
                if entry_count > settings.max_docx_zip_entries:
                    raise ApiError(422, "UNSAFE_DOCX_ARCHIVE", "DOCX archive juda katta.")
                name = info.filename
                if name == "[Content_Types].xml":
                    required_content_types = True
                elif name == "word/document.xml":
                    required_document_xml = True
                if info.flag_bits & 0x1:
                    raise ApiError(422, "UNSAFE_DOCX_ARCHIVE", "Parol bilan himoyalangan DOCX qabul qilinmaydi.")
                if name.startswith("/") or name.startswith("\\") or ".." in Path(name).parts or ":" in name:
                    raise ApiError(422, "UNSAFE_DOCX_ARCHIVE", "DOCX archive xavfsiz emas.")
                if name.endswith("/"):
                    continue
                if info.create_system == 3 and (info.external_attr >> 16) & 0o120000 == 0o120000:
                    raise ApiError(422, "UNSAFE_DOCX_ARCHIVE", "DOCX archive xavfsiz emas.")
                total_uncompressed += info.file_size
                if total_uncompressed > settings.max_docx_uncompressed_mb * 1024 * 1024:
                    raise ApiError(422, "UNSAFE_DOCX_ARCHIVE", "DOCX archive juda katta.")
                compressed = max(info.compress_size, 1)
                ratio = info.file_size / compressed if info.file_size else 0
                if ratio > settings.max_docx_compression_ratio:
                    raise ApiError(422, "UNSAFE_DOCX_ARCHIVE", "DOCX archive siqilish nisbati xavfli.")
            if not required_content_types or not required_document_xml:
                raise ApiError(422, structural_error_code, structural_error_message)
    except ApiError:
        raise
    except zipfile.BadZipFile as exc:
        raise ApiError(422, corrupt_error_code, corrupt_error_message) from exc
