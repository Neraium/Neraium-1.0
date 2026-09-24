"""Frozen target v1 semantic reader. Never used to produce current records."""
from __future__ import annotations


import hashlib


import json


from datetime import date, datetime


from typing import Any


SEMANTICS_VERSION = "governed-output-semantics.v1"


RUNTIME_ALIASES = ("generated_at", "analysis_id")


def canonical_json(value: Any) -> str:
    """Canonical JSON values; reject unsupported objects instead of repr hashing."""
    def plain(item: Any) -> Any:
        if isinstance(item, dict):
            if any(not isinstance(key, str) for key in item):
                raise TypeError("Canonical output mappings require string keys")
            return {key: plain(child) for key, child in item.items()}
        if isinstance(item, (set, frozenset)):
            return sorted((plain(child) for child in item), key=canonical_json)
        if isinstance(item, (list, tuple)):
            return [plain(child) for child in item]
        if isinstance(item, (datetime, date)):
            return item.isoformat()
        return item
    return json.dumps(plain(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def semantic_content(value: Any) -> Any:
    """Read the declared contract, retaining every source and analytical field.

No timestamp names, time paths, evidence lists or thresholds are ignored. Legacy
aliases are recognized only on newly marked governed roots, not arbitrary data.
"""
    if isinstance(value, dict):
        aliases = RUNTIME_ALIASES if value.get("output_semantics") == SEMANTICS_VERSION else ()
        return {key: semantic_content(child) for key, child in value.items()
                if key != "runtime_metadata" and key not in aliases}
    if isinstance(value, list):
        return [semantic_content(child) for child in value]
    return value


def semantic_digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(semantic_content(value)).encode()).hexdigest()


