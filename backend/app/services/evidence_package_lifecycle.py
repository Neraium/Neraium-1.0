from __future__ import annotations

import json
import threading
from typing import Any
from uuid import uuid5

from pydantic import BaseModel, ConfigDict, Field

from app.services.evidence_package import (
    LifecycleActor,
    LifecycleEvent,
    LifecycleEventType,
    LifecycleProvenance,
    LifecycleStatus,
    PACKAGE_NAMESPACE,
    PackageLifecycle,
    _timestamp,
)


LIFECYCLE_SCHEMA_VERSION = "evidence-package-lifecycle-v1"
_LIFECYCLE_LOCK = threading.RLock()


class LifecycleTransitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timestamp: str
    actor: LifecycleActor
    event_type: LifecycleEventType
    reason: str = Field(min_length=1, max_length=2000)
    metadata: dict[str, Any] = Field(default_factory=dict)


def initial_lifecycle(package: dict[str, Any]) -> PackageLifecycle:
    existing = package.get("lifecycle")
    if isinstance(existing, dict):
        return PackageLifecycle.model_validate(existing)
    timestamp = _timestamp(package.get("created_at"))
    if timestamp is None:
        raise ValueError("package_created_timestamp_invalid")
    canonical = timestamp[0]
    package_id = str(package.get("id") or "")
    event = LifecycleEvent(
        event_id=str(uuid5(PACKAGE_NAMESPACE, f"{package_id}:package_created:{canonical}")),
        timestamp=canonical,
        actor=LifecycleActor.system,
        event_type=LifecycleEventType.package_created,
        reason="Evidence Package created from the completed baseline comparison.",
        metadata={},
    )
    return PackageLifecycle(
        status=LifecycleStatus.OPEN,
        events=[event],
        provenance=LifecycleProvenance(schema_version=LIFECYCLE_SCHEMA_VERSION, source="lifecycle_event_store"),
    )


def lifecycle_status(event_type: LifecycleEventType) -> LifecycleStatus:
    return {
        LifecycleEventType.package_created: LifecycleStatus.OPEN,
        LifecycleEventType.package_acknowledged: LifecycleStatus.ACKNOWLEDGED,
        LifecycleEventType.package_resolved: LifecycleStatus.RESOLVED,
    }[event_type]


def append_lifecycle_event(
    package: dict[str, Any], lifecycle: PackageLifecycle, request: LifecycleTransitionRequest
) -> PackageLifecycle:
    if request.event_type is LifecycleEventType.package_created:
        raise ValueError("package_created_event_is_automatic")
    canonical_timestamp = _timestamp(request.timestamp)
    if canonical_timestamp is None:
        raise ValueError("lifecycle_timestamp_invalid")
    expected = {
        LifecycleStatus.OPEN: LifecycleEventType.package_acknowledged,
        LifecycleStatus.ACKNOWLEDGED: LifecycleEventType.package_resolved,
    }.get(lifecycle.status)
    if request.event_type is not expected:
        raise ValueError("invalid_lifecycle_transition")
    if lifecycle.events and canonical_timestamp[1] < _timestamp(lifecycle.events[-1].timestamp)[1]:
        raise ValueError("lifecycle_timestamp_precedes_latest_event")
    sequence = len(lifecycle.events) + 1
    canonical_metadata = json.dumps(request.metadata, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    identity = ":".join(
        (
            str(package["id"]),
            str(sequence),
            request.event_type.value,
            canonical_timestamp[0],
            request.actor.value,
            request.reason,
            canonical_metadata,
        )
    )
    event = LifecycleEvent(
        event_id=str(uuid5(PACKAGE_NAMESPACE, identity)),
        timestamp=canonical_timestamp[0],
        actor=request.actor,
        event_type=request.event_type,
        reason=request.reason,
        metadata=request.metadata,
    )
    return PackageLifecycle(
        status=lifecycle_status(event.event_type),
        events=[*lifecycle.events, event],
        provenance=lifecycle.provenance,
    )


def lifecycle_lock() -> threading.RLock:
    return _LIFECYCLE_LOCK
