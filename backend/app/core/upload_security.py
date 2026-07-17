from __future__ import annotations

import re
from pathlib import Path


_ALLOWED_CONTENT_TYPES = {
    ".csv": {"", "text/csv", "text/plain", "application/csv", "application/vnd.ms-excel", "application/octet-stream"},
    ".txt": {"", "text/plain", "text/csv", "application/octet-stream"},
    ".json": {"", "application/json", "text/json", "text/plain", "application/octet-stream"},
}


def sanitize_upload_filename(value: str | None, *, fallback: str = "upload.csv") -> str:
    raw = str(value or "").strip()
    basename = re.split(r"[\\/]", raw)[-1]
    basename = re.sub(r'[\x00-\x1f\x7f<>:"|?*]', "_", basename).strip(" .")
    if not basename:
        basename = fallback
    if len(basename) > 255:
        suffix = Path(basename).suffix[:20]
        stem_limit = max(1, 255 - len(suffix))
        basename = f"{Path(basename).stem[:stem_limit]}{suffix}"
    return basename


def validate_telemetry_upload(filename: str, content_type: str | None, *, allowed_extensions: set[str]) -> tuple[str, str]:
    sanitized = sanitize_upload_filename(filename)
    suffix = Path(sanitized).suffix.lower()
    if suffix not in allowed_extensions:
        if allowed_extensions == {".csv", ".json", ".txt"}:
            raise ValueError("Only .csv, .txt, and .json telemetry files are supported.")
        if allowed_extensions == {".csv"}:
            raise ValueError("Only CSV files are supported for the CSV connector.")
        allowed = ", ".join(sorted(allowed_extensions))
        raise ValueError(f"Only {allowed} telemetry files are supported.")
    normalized_type = str(content_type or "").split(";", 1)[0].strip().lower()
    if normalized_type not in _ALLOWED_CONTENT_TYPES.get(suffix, {""}):
        raise ValueError("Uploaded file content type does not match its telemetry file extension.")
    return sanitized, normalized_type


def contains_binary_markers(content: bytes | bytearray) -> bool:
    return b"\x00" in content
