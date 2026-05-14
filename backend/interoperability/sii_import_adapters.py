from __future__ import annotations

from typing import Any


def import_context_entity(payload: dict[str, Any]) -> dict[str, Any]:
    return {"imported": True, "entity": payload, "adapter": "sii_context_entity_adapter"}


def import_context_relationship(payload: dict[str, Any]) -> dict[str, Any]:
    return {"imported": True, "relationship": payload, "adapter": "sii_context_relationship_adapter"}

