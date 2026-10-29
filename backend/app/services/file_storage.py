import hashlib
from pathlib import Path

from app.core.config import settings


def compute_file_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def resolve_file_path(
    content_path: str,
    *,
    allow_legacy_absolute: bool = False,
) -> Path:
    """Resolve a stored content_path to an absolute Path.

    Supports two formats:
    - Relative (new): 'b2/hash.pdf' — resolved against settings.upload_dir
    - Absolute (legacy): allowed only when it resolves inside upload_dir
    """
    upload_root = Path(settings.upload_dir).resolve()
    p = Path(content_path)
    candidate = p if p.is_absolute() else upload_root / p
    resolved = candidate.resolve()

    if p.is_absolute() and allow_legacy_absolute and not _is_relative_to(resolved, upload_root):
        return resolved
    if not _is_relative_to(resolved, upload_root):
        raise ValueError("Resolved file path is outside the upload directory")
    return resolved


def save_file(content: bytes, content_hash: str, filename: str) -> str:
    """Save file and return a relative path (relative to upload_dir)."""
    subdir = content_hash[:2]
    dir_path = Path(settings.upload_dir) / subdir
    dir_path.mkdir(parents=True, exist_ok=True)

    ext = Path(filename).suffix
    file_path = dir_path / f"{content_hash}{ext}"

    if not file_path.exists():
        file_path.write_bytes(content)

    # Store as relative path so it works across environments
    return f"{subdir}/{content_hash}{ext}"


def delete_file(file_path: str) -> None:
    path = resolve_file_path(file_path)
    if path.exists():
        path.unlink()


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True
