"""Extract document files from ZIP archives."""

import io
import logging
import zipfile
from dataclasses import dataclass, field
from pathlib import PurePosixPath

logger = logging.getLogger(__name__)

MAX_TOTAL_EXTRACTED_MB = 500
MAX_DOCUMENT_COUNT = 100
SUPPORTED_EXTENSIONS = (".pdf", ".docx", ".md", ".txt")


def _decode_zip_filename(info: zipfile.ZipInfo) -> str:
    """Decode a ZIP entry filename, handling CJK encodings.

    Python's zipfile decodes non-UTF-8 filenames as CP437, which garbles
    CJK characters.  When the UTF-8 flag (bit 11) is NOT set we re-encode
    the CP437 string back to raw bytes and try UTF-8, then GBK (covers
    Simplified Chinese, the most common case for ZIP files from Chinese systems).
    """
    if info.flag_bits & 0x800:
        # Bit 11 set: filename is already UTF-8, Python decoded it correctly
        return info.filename

    # Python decoded as CP437 — reverse it to get the raw bytes
    try:
        raw = info.filename.encode("cp437")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return info.filename

    # Try UTF-8 first, then GBK (GB2312 superset)
    for encoding in ("utf-8", "gbk"):
        try:
            return raw.decode(encoding)
        except (UnicodeDecodeError, UnicodeEncodeError):
            continue

    # Fallback: return Python's original CP437 decode
    return info.filename


@dataclass
class ExtractedDocument:
    """A document file extracted from a ZIP archive."""

    filename: str  # e.g. "c.pdf"
    content: bytes
    dir_parts: list[str] = field(default_factory=list)  # e.g. ["a", "b"] for "a/b/c.pdf"


def extract_documents_from_zip(
    zip_bytes: bytes,
    max_file_size_mb: int = 10,
) -> tuple[list[ExtractedDocument], list[str]]:
    """Extract all supported document files (PDF/DOCX/MD/TXT) from a ZIP archive.

    Returns (documents, errors) where errors contains human-readable skip reasons.
    Skips __MACOSX/ entries, unsupported files, and directories.
    Rejects path traversal attempts and enforces size limits.
    """
    documents: list[ExtractedDocument] = []
    errors: list[str] = []
    total_extracted = 0
    max_total_bytes = MAX_TOTAL_EXTRACTED_MB * 1024 * 1024
    max_single_bytes = max_file_size_mb * 1024 * 1024

    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile:
        raise ValueError("Invalid or corrupted ZIP file")

    with zf:
        for info in zf.infolist():
            # Skip directories
            if info.is_dir():
                continue

            name = _decode_zip_filename(info)

            logger.info("ZIP entry: raw=%r decoded=%r", info.filename, name)

            # Skip macOS resource fork entries
            if name.startswith("__MACOSX/") or "/__MACOSX/" in name:
                logger.info("ZIP: skipping macOS resource fork: %s", name)
                continue

            # Skip hidden files (starting with .)
            parts = PurePosixPath(name).parts
            if any(p.startswith(".") for p in parts):
                logger.info("ZIP: skipping hidden file: %s", name)
                continue

            # Only process supported document files
            if not name.lower().endswith(SUPPORTED_EXTENSIONS):
                logger.info("ZIP: skipping unsupported file: %s", name)
                continue

            # Security: reject path traversal
            if any(p == ".." for p in parts):
                errors.append(f"Skipped '{name}': path traversal not allowed")
                continue

            # Check max document count
            if len(documents) >= MAX_DOCUMENT_COUNT:
                errors.append(
                    f"Skipped '{name}': maximum {MAX_DOCUMENT_COUNT} documents per ZIP exceeded"
                )
                continue

            # Check uncompressed size before reading
            if info.file_size > max_single_bytes:
                errors.append(
                    f"Skipped '{name}': exceeds {max_file_size_mb}MB size limit"
                )
                continue

            if total_extracted + info.file_size > max_total_bytes:
                errors.append(
                    f"Skipped '{name}': total extracted size would exceed {MAX_TOTAL_EXTRACTED_MB}MB limit"
                )
                continue

            try:
                content = zf.read(info)
            except Exception as exc:
                errors.append(f"Skipped '{name}': {exc}")
                continue

            total_extracted += len(content)

            # Parse directory structure
            path = PurePosixPath(name)
            dir_parts = list(path.parts[:-1])  # everything except filename
            filename = path.name

            documents.append(ExtractedDocument(filename=filename, content=content, dir_parts=dir_parts))
            logger.info("Extracted document: %s (dirs=%s, size=%d)", filename, dir_parts, len(content))

    return documents, errors
