"""Read-only historical Aletheia EVP compatibility.

Records are opaque, version-owned artifacts: original doctrine records and the
later content_identity variant are returned unchanged. No generation or sealing.
"""
from __future__ import annotations

import json
from typing import Any
from app.core.config import get_settings

EVP_LOG_PATH = get_settings().runtime_dir / "evidence" / "evp_records.jsonl"


def list_evp_records(*, limit: int = 100, operator_visible: bool | None = None) -> list[dict[str, Any]]:
    if not EVP_LOG_PATH.exists():
        return []
    records: list[dict[str, Any]] = []
    try:
        with EVP_LOG_PATH.open("r", encoding="utf-8") as handle:
            for line in handle:
                text = line.strip()
                if not text:
                    continue
                item = json.loads(text)
                if operator_visible is not None and bool(item.get("operator_visible")) is not operator_visible:
                    continue
                records.append(item)
    except Exception:
        return []
    records.reverse()
    return records[: max(1, min(limit, 1000))]
