"""Frozen source v1 semantic reader. Never used to produce current records."""
from __future__ import annotations


import hashlib


import json


from collections.abc import Mapping


from datetime import date, datetime


from typing import Any


SEMANTICS_VERSION = "governed-output-semantics.v1"


RUNTIME_VERSION = "execution-metadata.v1"


def canonical_json(value: Any) -> str:
    """Canonical semantic encoding; never used to rewrite canonical artifacts."""
    def plain(item: Any) -> Any:
        if isinstance(item, Mapping):
            if any(not isinstance(key, str) for key in item):
                raise TypeError("Canonical mappings require string keys")
            return {key: plain(child) for key, child in item.items()}
        if isinstance(item, (set, frozenset)):
            return sorted((plain(child) for child in item), key=canonical_json)
        if isinstance(item, (list, tuple)):
            return [plain(child) for child in item]
        if isinstance(item, datetime):
            return item.isoformat(sep=" ")
        if isinstance(item, date):
            return item.isoformat()
        return item
    # Match legacy result storage's nonfinite tokens without collapsing to null.
    # The separate immutable artifact contract continues to reject nonfinite JSON.
    return json.dumps(plain(value), sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=True)


def semantic_content(value: Any) -> Any:
    if isinstance(value, Mapping):
        aliases = {"generated_at"} if value.get("output_semantics") == SEMANTICS_VERSION else set()
        return {key: semantic_content(child) for key, child in value.items()
                if not (key == "runtime_metadata" and isinstance(child, Mapping)
                        and child.get("contract_version") == RUNTIME_VERSION)
                and key not in aliases}
    if isinstance(value, (list, tuple)):
        return [semantic_content(child) for child in value]
    if isinstance(value, (set, frozenset)):
        return sorted((semantic_content(child) for child in value), key=canonical_json)
    return value


def semantic_digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(semantic_content(value)).encode("utf-8")).hexdigest()


