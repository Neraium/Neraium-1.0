from __future__ import annotations

import re
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any
from urllib.parse import unquote


class StoragePathError(ValueError):
    """Controlled validation error for unsafe storage paths."""

    def __init__(self, code: str = "invalid_storage_path") -> None:
        self.code = code
        super().__init__("Invalid storage path.")


_INVALID_PERCENT_ENCODING = re.compile(r"%(?![0-9A-Fa-f]{2})")
_UPLOAD_SUFFIXES = {".csv", ".json", ".txt"}


def _decode_storage_value(value: str) -> str:
    decoded = value
    for _ in range(3):
        next_value = unquote(decoded)
        if next_value == decoded:
            return decoded
        decoded = next_value
    return decoded


def _coerce_relative_storage_path(value: str | Path | None) -> PurePosixPath:
    if value is None:
        raise StoragePathError()
    raw = str(value).strip()
    if not raw or raw in {".", "./"}:
        raise StoragePathError()
    if _INVALID_PERCENT_ENCODING.search(raw):
        raise StoragePathError()

    decoded = _decode_storage_value(raw).strip()
    if not decoded or decoded in {".", "./"} or "\x00" in decoded:
        raise StoragePathError()
    if any(ord(char) < 32 for char in decoded):
        raise StoragePathError()
    if "\\" in decoded:
        raise StoragePathError()
    if Path(decoded).is_absolute():
        raise StoragePathError()

    windows_path = PureWindowsPath(decoded)
    if windows_path.drive or windows_path.root:
        raise StoragePathError()

    relative = PurePosixPath(decoded)
    if relative.is_absolute():
        raise StoragePathError()
    if any(part in {"", ".", ".."} for part in relative.parts):
        raise StoragePathError()
    return relative


def ensure_storage_root(root: str | Path) -> Path:
    storage_root = Path(root)
    storage_root.mkdir(parents=True, exist_ok=True)
    return storage_root.resolve(strict=True)


def resolve_storage_path(root: str | Path, requested_path: str | Path | None) -> Path:
    storage_root = ensure_storage_root(root)
    relative = _coerce_relative_storage_path(requested_path)
    candidate = storage_root / Path(*relative.parts)
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(storage_root)
    except ValueError as exc:
        raise StoragePathError() from exc
    return resolved


def resolve_existing_storage_path(root: str | Path, requested_path: str | Path | None) -> Path:
    storage_root = ensure_storage_root(root)
    relative = _coerce_relative_storage_path(requested_path)
    candidate = storage_root / Path(*relative.parts)
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(storage_root)
    except (OSError, ValueError) as exc:
        raise StoragePathError() from exc
    return resolved


def storage_key_for_server_path(root: str | Path, server_path: str | Path) -> str:
    storage_root = ensure_storage_root(root)
    try:
        resolved = Path(server_path).resolve(strict=True)
        relative = resolved.relative_to(storage_root)
    except (OSError, ValueError) as exc:
        raise StoragePathError() from exc
    return relative.as_posix()


def safe_upload_suffix(filename: Any, default: str = ".csv") -> str:
    raw = str(filename or "").strip()
    if _INVALID_PERCENT_ENCODING.search(raw):
        return default
    decoded = _decode_storage_value(raw)
    if "\x00" in decoded or any(ord(char) < 32 for char in decoded):
        return default
    suffix = PurePosixPath(decoded.replace("\\", "/")).suffix.lower()
    return suffix if suffix in _UPLOAD_SUFFIXES else default
