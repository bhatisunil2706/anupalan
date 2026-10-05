"""Evidence file storage. Local filesystem for now; swap for S3 (per-tenant prefix + KMS) in production."""
import re
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

from app.config import get_settings

ALLOWED_EXTENSIONS = {
    ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".txt", ".csv", ".json", ".md",
    ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".zip", ".log", ".yaml", ".yml",
}


def safe_filename(name: str) -> str:
    name = Path(name or "file").name
    name = re.sub(r"[^A-Za-z0-9._ -]", "_", name).strip() or "file"
    return name[:200]


def _root() -> Path:
    root = get_settings().storage_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def save_upload(org_id: uuid.UUID, upload: UploadFile) -> tuple[str, str, int]:
    """Save an upload, return (key, original safe name, size). Enforces type and size limits."""
    name = safe_filename(upload.filename or "file")
    if Path(name).suffix.lower() not in ALLOWED_EXTENSIONS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"File type not allowed: {Path(name).suffix or 'none'}")
    limit = get_settings().max_upload_mb * 1024 * 1024
    key = f"{org_id}/{uuid.uuid4().hex}_{name}"
    path = _root() / key
    path.parent.mkdir(parents=True, exist_ok=True)
    size = 0
    with path.open("wb") as out:
        while chunk := upload.file.read(1024 * 1024):
            size += len(chunk)
            if size > limit:
                out.close()
                path.unlink(missing_ok=True)
                raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "File too large")
            out.write(chunk)
    return key, name, size


def path_for(org_id: uuid.UUID, key: str) -> Path:
    if not key.startswith(f"{org_id}/"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found")
    path = (_root() / key).resolve()
    if _root() not in path.parents or not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found")
    return path


def delete(key: str) -> None:
    if key:
        (_root() / key).unlink(missing_ok=True)
