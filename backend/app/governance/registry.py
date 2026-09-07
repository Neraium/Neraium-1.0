"""Scoped append-only version registries over the existing atomic runtime ledger."""
from __future__ import annotations

from datetime import datetime
from typing import TypeVar, TYPE_CHECKING

if TYPE_CHECKING:
    from app.governance.authority_store import AuthorityDecisionStore
from app.governance.contracts import ContentRecord, Timestamp, _timestamp

Record = TypeVar("Record", bound=ContentRecord)


def time(value: str) -> datetime:
    return datetime.fromisoformat(_timestamp(value))


def covers(start: Timestamp, end: Timestamp | None, at: str) -> bool:
    """Half-open effective intervals: [start, end)."""
    return time(start) <= time(at) and (end is None or time(at) < time(end))


class VersionRegistry:
    def __init__(self, storage: AuthorityDecisionStore, record_type: type[Record], namespace: str):
        self.storage, self.record_type, self.namespace = storage, record_type, namespace

    def _key(self, scope, system_scope):
        return f"{self.namespace}::{self.storage._key(scope, system_scope)}"

    def append(self, scope, record: Record) -> Record:
        from app.governance.authority_store import AuthorityRecordConflict
        record = self.record_type.model_validate(record.as_dict())
        system_scope = record.registry_scope
        key = self._key(scope, system_scope)

        def update(raw):
            ledger = self.storage._ledger(raw, scope, system_scope)
            records = [self.record_type.model_validate(item) for item in ledger["records"]]
            if record in records:
                return ledger
            chain = [item for item in records if item.registry_identity == record.registry_identity]
            if chain:
                previous = chain[-1]
                if (record.supersedes != previous.record_id or record.registry_version != previous.registry_version + 1
                        or time(record.created_at) < time(previous.created_at)):
                    raise AuthorityRecordConflict("invalid_registry_successor")
            elif record.registry_version != 1 or record.supersedes is not None:
                raise AuthorityRecordConflict("registry_predecessor_missing")
            ledger["records"].append(record.as_dict())
            return ledger

        self.storage._mutate(key, update)
        return self.record_type.model_validate(record.as_dict())

    def history(self, scope, system_scope: str) -> tuple[Record, ...]:
        ledger = self.storage._ledger(self.storage._read(self._key(scope, system_scope)), scope, system_scope)
        return tuple(self.record_type.model_validate(item) for item in ledger["records"])

    def as_of(self, scope, system_scope: str, evaluated_at: str) -> tuple[Record, ...]:
        # Return known history, including invalidation and expired versions.
        return tuple(item for item in self.history(scope, system_scope) if time(item.created_at) <= time(evaluated_at))
