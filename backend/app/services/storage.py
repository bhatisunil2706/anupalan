"""Evidence file storage with per-organisation encryption.

Every file is encrypted with AES-256-GCM before it is written. Each organisation gets its own data key derived
from the master key (HKDF), and the storage key is bound in as associated data, so a file copied to another
organisation's path can't be decrypted. Backends: local disk, or S3 (which additionally applies SSE-KMS).
Uploads are checked against their claimed type by file signature, and optionally scanned by ClamAV.
"""
import base64
import logging
import os
import re
import socket
import struct
import uuid
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from fastapi import HTTPException, UploadFile, status
from fastapi.responses import Response

from app.config import get_settings

log = logging.getLogger("storage")
MAGIC = b"ANPE1"

BINARY_SIGNATURES = {
    ".pdf": [b"%PDF-"],
    ".png": [b"\x89PNG\r\n\x1a\n"],
    ".jpg": [b"\xff\xd8\xff"],
    ".jpeg": [b"\xff\xd8\xff"],
    ".gif": [b"GIF87a", b"GIF89a"],
    ".webp": [b"RIFF"],
    ".zip": [b"PK\x03\x04", b"PK\x05\x06"],
    ".docx": [b"PK\x03\x04"],
    ".xlsx": [b"PK\x03\x04"],
    ".pptx": [b"PK\x03\x04"],
    ".doc": [b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"],
    ".xls": [b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"],
    ".ppt": [b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"],
}
TEXT_EXTENSIONS = {".txt", ".csv", ".json", ".md", ".log", ".yaml", ".yml"}
ALLOWED_EXTENSIONS = set(BINARY_SIGNATURES) | TEXT_EXTENSIONS
CONTENT_TYPES = {
    ".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".gif": "image/gif", ".webp": "image/webp", ".zip": "application/zip",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".doc": "application/msword", ".xls": "application/vnd.ms-excel", ".ppt": "application/vnd.ms-powerpoint",
    ".csv": "text/csv", ".json": "application/json",
}


def safe_filename(name: str) -> str:
    name = Path(name or "file").name
    name = re.sub(r"[^A-Za-z0-9._ -]", "_", name).strip(" .") or "file"
    return name[:200]


def content_type_for(name: str) -> str:
    return CONTENT_TYPES.get(Path(name).suffix.lower(), "text/plain")


# ---------------------------------------------------------------- validation


def validate_content(name: str, data: bytes) -> None:
    ext = Path(name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"File type not allowed: {ext or 'none'}")
    if ext in BINARY_SIGNATURES:
        ok = any(data.startswith(sig) for sig in BINARY_SIGNATURES[ext])
        if ext == ".webp":
            ok = ok and data[8:12] == b"WEBP"
        if not ok:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                f"The file's content doesn't match its {ext} extension")
    else:
        if b"\x00" in data:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Text files can't contain binary data")
        try:
            data.decode("utf-8-sig")
        except UnicodeDecodeError as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Text files must be UTF-8 encoded") from e


def clamav_scan(data: bytes, address: str) -> str | None:
    """Return the malware signature name if ClamAV finds one, else None. Raises OSError if unreachable."""
    host, _, port = address.rpartition(":")
    with socket.create_connection((host, int(port)), timeout=30) as s:
        s.sendall(b"zINSTREAM\0")
        for i in range(0, len(data), 64 * 1024):
            chunk = data[i:i + 64 * 1024]
            s.sendall(struct.pack("!L", len(chunk)) + chunk)
        s.sendall(struct.pack("!L", 0))
        reply = s.recv(4096).decode(errors="replace").strip("\0\n ")
    if reply.endswith("FOUND"):
        return reply.split(":", 1)[-1].replace("FOUND", "").strip()
    if not reply.endswith("OK"):
        raise OSError(f"Unexpected ClamAV reply: {reply}")
    return None


def scan_for_malware(data: bytes) -> None:
    address = get_settings().clamav_address
    if not address:
        return
    try:
        found = clamav_scan(data, address)
    except OSError as e:
        log.error("malware scanner unavailable: %s", e)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "Uploads are paused because the malware scanner is unavailable") from e
    if found:
        log.warning("malware blocked: %s", found)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This file was blocked by the malware scanner")


# ---------------------------------------------------------------- encryption


@lru_cache
def _master_key() -> bytes:
    raw = base64.urlsafe_b64decode(get_settings().encryption_key.encode())
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=b"anupalan-storage-master",
                info=b"evidence").derive(raw)


@lru_cache(maxsize=1024)
def _org_key(org_id: uuid.UUID) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=b"anupalan-storage-org", info=org_id.bytes).derive(
        _master_key())


def encrypt(org_id: uuid.UUID, key: str, data: bytes) -> bytes:
    nonce = os.urandom(12)
    return MAGIC + nonce + AESGCM(_org_key(org_id)).encrypt(nonce, data, key.encode())


def decrypt(org_id: uuid.UUID, key: str, blob: bytes) -> bytes:
    if not blob.startswith(MAGIC):
        return blob  # stored before encryption was introduced
    nonce, ct = blob[len(MAGIC):len(MAGIC) + 12], blob[len(MAGIC) + 12:]
    return AESGCM(_org_key(org_id)).decrypt(nonce, ct, key.encode())


# ---------------------------------------------------------------- backends


class LocalBackend:
    def _root(self) -> Path:
        root = get_settings().storage_dir.resolve()
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _path(self, key: str) -> Path:
        path = (self._root() / key).resolve()
        if self._root() not in path.parents:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found")
        return path

    def put(self, key: str, blob: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(blob)
        os.chmod(path, 0o600)

    def get(self, key: str) -> bytes:
        path = self._path(key)
        if not path.exists():
            raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found")
        return path.read_bytes()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)


class S3Backend:
    def __init__(self) -> None:
        import boto3

        s = get_settings()
        self.bucket, self.prefix, self.kms = s.s3_bucket, s.s3_prefix.strip("/"), s.s3_kms_key_id
        self.s3 = boto3.client("s3", region_name=s.s3_region)

    def _k(self, key: str) -> str:
        return f"{self.prefix}/{key}" if self.prefix else key

    def put(self, key: str, blob: bytes) -> None:
        extra = {"ServerSideEncryption": "aws:kms", "SSEKMSKeyId": self.kms} if self.kms else {
            "ServerSideEncryption": "AES256"}
        self.s3.put_object(Bucket=self.bucket, Key=self._k(key), Body=blob, **extra)

    def get(self, key: str) -> bytes:
        try:
            return self.s3.get_object(Bucket=self.bucket, Key=self._k(key))["Body"].read()
        except self.s3.exceptions.NoSuchKey as e:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found") from e

    def delete(self, key: str) -> None:
        self.s3.delete_object(Bucket=self.bucket, Key=self._k(key))


@lru_cache
def backend():
    return S3Backend() if get_settings().storage_backend == "s3" else LocalBackend()


# ---------------------------------------------------------------- public API


def _new_key(org_id: uuid.UUID, name: str) -> str:
    return f"{org_id}/{uuid.uuid4().hex}_{name}"


def store(org_id: uuid.UUID, name: str, data: bytes) -> tuple[str, str, int]:
    name = safe_filename(name)
    key = _new_key(org_id, name)
    backend().put(key, encrypt(org_id, key, data))
    return key, name, len(data)


def save_upload(org_id: uuid.UUID, upload: UploadFile) -> tuple[str, str, int]:
    """Validate, scan, encrypt and store an upload. Returns (key, safe name, size)."""
    name = safe_filename(upload.filename or "file")
    limit = get_settings().max_upload_mb * 1024 * 1024
    data = upload.file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "File too large")
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The file is empty")
    validate_content(name, data)
    scan_for_malware(data)
    return store(org_id, name, data)


def save_bytes(org_id: uuid.UUID, name: str, data: bytes) -> tuple[str, str, int]:
    """Store generated content (e.g. an access review export)."""
    return store(org_id, name, data)


def _check_owner(org_id: uuid.UUID, key: str) -> None:
    if not key or not key.startswith(f"{org_id}/"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found")


def read(org_id: uuid.UUID, key: str) -> bytes:
    _check_owner(org_id, key)
    return decrypt(org_id, key, backend().get(key))


def delete(org_id: uuid.UUID, key: str) -> None:
    if key and key.startswith(f"{org_id}/"):
        backend().delete(key)


def download_response(org_id: uuid.UUID, key: str, filename: str) -> Response:
    data = read(org_id, key)
    safe = safe_filename(filename)
    return Response(data, media_type=content_type_for(safe), headers={
        "Content-Disposition": f"attachment; filename=\"{safe}\"; filename*=UTF-8''{quote(safe)}",
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'; sandbox",
        "Cache-Control": "private, no-store",
    })
