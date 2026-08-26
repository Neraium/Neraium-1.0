"""PostgreSQL repository foundation for scoped production telemetry.

Every operation requires the complete server-attested resource scope.  Public
connection projections are deliberately enumerated and never include secret
binding IDs or internal secret references.
"""

from __future__ import annotations

import json
import logging
import math
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import re
from typing import Any, Callable, Iterator, Mapping, Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.services.telemetry_domain import (
    CheckpointMode,
    ConnectionHealthState,
    ConnectionLifecycleStatus,
    ConnectorType,
    HealthFacetStatus,
    TelemetryScopeRef,
    require_connection_transition,
    reject_sensitive_telemetry_fields,
    sanitize_telemetry_public_value,
)
from app.services.telemetry_units import conversion_contract
from app.services.phase4_scope import (
    ServerBoundSystemIdentityV2,
    build_telemetry_server_bound_system_identity,
)
from app.services.telemetry_result_artifact import (
    CanonicalResultArtifact,
    canonical_result_id,
)
from app.engine.sii.behavioral_model_contract import AuthenticatedPhase4Scope


ConnectionFactory = Callable[[], Any]
logger = logging.getLogger(__name__)


class TelemetryRepositoryError(RuntimeError):
    """Base class for stable repository failures."""


class TelemetryLeaseLost(TelemetryRepositoryError):
    """The caller no longer owns the requested connection lease."""


class TelemetryCheckpointConflict(TelemetryRepositoryError):
    """Checkpoint compare-and-swap revision did not match."""


class TelemetryMappingConflict(TelemetryRepositoryError):
    """A mapping revision or enabled canonical hierarchy conflicts."""


class TelemetryResultArtifactConflict(TelemetryRepositoryError):
    """An immutable result identity already names different artifact bytes."""


TelemetryRepositoryScope = TelemetryScopeRef


def _phase4_scope(scope: TelemetryRepositoryScope) -> AuthenticatedPhase4Scope:
    _scope_parameters(scope)
    phase4_scope = AuthenticatedPhase4Scope(
        tenant_scope_id=scope.tenant_scope_id,
        workspace_id=scope.workspace_id,
        resource_scope_id=scope.resource_scope_id,
    )
    if scope.facility_id != phase4_scope.workspace_id:
        raise ValueError("telemetry_repository_facility_scope_mismatch")
    return phase4_scope


def _scope_parameters(scope: TelemetryScopeRef) -> tuple[str, str, str, str]:
    if not isinstance(scope, TelemetryScopeRef):
        raise TypeError("telemetry_repository_scope_required")
    return (
        scope.resource_scope_id,
        scope.tenant_scope_id,
        scope.workspace_id,
        scope.facility_id,
    )


_PUBLIC_CONNECTION_COLUMNS = """
    c.id, c.tenant_scope_id, c.workspace_id, c.resource_scope_id, c.facility_id,
    c.name, c.connector_type, c.lifecycle_status, c.enabled, c.safe_config,
    c.timezone, c.polling_interval_seconds, c.next_attempt_at,
    c.last_attempt_at, c.last_success_at, c.last_healthy_at,
    c.last_telemetry_at, c.last_error_code, c.last_error_summary,
    c.retry_count, c.created_by, c.updated_by, c.created_at, c.updated_at,
    c.archived_at,
    EXISTS (
        SELECT 1 FROM telemetry.connection_secret_bindings sb
        WHERE sb.resource_scope_id = c.resource_scope_id
          AND sb.connection_id = c.id
    ) AS credentials_configured
"""

_PUBLIC_SIGNAL_COLUMNS = """
    s.id, s.connection_id, s.external_tag_id, s.external_tag_name,
    s.display_label, s.source_unit, s.sample_cadence_seconds, s.enabled,
    s.mapping_status, s.last_observed_at, s.quality_state,
    s.source_metadata, s.created_at, s.updated_at,
    m.id AS mapping_id, m.system_id, m.asset_id,
    m.canonical_concept_id AS canonical_signal_id,
    m.canonical_signal_name, m.canonical_unit, m.conversion_id,
    m.conversion_version, m.source_timezone, m.expected_cadence_seconds,
    m.provenance, m.provenance_reason, m.mapped_by, m.mapped_at,
    m.revision AS mapping_revision
"""

_MAPPING_PROVENANCE = frozenset(
    {"manual", "approved_suggestion", "imported_verified"}
)

def _require_identifier(value: str, code: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(code)
    return normalized


_PUBLIC_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}$")
_SHA256_DIGEST = re.compile(r"^[0-9a-f]{64}$")


def _require_public_identifier(value: str, code: str) -> str:
    normalized = _require_identifier(value, code)
    if not _PUBLIC_IDENTIFIER.fullmatch(normalized):
        raise ValueError(code)
    return normalized


def _require_uuid(value: str, code: str) -> str:
    normalized = _require_identifier(value, code)
    try:
        return str(uuid.UUID(normalized))
    except (AttributeError, TypeError, ValueError) as error:
        raise ValueError(code) from error


def _supported_unit_identity(value: str) -> str | None:
    contract = conversion_contract(
        source_unit=value,
        canonical_unit=value,
        expected_dimension=None,
    )
    conversion_id = contract.get("conversion_id")
    if not contract.get("valid") or not isinstance(conversion_id, str):
        return None
    return conversion_id.partition("_to_")[0]


def _safe_json(
    value: Mapping[str, Any],
    *,
    code: str,
    reject_sensitive: bool = False,
) -> str:
    if reject_sensitive:
        reject_sensitive_telemetry_fields(value, code=code)
    try:
        encoded = json.dumps(dict(value), separators=(",", ":"), sort_keys=True)
    except (TypeError, ValueError) as exc:
        raise ValueError(code) from exc
    if len(encoded.encode("utf-8")) > 65_536:
        raise ValueError(code)
    return encoded


def _safe_audit_detail(value: Mapping[str, Any]) -> str:
    sanitized = sanitize_telemetry_public_value(value)
    encoded = _safe_json(sanitized, code="telemetry_audit_detail_invalid")
    if len(encoded.encode("utf-8")) > 16_384:
        raise ValueError("telemetry_audit_detail_invalid")
    return encoded


def _safe_json_records(
    records: Sequence[Mapping[str, Any]], *, code: str, limit: int = 5_000
) -> str:
    if len(records) > limit:
        raise ValueError(code)
    try:
        def encode_extra(value: Any) -> str:
            if isinstance(value, datetime):
                if value.tzinfo is None or value.utcoffset() is None:
                    raise TypeError("naive_datetime")
                return value.astimezone(UTC).isoformat()
            if isinstance(value, uuid.UUID):
                return str(value)
            if isinstance(value, Decimal):
                return str(value)
            raise TypeError(type(value).__name__)

        encoded = json.dumps(
            [dict(record) for record in records],
            separators=(",", ":"),
            default=encode_extra,
        )
    except (TypeError, ValueError) as error:
        raise ValueError(code) from error
    if len(encoded.encode("utf-8")) > 8_388_608:
        raise ValueError(code)
    return encoded


def _safe_error_fields(code: str, summary: str | None) -> tuple[str, str | None]:
    error_code = _require_public_identifier(code, "telemetry_ingestion_error_code_invalid")
    error_summary = str(summary).strip() if summary else None
    if error_summary is not None:
        if len(error_summary) > 500:
            raise ValueError("telemetry_ingestion_error_summary_invalid")
        reject_sensitive_telemetry_fields(
            {"error_summary": error_summary}, code="telemetry_ingestion_error_summary_invalid"
        )
        lowered = error_summary.lower()
        if any(marker in lowered for marker in ("authorization:", "bearer ", "api_key=", "token=")):
            raise ValueError("telemetry_ingestion_error_summary_invalid")
    return error_code, error_summary


def _row_dict(cursor: Any, row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    if isinstance(row, Mapping):
        result = dict(row)
    else:
        names = [str(column.name if hasattr(column, "name") else column[0]) for column in cursor.description]
        result = dict(zip(names, row, strict=True))
    for key in (
        "safe_config",
        "cursor_payload",
        "details",
        "safe_detail",
        "source_metadata",
        "previous_details",
        "quality_summary",
        "authority_snapshot",
        "result_metadata",
        "evidence_lineage",
        "reference_metadata",
        "finding_ids",
        "evidence_ids",
    ):
        if isinstance(result.get(key), str):
            try:
                result[key] = json.loads(result[key])
            except (TypeError, ValueError):
                if key in {
                    "safe_config",
                    "details",
                    "safe_detail",
                    "source_metadata",
                    "previous_details",
                    "quality_summary",
                    "authority_snapshot",
                    "result_metadata",
                    "evidence_lineage",
                }:
                    result[key] = {}
    for key in (
        "safe_config",
        "details",
        "safe_detail",
        "source_metadata",
        "previous_details",
        "quality_summary",
        "authority_snapshot",
        "result_metadata",
        "evidence_lineage",
    ):
        if key in result:
            result[key] = sanitize_telemetry_public_value(result[key])
    return result


def _checkpoint_mode(value: CheckpointMode | str) -> str:
    try:
        return CheckpointMode(value).value
    except (TypeError, ValueError) as error:
        raise ValueError("telemetry_checkpoint_mode_invalid") from error


def _connector_type(value: ConnectorType | str) -> str:
    try:
        return ConnectorType(value).value
    except (TypeError, ValueError) as error:
        raise ValueError("telemetry_connector_type_invalid") from error


class PostgreSQLTelemetryRepository:
    """Repository for the shared PostgreSQL telemetry schema.

    The factory must return a psycopg-compatible connection.  There is no
    production SQLite fallback; unit tests can provide a recording fake.
    """

    def __init__(self, connection_factory: ConnectionFactory):
        if not callable(connection_factory):
            raise TypeError("telemetry_connection_factory_required")
        self._connection_factory = connection_factory

    @contextmanager
    def _connection(self) -> Iterator[Any]:
        connection = self._connection_factory()
        try:
            yield connection
            connection.commit()
        except Exception:
            rollback = getattr(connection, "rollback", None)
            if callable(rollback):
                rollback()
            raise
        finally:
            close = getattr(connection, "close", None)
            if callable(close):
                close()

    @staticmethod
    def _scope_predicate(alias: str = "c") -> str:
        return (
            f"{alias}.resource_scope_id = %s AND {alias}.tenant_scope_id = %s "
            f"AND {alias}.workspace_id = %s AND {alias}.facility_id = %s"
        )

    def create_connection(
        self,
        scope: TelemetryRepositoryScope,
        *,
        connection_id: str,
        name: str,
        connector_type: ConnectorType | str,
        safe_config: Mapping[str, Any],
        timezone_name: str,
        polling_interval_seconds: int,
        actor_id: str,
        audit_event_id: str | None = None,
        audit_safe_detail: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        connection_id = _require_identifier(connection_id, "telemetry_connection_id_required")
        name = _require_identifier(name, "telemetry_connection_name_required")
        actor_id = _require_identifier(actor_id, "telemetry_connection_actor_required")
        connector_type_value = _connector_type(connector_type)
        config_json = _safe_json(
            safe_config,
            code="telemetry_connection_safe_config_invalid",
            reject_sensitive=True,
        )
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO telemetry.data_connections (
                    id, tenant_scope_id, workspace_id, resource_scope_id, facility_id,
                    name, connector_type, safe_config, timezone,
                    polling_interval_seconds, created_by, updated_by
                ) VALUES (
                    %s::UUID, %s, %s, %s, %s, %s, %s, %s::JSONB, %s, %s, %s, %s
                )
                """,
                (
                    connection_id,
                    scope.tenant_scope_id,
                    scope.workspace_id,
                    scope.resource_scope_id,
                    scope.facility_id,
                    name,
                    connector_type_value,
                    config_json,
                    timezone_name,
                    int(polling_interval_seconds),
                    actor_id,
                    actor_id,
                ),
            )
            if audit_event_id is not None:
                self._insert_audit_event(
                    cursor,
                    scope,
                    event_id=_require_uuid(
                        audit_event_id, "telemetry_audit_event_id_invalid"
                    ),
                    connection_id=connection_id,
                    actor_id=actor_id,
                    action="connection_created",
                    safe_detail=audit_safe_detail or {},
                )
            return self._get_connection(cursor, scope, connection_id)

    def get_connection(
        self,
        scope: TelemetryRepositoryScope,
        connection_id: str,
    ) -> dict[str, Any] | None:
        with self._connection() as connection, connection.cursor() as cursor:
            return self._get_connection(cursor, scope, connection_id, required=False)

    def _get_connection(
        self,
        cursor: Any,
        scope: TelemetryRepositoryScope,
        connection_id: str,
        *,
        required: bool = True,
    ) -> dict[str, Any] | None:
        cursor.execute(
            f"""
            SELECT {_PUBLIC_CONNECTION_COLUMNS}
            FROM telemetry.data_connections c
            WHERE {self._scope_predicate('c')} AND c.id = %s::UUID
            """,
            (*_scope_parameters(scope), _require_identifier(connection_id, "telemetry_connection_id_required")),
        )
        record = _row_dict(cursor, cursor.fetchone())
        if required and record is None:
            raise TelemetryRepositoryError("telemetry_connection_not_found")
        return record

    def list_connections(
        self,
        scope: TelemetryRepositoryScope,
        *,
        include_archived: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        bounded_limit = min(max(int(limit), 1), 500)
        bounded_offset = max(int(offset), 0)
        archive_clause = "" if include_archived else "AND c.archived_at IS NULL"
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT {_PUBLIC_CONNECTION_COLUMNS}
                FROM telemetry.data_connections c
                WHERE {self._scope_predicate('c')} {archive_clause}
                ORDER BY c.updated_at DESC, c.id
                LIMIT %s OFFSET %s
                """,
                (*_scope_parameters(scope), bounded_limit, bounded_offset),
            )
            return [_row_dict(cursor, row) or {} for row in cursor.fetchall()]

    def update_connection_metadata(
        self,
        scope: TelemetryRepositoryScope,
        *,
        connection_id: str,
        actor_id: str,
        name: str | None = None,
        safe_config: Mapping[str, Any] | None = None,
        timezone_name: str | None = None,
        polling_interval_seconds: int | None = None,
    ) -> dict[str, Any] | None:
        """Patch only allow-listed non-secret connection metadata."""
        connection_id = _require_uuid(connection_id, "telemetry_connection_id_invalid")
        actor_id = _require_identifier(actor_id, "telemetry_connection_actor_required")
        assignments: list[str] = []
        values: list[Any] = []
        changed: list[str] = []
        if name is not None:
            normalized_name = _require_identifier(
                name, "telemetry_connection_name_required"
            )
            if len(normalized_name) > 160:
                raise ValueError("telemetry_connection_name_invalid")
            assignments.append("name = %s")
            values.append(normalized_name)
            changed.append("name")
        if safe_config is not None:
            assignments.append("safe_config = %s::JSONB")
            values.append(
                _safe_json(
                    safe_config,
                    code="telemetry_connection_safe_config_invalid",
                    reject_sensitive=True,
                )
            )
            changed.append("safe_config")
        if timezone_name is not None:
            timezone_value = _require_identifier(
                timezone_name, "telemetry_connection_timezone_required"
            )
            try:
                ZoneInfo(timezone_value)
            except ZoneInfoNotFoundError as error:
                raise ValueError("telemetry_connection_timezone_invalid") from error
            assignments.append("timezone = %s")
            values.append(timezone_value)
            changed.append("timezone")
        if polling_interval_seconds is not None:
            cadence = int(polling_interval_seconds)
            if cadence < 30 or cadence > 86_400:
                raise ValueError("telemetry_connection_polling_interval_invalid")
            assignments.append("polling_interval_seconds = %s")
            values.append(cadence)
            changed.append("polling_interval_seconds")
        if not assignments:
            return self.get_connection(scope, connection_id)
        assignments.extend(("updated_by = %s", "updated_at = NOW()"))
        values.append(actor_id)
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE telemetry.data_connections c
                SET {', '.join(assignments)}
                WHERE {self._scope_predicate('c')} AND c.id = %s::UUID
                  AND c.archived_at IS NULL
                RETURNING c.id
                """,
                (*values, *_scope_parameters(scope), connection_id),
            )
            if cursor.fetchone() is None:
                return None
            self._insert_audit_event(
                cursor,
                scope,
                event_id=str(uuid.uuid4()),
                connection_id=connection_id,
                actor_id=actor_id,
                action="connection_updated",
                safe_detail={"changed_fields": changed},
            )
            return self._get_connection(cursor, scope, connection_id)

    def set_connection_lifecycle(
        self,
        scope: TelemetryRepositoryScope,
        *,
        connection_id: str,
        target_status: ConnectionLifecycleStatus | str,
        actor_id: str,
        enabled: bool | None = None,
        last_attempt_at: datetime | None = None,
        last_success_at: datetime | None = None,
        last_healthy_at: datetime | None = None,
        last_telemetry_at: datetime | None = None,
        last_error_code: str | None = None,
        last_error_summary: str | None = None,
    ) -> dict[str, Any] | None:
        """Apply an ordinary lifecycle transition with bounded safe status data."""
        connection_id = _require_uuid(connection_id, "telemetry_connection_id_invalid")
        actor_id = _require_identifier(actor_id, "telemetry_connection_actor_required")
        target = ConnectionLifecycleStatus(target_status)
        for value in (
            last_attempt_at,
            last_success_at,
            last_healthy_at,
            last_telemetry_at,
        ):
            if value is not None and (value.tzinfo is None or value.utcoffset() is None):
                raise ValueError("telemetry_connection_status_timestamp_invalid")
        error_code = str(last_error_code).strip() if last_error_code else None
        if error_code is not None and not _PUBLIC_IDENTIFIER.fullmatch(error_code):
            raise ValueError("telemetry_connection_error_code_invalid")
        error_summary = str(last_error_summary).strip() if last_error_summary else None
        if error_summary is not None and (
            len(error_summary) > 500
            or "authorization:" in error_summary.lower()
            or "bearer " in error_summary.lower()
            or "api_key=" in error_summary.lower()
            or "token=" in error_summary.lower()
        ):
            raise ValueError("telemetry_connection_error_summary_invalid")
        if target in {
            ConnectionLifecycleStatus.DISABLED,
            ConnectionLifecycleStatus.ARCHIVED,
        } and enabled is True:
            raise ValueError("telemetry_connection_enabled_status_conflict")

        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT c.lifecycle_status, c.enabled
                FROM telemetry.data_connections c
                WHERE {self._scope_predicate('c')} AND c.id = %s::UUID
                  AND c.archived_at IS NULL
                FOR UPDATE
                """,
                (*_scope_parameters(scope), connection_id),
            )
            current = cursor.fetchone()
            if current is None:
                return None
            current_status = str(
                current[0]
                if not isinstance(current, Mapping)
                else current["lifecycle_status"]
            )
            if current_status != target.value:
                require_connection_transition(current_status, target)
            resulting_enabled = (
                bool(current[1] if not isinstance(current, Mapping) else current["enabled"])
                if enabled is None
                else bool(enabled)
            )
            if target is ConnectionLifecycleStatus.DISABLED:
                resulting_enabled = False
            cursor.execute(
                f"""
                UPDATE telemetry.data_connections c
                SET lifecycle_status = %s, enabled = %s,
                    last_attempt_at = COALESCE(%s, c.last_attempt_at),
                    last_success_at = COALESCE(%s, c.last_success_at),
                    last_healthy_at = COALESCE(%s, c.last_healthy_at),
                    last_telemetry_at = COALESCE(%s, c.last_telemetry_at),
                    last_error_code = %s, last_error_summary = %s,
                    updated_by = %s, updated_at = NOW()
                WHERE {self._scope_predicate('c')} AND c.id = %s::UUID
                RETURNING c.id
                """,
                (
                    target.value,
                    resulting_enabled,
                    last_attempt_at,
                    last_success_at,
                    last_healthy_at,
                    last_telemetry_at,
                    error_code,
                    error_summary,
                    actor_id,
                    *_scope_parameters(scope),
                    connection_id,
                ),
            )
            if cursor.fetchone() is None:
                return None
            if target is ConnectionLifecycleStatus.DISABLED:
                action = "connection_disabled"
            elif resulting_enabled and not bool(
                current[1] if not isinstance(current, Mapping) else current["enabled"]
            ):
                action = "connection_enabled"
            else:
                action = "connection_updated"
            self._insert_audit_event(
                cursor,
                scope,
                event_id=str(uuid.uuid4()),
                connection_id=connection_id,
                actor_id=actor_id,
                action=action,
                safe_detail={
                    "from_status": current_status,
                    "to_status": target.value,
                    "enabled": resulting_enabled,
                    "error_code": error_code,
                },
            )
            return self._get_connection(cursor, scope, connection_id)

    def archive_connection(
        self,
        scope: TelemetryRepositoryScope,
        *,
        connection_id: str,
        actor_id: str,
    ) -> dict[str, Any] | None:
        connection_id = _require_uuid(connection_id, "telemetry_connection_id_invalid")
        actor_id = _require_identifier(actor_id, "telemetry_connection_actor_required")
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT c.lifecycle_status
                FROM telemetry.data_connections c
                WHERE {self._scope_predicate('c')} AND c.id = %s::UUID
                  AND c.archived_at IS NULL
                FOR UPDATE
                """,
                (*_scope_parameters(scope), connection_id),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            current_status = str(
                row[0] if not isinstance(row, Mapping) else row["lifecycle_status"]
            )
            require_connection_transition(
                current_status, ConnectionLifecycleStatus.ARCHIVED
            )
            cursor.execute(
                f"""
                UPDATE telemetry.data_connections c
                SET lifecycle_status = 'archived', enabled = FALSE,
                    archived_at = NOW(), updated_by = %s, updated_at = NOW(),
                    lease_owner = NULL, lease_token = NULL, lease_expires_at = NULL
                WHERE {self._scope_predicate('c')} AND c.id = %s::UUID
                RETURNING c.id
                """,
                (actor_id, *_scope_parameters(scope), connection_id),
            )
            if cursor.fetchone() is None:
                return None
            self._insert_audit_event(
                cursor,
                scope,
                event_id=str(uuid.uuid4()),
                connection_id=connection_id,
                actor_id=actor_id,
                action="connection_archived",
                safe_detail={"from_status": current_status},
            )
            return self._get_connection(cursor, scope, connection_id)

    def upsert_secret_binding(
        self,
        scope: TelemetryRepositoryScope,
        *,
        connection_id: str,
        binding_id: str,
        provider: str,
        internal_reference: str,
        version_marker: str | None,
        actor_id: str | None = None,
        audit_event_id: str | None = None,
        audit_safe_detail: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Store an opaque secret reference and return only safe status metadata."""
        connection_id = _require_identifier(connection_id, "telemetry_connection_id_required")
        binding_id = _require_identifier(binding_id, "telemetry_secret_binding_id_required")
        internal_reference = _require_identifier(
            internal_reference, "telemetry_secret_internal_reference_required"
        )
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT c.id FROM telemetry.data_connections c
                WHERE {self._scope_predicate('c')} AND c.id = %s::UUID
                FOR UPDATE
                """,
                (*_scope_parameters(scope), connection_id),
            )
            if cursor.fetchone() is None:
                raise TelemetryRepositoryError("telemetry_connection_not_found")
            cursor.execute(
                """
                INSERT INTO telemetry.connection_secret_bindings (
                    id, tenant_scope_id, workspace_id, resource_scope_id, facility_id,
                    connection_id, provider, internal_reference, version_marker
                ) VALUES (%s::UUID, %s, %s, %s, %s, %s::UUID, %s, %s, %s)
                ON CONFLICT (resource_scope_id, connection_id) DO UPDATE SET
                    id = EXCLUDED.id,
                    provider = EXCLUDED.provider,
                    internal_reference = EXCLUDED.internal_reference,
                    version_marker = EXCLUDED.version_marker,
                    updated_at = NOW()
                """,
                (
                    binding_id,
                    scope.tenant_scope_id,
                    scope.workspace_id,
                    scope.resource_scope_id,
                    scope.facility_id,
                    connection_id,
                    provider,
                    internal_reference,
                    version_marker,
                ),
            )
            cursor.execute(
                f"""
                UPDATE telemetry.data_connections c
                SET secret_binding_id = %s::UUID, updated_at = NOW()
                WHERE {self._scope_predicate('c')} AND c.id = %s::UUID
                """,
                (binding_id, *_scope_parameters(scope), connection_id),
            )
            if audit_event_id is not None:
                self._insert_audit_event(
                    cursor,
                    scope,
                    event_id=_require_uuid(
                        audit_event_id, "telemetry_audit_event_id_invalid"
                    ),
                    connection_id=connection_id,
                    actor_id=_require_identifier(
                        actor_id, "telemetry_audit_actor_required"
                    ),
                    action="credential_binding_changed",
                    safe_detail=audit_safe_detail or {},
                )
        return {"credentials_configured": True, "version_marker": version_marker}

    def resolve_internal_secret_reference(
        self,
        scope: TelemetryRepositoryScope,
        connection_id: str,
    ) -> tuple[str, str, str | None]:
        """Compatibility worker lookup; prefer :meth:`load_secret_binding`."""
        binding = self.load_secret_binding(scope, connection_id=connection_id)
        if binding is None:
            raise TelemetryRepositoryError("telemetry_secret_binding_not_found")
        fields = binding.internal_persistence_fields()
        return (
            str(fields["provider"]),
            str(fields["internal_reference"]),
            str(fields["version_marker"]) if fields["version_marker"] is not None else None,
        )

    def load_secret_binding(
        self,
        scope: TelemetryRepositoryScope,
        *,
        connection_id: str,
    ) -> Any | None:
        """Return an opaque server-only binding for an in-scope connection.

        The return type is intentionally not a mapping and has no public
        serialization method containing the internal reference.
        """
        from app.services.telemetry_secrets import SecretBinding

        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT sb.id, sb.provider, sb.resource_scope_id,
                    sb.connection_id, sb.internal_reference, sb.version_marker,
                    sb.updated_at
                FROM telemetry.data_connections c
                JOIN telemetry.connection_secret_bindings sb
                  ON sb.resource_scope_id = c.resource_scope_id
                 AND sb.tenant_scope_id = c.tenant_scope_id
                 AND sb.workspace_id = c.workspace_id
                 AND sb.facility_id = c.facility_id
                 AND sb.connection_id = c.id
                WHERE {self._scope_predicate('c')} AND c.id = %s::UUID
                  AND c.archived_at IS NULL
                """,
                (
                    *_scope_parameters(scope),
                    _require_uuid(connection_id, "telemetry_connection_id_invalid"),
                ),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            values = (
                dict(row)
                if isinstance(row, Mapping)
                else dict(
                    zip(
                        (
                            "id",
                            "provider",
                            "resource_scope_id",
                            "connection_id",
                            "internal_reference",
                            "version_marker",
                            "updated_at",
                        ),
                        row,
                        strict=False,
                    )
                )
            )
            return SecretBinding.from_internal_persistence(
                binding_id=str(values["id"]),
                provider=str(values["provider"]),
                resource_scope_id=str(values["resource_scope_id"]),
                connection_id=str(values["connection_id"]),
                internal_reference=str(values["internal_reference"]),
                version_marker=(
                    str(values["version_marker"])
                    if values.get("version_marker") is not None
                    else None
                ),
                updated_at=values.get("updated_at"),
            )

    def claim_due_connection(
        self,
        scope: TelemetryRepositoryScope,
        *,
        worker_id: str,
        lease_seconds: int,
        now: datetime,
    ) -> dict[str, Any] | None:
        """Claim one due connection without overlapping another worker."""
        worker_id = _require_identifier(worker_id, "telemetry_worker_id_required")
        bounded_lease = min(max(int(lease_seconds), 30), 3600)
        lease_token = str(uuid.uuid4())
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""
                WITH candidate AS (
                    SELECT c.id
                    FROM telemetry.data_connections c
                    WHERE {self._scope_predicate('c')}
                      AND c.enabled = TRUE
                      AND c.archived_at IS NULL
                      AND c.next_attempt_at <= %s
                      AND (c.lease_expires_at IS NULL OR c.lease_expires_at <= %s)
                    ORDER BY c.next_attempt_at, c.id
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                UPDATE telemetry.data_connections c
                SET lease_owner = %s, lease_token = %s::UUID,
                    lease_expires_at = %s + make_interval(secs => %s),
                    last_attempt_at = %s, updated_at = %s
                FROM candidate
                WHERE c.id = candidate.id AND {self._scope_predicate('c')}
                RETURNING c.id, c.connector_type, c.safe_config, c.timezone,
                    c.polling_interval_seconds, c.lease_token, c.lease_expires_at
                """,
                (
                    *_scope_parameters(scope),
                    now,
                    now,
                    worker_id,
                    lease_token,
                    now,
                    bounded_lease,
                    now,
                    now,
                    *_scope_parameters(scope),
                ),
            )
            return _row_dict(cursor, cursor.fetchone())

    def claim_next_due_work(
        self,
        *,
        worker_id: str,
        now: datetime,
        lease_seconds: int = 120,
    ) -> dict[str, Any] | None:
        """Globally claim one due item and create/activate its run atomically.

        Worker scope is reconstructed exclusively from the selected row.  A
        malformed legacy/global row therefore causes rollback instead of being
        assigned to a tenant by the worker.
        """
        worker_id = _require_public_identifier(worker_id, "telemetry_worker_id_invalid")
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("telemetry_worker_clock_invalid")
        bounded_lease = min(max(int(lease_seconds), 30), 3600)
        lease_token = str(uuid.uuid4())
        with self._connection() as connection, connection.cursor() as cursor:
            candidate: dict[str, Any] | None = None
            scope: TelemetryScopeRef | None = None
            # Drain a bounded number of malformed legacy/global rows without
            # allowing the earliest one to starve every valid tenant scope.
            for _ in range(32):
                cursor.execute(
                    """
                    SELECT c.id, c.tenant_scope_id, c.workspace_id,
                           c.resource_scope_id, c.facility_id, c.connector_type,
                           c.safe_config, c.timezone, c.polling_interval_seconds,
                           pending.id AS pending_run_id, pending.mode AS pending_mode,
                           pending.status AS pending_status,
                           pending.range_start, pending.range_end
                    FROM telemetry.data_connections c
                    LEFT JOIN LATERAL (
                        SELECT r.id, r.mode, r.status, r.range_start, r.range_end
                        FROM telemetry.ingestion_runs r
                        WHERE r.resource_scope_id = c.resource_scope_id
                          AND r.tenant_scope_id = c.tenant_scope_id
                          AND r.workspace_id = c.workspace_id
                          AND r.facility_id = c.facility_id
                          AND r.connection_id = c.id
                          AND r.mode IN ('incremental', 'backfill', 'retry')
                          AND r.status IN ('pending', 'running')
                        ORDER BY (r.status = 'running') DESC, r.created_at, r.id
                        LIMIT 1
                    ) pending ON TRUE
                    WHERE c.enabled = TRUE AND c.archived_at IS NULL
                      AND (c.lease_expires_at IS NULL OR c.lease_expires_at <= %s)
                      AND c.next_attempt_at <= %s
                    ORDER BY (pending.id IS NOT NULL) DESC, c.next_attempt_at, c.id
                    FOR UPDATE OF c SKIP LOCKED
                    LIMIT 1
                    """,
                    (now, now),
                )
                candidate = _row_dict(cursor, cursor.fetchone())
                if candidate is None:
                    return None
                try:
                    # TelemetryScopeRef verifies the canonical Phase 4 resource
                    # identity before any lease or run is assigned.
                    scope = TelemetryScopeRef(
                        tenant_scope_id=str(candidate.get("tenant_scope_id") or ""),
                        workspace_id=str(candidate.get("workspace_id") or ""),
                        resource_scope_id=str(candidate.get("resource_scope_id") or ""),
                        facility_id=str(candidate.get("facility_id") or ""),
                    )
                    break
                except (TypeError, ValueError):
                    invalid_connection_id = _require_uuid(
                        str(candidate.get("id") or ""),
                        "telemetry_connection_id_invalid",
                    )
                    cursor.execute(
                        """
                        UPDATE telemetry.data_connections
                        SET enabled = FALSE, lifecycle_status = 'error',
                            last_error_code = 'telemetry_scope_invalid',
                            last_error_summary = 'Connection requires scope remediation.',
                            lease_owner = NULL, lease_token = NULL,
                            lease_expires_at = NULL, updated_at = NOW()
                        WHERE id = %s::UUID AND enabled = TRUE
                        """,
                        (invalid_connection_id,),
                    )
                    logger.error(
                        "telemetry_legacy_scope_quarantined",
                        extra={
                            "event": "telemetry_legacy_scope_quarantined",
                            "connection_id": invalid_connection_id,
                            "reason": "invalid_server_scope",
                        },
                    )
                    candidate = None
                    scope = None
            if candidate is None or scope is None:
                return None
            connection_id = _require_uuid(str(candidate["id"]), "telemetry_connection_id_invalid")
            cursor.execute(
                f"""
                UPDATE telemetry.data_connections c
                SET lease_owner = %s, lease_token = %s::UUID,
                    lease_expires_at = %s + make_interval(secs => %s),
                    last_attempt_at = %s, updated_at = %s
                WHERE {self._scope_predicate('c')} AND c.id = %s::UUID
                  AND c.enabled = TRUE AND c.archived_at IS NULL
                RETURNING c.lease_expires_at
                """,
                (
                    worker_id,
                    lease_token,
                    now,
                    bounded_lease,
                    now,
                    now,
                    *_scope_parameters(scope),
                    connection_id,
                ),
            )
            lease_row = cursor.fetchone()
            if lease_row is None:
                raise TelemetryLeaseLost("telemetry_connection_claim_lost")
            lease_expires_at = (
                lease_row.get("lease_expires_at")
                if isinstance(lease_row, Mapping)
                else lease_row[0]
            )
            pending_run_id = candidate.get("pending_run_id")
            if pending_run_id:
                run_id = _require_uuid(str(pending_run_id), "telemetry_ingestion_run_id_invalid")
                run_mode = str(candidate.get("pending_mode") or "backfill")
                cursor.execute(
                    """
                    UPDATE telemetry.ingestion_runs r
                    SET status = 'running', lease_token = %s::UUID,
                        worker_id = %s, started_at = %s,
                        attempt_count = r.attempt_count + 1, updated_at = %s
                    WHERE r.resource_scope_id = %s AND r.tenant_scope_id = %s
                      AND r.workspace_id = %s AND r.facility_id = %s
                      AND r.connection_id = %s::UUID AND r.id = %s::UUID
                      AND r.mode IN ('incremental', 'backfill', 'retry')
                      AND r.status IN ('pending', 'running')
                    RETURNING r.id
                    """,
                    (
                        lease_token,
                        worker_id,
                        now,
                        now,
                        *_scope_parameters(scope),
                        connection_id,
                        run_id,
                    ),
                )
                if cursor.fetchone() is None:
                    raise TelemetryLeaseLost("telemetry_backfill_claim_lost")
            else:
                run_id = str(uuid.uuid4())
                run_mode = "incremental"
                cursor.execute(
                    """
                    INSERT INTO telemetry.ingestion_runs (
                        id, tenant_scope_id, workspace_id, resource_scope_id,
                        facility_id, connection_id, mode, status, lease_token,
                        started_at, attempt_count, retry_count, worker_id
                    ) VALUES (
                        %s::UUID, %s, %s, %s, %s, %s::UUID, 'incremental',
                        'running', %s::UUID, %s, 1, 0, %s
                    )
                    """,
                    (
                        run_id,
                        scope.tenant_scope_id,
                        scope.workspace_id,
                        scope.resource_scope_id,
                        scope.facility_id,
                        connection_id,
                        lease_token,
                        now,
                        worker_id,
                    ),
                )
            candidate.update(
                {
                    "scope": scope,
                    "connection_id": connection_id,
                    "run_id": run_id,
                    "run_mode": run_mode,
                    "checkpoint_mode": (
                        "backfill"
                        if candidate.get("range_start") is not None
                        and candidate.get("range_end") is not None
                        else "incremental"
                    ),
                    "lease_token": lease_token,
                    "lease_expires_at": lease_expires_at,
                }
            )
            candidate.pop("pending_run_id", None)
            candidate.pop("pending_mode", None)
            candidate.pop("pending_status", None)
            return candidate

    def load_ingestion_snapshot(
        self,
        scope: TelemetryRepositoryScope,
        *,
        connection_id: str,
        run_id: str,
        lease_token: str,
        checkpoint_mode: CheckpointMode | str = CheckpointMode.INCREMENTAL,
    ) -> dict[str, Any]:
        """Load one lease-attested immutable worker execution snapshot."""
        from app.services.telemetry_secrets import SecretBinding

        connection_id = _require_uuid(connection_id, "telemetry_connection_id_invalid")
        run_id = _require_uuid(run_id, "telemetry_ingestion_run_id_invalid")
        lease_token = _require_uuid(lease_token, "telemetry_lease_token_invalid")
        mode = _checkpoint_mode(checkpoint_mode)
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT c.id, c.tenant_scope_id, c.workspace_id,
                       c.resource_scope_id, c.facility_id, c.enabled,
                       c.connector_type, c.safe_config, c.timezone,
                       c.polling_interval_seconds, c.lease_expires_at,
                       r.id AS run_id, r.mode AS run_mode, r.range_start,
                       r.range_end, sb.id AS binding_id, sb.provider,
                       sb.internal_reference, sb.version_marker, sb.updated_at
                FROM telemetry.data_connections c
                JOIN telemetry.ingestion_runs r
                  ON r.resource_scope_id = c.resource_scope_id
                 AND r.tenant_scope_id = c.tenant_scope_id
                 AND r.workspace_id = c.workspace_id
                 AND r.facility_id = c.facility_id
                 AND r.connection_id = c.id
                LEFT JOIN telemetry.connection_secret_bindings sb
                  ON sb.resource_scope_id = c.resource_scope_id
                 AND sb.tenant_scope_id = c.tenant_scope_id
                 AND sb.workspace_id = c.workspace_id
                 AND sb.facility_id = c.facility_id
                 AND sb.connection_id = c.id
                WHERE {self._scope_predicate('c')} AND c.id = %s::UUID
                  AND c.lease_token = %s::UUID AND c.lease_expires_at > NOW()
                  AND r.id = %s::UUID AND r.lease_token = c.lease_token
                  AND r.status = 'running'
                FOR SHARE OF c, r
                """,
                (*_scope_parameters(scope), connection_id, lease_token, run_id),
            )
            connection_record = _row_dict(cursor, cursor.fetchone())
            if connection_record is None:
                raise TelemetryLeaseLost("telemetry_connection_lease_lost")
            cursor.execute(
                """
                SELECT m.id AS mapping_id, m.external_signal_id,
                       s.external_tag_id, m.system_id, m.asset_id,
                       m.canonical_concept_id, m.canonical_signal_name,
                       m.source_unit, m.canonical_unit, m.conversion_id,
                       m.conversion_version, m.source_timezone,
                       m.expected_cadence_seconds, concept.physical_dimension
                           AS expected_dimension, m.provenance,
                       m.mapped_by, m.mapped_at, m.authority_digest,
                       m.revision
                FROM telemetry.signal_mappings m
                JOIN telemetry.external_signals s
                  ON s.resource_scope_id = m.resource_scope_id
                 AND s.tenant_scope_id = m.tenant_scope_id
                 AND s.workspace_id = m.workspace_id
                 AND s.facility_id = m.facility_id
                 AND s.connection_id = m.connection_id
                 AND s.id = m.external_signal_id
                JOIN telemetry.canonical_signal_concepts concept
                  ON concept.id = m.canonical_concept_id
                WHERE m.resource_scope_id = %s AND m.tenant_scope_id = %s
                  AND m.workspace_id = %s AND m.facility_id = %s
                  AND m.connection_id = %s::UUID AND m.enabled = TRUE
                  AND s.enabled = TRUE AND s.mapping_status = 'mapped'
                ORDER BY s.external_tag_id, m.id
                """,
                (*_scope_parameters(scope), connection_id),
            )
            mappings = [_row_dict(cursor, row) or {} for row in cursor.fetchall()]
            for mapping in mappings:
                mapping["scope"] = scope
                mapping["connection_id"] = connection_id
            cursor.execute(
                """
                SELECT cp.mode, cp.cursor_payload, cp.high_water_at, cp.revision,
                       cp.updated_run_id, cp.updated_at
                FROM telemetry.connection_checkpoints cp
                WHERE cp.resource_scope_id = %s AND cp.tenant_scope_id = %s
                  AND cp.workspace_id = %s AND cp.facility_id = %s
                  AND cp.connection_id = %s::UUID AND cp.mode = %s
                """,
                (*_scope_parameters(scope), connection_id, mode),
            )
            checkpoint = _row_dict(cursor, cursor.fetchone()) or {
                "mode": mode,
                "cursor_payload": {},
                "high_water_at": None,
                "revision": 0,
                "updated_run_id": None,
                "updated_at": None,
            }
            secret_binding = None
            if connection_record.get("binding_id") is not None:
                secret_binding = SecretBinding.from_internal_persistence(
                    binding_id=str(connection_record.pop("binding_id")),
                    provider=str(connection_record.pop("provider")),
                    resource_scope_id=scope.resource_scope_id,
                    connection_id=connection_id,
                    internal_reference=str(connection_record.pop("internal_reference")),
                    version_marker=(
                        str(connection_record.get("version_marker"))
                        if connection_record.get("version_marker") is not None
                        else None
                    ),
                    updated_at=connection_record.pop("updated_at", None),
                )
                connection_record.pop("version_marker", None)
            else:
                for key in ("binding_id", "provider", "internal_reference", "version_marker"):
                    connection_record.pop(key, None)
            return {
                "connection": connection_record,
                "scope": scope,
                "run_id": run_id,
                "run_mode": str(connection_record["run_mode"]),
                "range_start": connection_record.get("range_start"),
                "range_end": connection_record.get("range_end"),
                "secret_binding": secret_binding,
                "mappings": mappings,
                "checkpoint": checkpoint,
            }

    def renew_lease(
        self,
        scope: TelemetryRepositoryScope,
        *,
        connection_id: str,
        lease_token: str,
        lease_seconds: int,
        now: datetime,
    ) -> bool:
        bounded_lease = min(max(int(lease_seconds), 30), 3600)
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE telemetry.data_connections c
                SET lease_expires_at = %s + make_interval(secs => %s), updated_at = %s
                WHERE {self._scope_predicate('c')} AND c.id = %s::UUID
                  AND c.lease_token = %s::UUID AND c.lease_expires_at > %s
                """,
                (
                    now,
                    bounded_lease,
                    now,
                    *_scope_parameters(scope),
                    _require_identifier(connection_id, "telemetry_connection_id_required"),
                    _require_identifier(lease_token, "telemetry_lease_token_required"),
                    now,
                ),
            )
            return cursor.rowcount == 1

    def release_lease(
        self,
        scope: TelemetryRepositoryScope,
        *,
        connection_id: str,
        lease_token: str,
        next_attempt_at: datetime | None,
    ) -> bool:
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE telemetry.data_connections c
                SET lease_owner = NULL, lease_token = NULL, lease_expires_at = NULL,
                    next_attempt_at = %s, updated_at = NOW()
                WHERE {self._scope_predicate('c')} AND c.id = %s::UUID
                  AND c.lease_token = %s::UUID
                """,
                (
                    next_attempt_at,
                    *_scope_parameters(scope),
                    _require_identifier(connection_id, "telemetry_connection_id_required"),
                    _require_identifier(lease_token, "telemetry_lease_token_required"),
                ),
            )
            return cursor.rowcount == 1

    def get_checkpoint(
        self,
        scope: TelemetryRepositoryScope,
        *,
        connection_id: str,
        mode: CheckpointMode | str,
    ) -> dict[str, Any] | None:
        mode_value = _checkpoint_mode(mode)
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT cp.mode, cp.cursor_payload, cp.high_water_at, cp.revision,
                    cp.updated_run_id, cp.updated_at
                FROM telemetry.connection_checkpoints cp
                WHERE cp.resource_scope_id = %s AND cp.tenant_scope_id = %s
                  AND cp.workspace_id = %s AND cp.facility_id = %s
                  AND cp.connection_id = %s::UUID AND cp.mode = %s
                """,
                (
                    *_scope_parameters(scope),
                    _require_identifier(connection_id, "telemetry_connection_id_required"),
                    mode_value,
                ),
            )
            return _row_dict(cursor, cursor.fetchone())

    def advance_checkpoint(
        self,
        scope: TelemetryRepositoryScope,
        *,
        connection_id: str,
        mode: CheckpointMode | str,
        expected_revision: int,
        cursor_payload: Mapping[str, Any],
        high_water_at: datetime | None,
        updated_run_id: str,
        lease_token: str,
    ) -> int:
        """Advance a checkpoint with lease validation and revision CAS."""
        mode_value = _checkpoint_mode(mode)
        cursor_json = _safe_json(cursor_payload, code="telemetry_checkpoint_cursor_invalid")
        connection_id = _require_identifier(connection_id, "telemetry_connection_id_required")
        updated_run_id = _require_identifier(updated_run_id, "telemetry_ingestion_run_id_required")
        lease_token = _require_identifier(lease_token, "telemetry_lease_token_required")
        if int(expected_revision) < 0:
            raise ValueError("telemetry_checkpoint_revision_invalid")
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT c.id FROM telemetry.data_connections c
                WHERE {self._scope_predicate('c')} AND c.id = %s::UUID
                  AND c.lease_token = %s::UUID AND c.lease_expires_at > NOW()
                FOR UPDATE
                """,
                (*_scope_parameters(scope), connection_id, lease_token),
            )
            if cursor.fetchone() is None:
                raise TelemetryLeaseLost("telemetry_connection_lease_lost")

            if int(expected_revision) == 0:
                cursor.execute(
                    """
                    INSERT INTO telemetry.connection_checkpoints (
                        tenant_scope_id, workspace_id, resource_scope_id, facility_id,
                        connection_id, mode, cursor_payload, high_water_at,
                        revision, updated_run_id
                    ) VALUES (%s, %s, %s, %s, %s::UUID, %s, %s::JSONB, %s, 1, %s::UUID)
                    ON CONFLICT (resource_scope_id, connection_id, mode) DO NOTHING
                    RETURNING revision
                    """,
                    (
                        scope.tenant_scope_id,
                        scope.workspace_id,
                        scope.resource_scope_id,
                        scope.facility_id,
                        connection_id,
                        mode_value,
                        cursor_json,
                        high_water_at,
                        updated_run_id,
                    ),
                )
            else:
                cursor.execute(
                    """
                    UPDATE telemetry.connection_checkpoints cp
                    SET cursor_payload = %s::JSONB, high_water_at = %s,
                        revision = cp.revision + 1, updated_run_id = %s::UUID,
                        updated_at = NOW()
                    WHERE cp.resource_scope_id = %s AND cp.tenant_scope_id = %s
                      AND cp.workspace_id = %s AND cp.facility_id = %s
                      AND cp.connection_id = %s::UUID AND cp.mode = %s
                      AND cp.revision = %s
                    RETURNING cp.revision
                    """,
                    (
                        cursor_json,
                        high_water_at,
                        updated_run_id,
                        *_scope_parameters(scope),
                        connection_id,
                        mode_value,
                        int(expected_revision),
                    ),
                )
            row = cursor.fetchone()
            if row is None:
                raise TelemetryCheckpointConflict("telemetry_checkpoint_revision_conflict")
            return int(row[0])

    def upsert_external_signals(
        self,
        scope: TelemetryRepositoryScope,
        *,
        connection_id: str,
        signals: Sequence[Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        """Register discovery results without approving them for analysis.

        Rediscovery may refresh descriptive source metadata, but it cannot enable
        a signal or alter an existing mapping. New tags always begin unmapped,
        disabled, and mapping-required.
        """
        connection_id = _require_uuid(
            connection_id, "telemetry_connection_id_invalid"
        )
        if len(signals) > 10_000:
            raise ValueError("telemetry_signal_discovery_batch_too_large")
        prepared: list[dict[str, Any]] = []
        seen: set[str] = set()
        for raw in signals:
            signal_id = _require_uuid(
                str(raw.get("signal_id") or ""), "telemetry_signal_id_invalid"
            )
            external_tag_id = _require_public_identifier(
                str(raw.get("external_tag_id") or ""),
                "telemetry_external_tag_id_invalid",
            )
            if external_tag_id in seen:
                raise ValueError("telemetry_external_tag_duplicate_in_batch")
            seen.add(external_tag_id)
            external_tag_name = _require_identifier(
                str(raw.get("external_tag_name") or ""),
                "telemetry_external_tag_name_required",
            )
            if len(external_tag_name) > 512:
                raise ValueError("telemetry_external_tag_name_invalid")
            label = str(raw["display_label"]).strip() if raw.get("display_label") else None
            source_unit = str(raw["source_unit"]).strip() if raw.get("source_unit") else None
            cadence = raw.get("sample_cadence_seconds")
            cadence_value = float(cadence) if cadence is not None else None
            if cadence_value is not None and (
                not math.isfinite(cadence_value) or cadence_value <= 0
            ):
                raise ValueError("telemetry_signal_cadence_invalid")
            metadata = raw.get("metadata") or {}
            if not isinstance(metadata, Mapping):
                raise ValueError("telemetry_signal_metadata_invalid")
            metadata_json = _safe_json(
                metadata,
                code="telemetry_signal_metadata_invalid",
                reject_sensitive=True,
            )
            prepared.append(
                {
                    "signal_id": signal_id,
                    "external_tag_id": external_tag_id,
                    "external_tag_name": external_tag_name,
                    "display_label": label,
                    "source_unit": source_unit,
                    "sample_cadence_seconds": cadence_value,
                    "source_metadata": json.loads(metadata_json),
                }
            )

        returned: list[dict[str, Any]] = []
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT c.id FROM telemetry.data_connections c
                WHERE {self._scope_predicate('c')} AND c.id = %s::UUID
                  AND c.archived_at IS NULL
                FOR UPDATE
                """,
                (*_scope_parameters(scope), connection_id),
            )
            if cursor.fetchone() is None:
                raise TelemetryRepositoryError("telemetry_connection_not_found")
            # A discovery page is inserted set-wise. Chunks bound PostgreSQL
            # parameter memory while avoiding one network round trip per tag.
            for start in range(0, len(prepared), 250):
                chunk = prepared[start : start + 250]
                cursor.execute(
                    """
                    INSERT INTO telemetry.external_signals (
                        id, tenant_scope_id, workspace_id, resource_scope_id,
                        facility_id, connection_id, external_tag_id,
                        external_tag_name, display_label, source_unit,
                        sample_cadence_seconds, enabled, mapping_status,
                        quality_state, source_metadata
                    )
                    SELECT d.signal_id, %s, %s, %s, %s, %s::UUID,
                        d.external_tag_id, d.external_tag_name, d.display_label,
                        d.source_unit, d.sample_cadence_seconds,
                        FALSE, 'unmapped', 'mapping_required', d.source_metadata
                    FROM jsonb_to_recordset(%s::JSONB) AS d(
                        signal_id UUID,
                        external_tag_id TEXT,
                        external_tag_name TEXT,
                        display_label TEXT,
                        source_unit TEXT,
                        sample_cadence_seconds DOUBLE PRECISION,
                        source_metadata JSONB
                    )
                    ON CONFLICT (resource_scope_id, connection_id, external_tag_id)
                    DO UPDATE SET
                        external_tag_name = EXCLUDED.external_tag_name,
                        display_label = EXCLUDED.display_label,
                        source_unit = EXCLUDED.source_unit,
                        sample_cadence_seconds = EXCLUDED.sample_cadence_seconds,
                        source_metadata = EXCLUDED.source_metadata,
                        updated_at = NOW()
                    RETURNING id, connection_id, external_tag_id,
                        external_tag_name, display_label, source_unit,
                        sample_cadence_seconds, enabled, mapping_status,
                        last_observed_at, quality_state, source_metadata,
                        created_at, updated_at
                    """,
                    (
                        scope.tenant_scope_id,
                        scope.workspace_id,
                        scope.resource_scope_id,
                        scope.facility_id,
                        connection_id,
                        json.dumps(chunk, separators=(",", ":"), sort_keys=True),
                    ),
                )
                returned.extend(
                    _row_dict(cursor, row) or {} for row in cursor.fetchall()
                )
        order = {
            item["external_tag_id"]: index for index, item in enumerate(prepared)
        }
        return sorted(
            returned,
            key=lambda item: order.get(str(item.get("external_tag_id") or ""), len(order)),
        )

    def list_external_signals(
        self,
        scope: TelemetryRepositoryScope,
        *,
        connection_id: str,
        mapping_status: str | None = None,
        limit: int = 250,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        connection_id = _require_uuid(
            connection_id, "telemetry_connection_id_invalid"
        )
        statuses = {"unmapped", "mapped", "invalid", "disabled"}
        if mapping_status is not None and mapping_status not in statuses:
            raise ValueError("telemetry_signal_mapping_status_invalid")
        status_clause = "" if mapping_status is None else "AND s.mapping_status = %s"
        parameters: list[Any] = [*_scope_parameters(scope), connection_id]
        if mapping_status is not None:
            parameters.append(mapping_status)
        parameters.extend((min(max(int(limit), 1), 500), max(int(offset), 0)))
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT {_PUBLIC_SIGNAL_COLUMNS}
                FROM telemetry.data_connections c
                JOIN telemetry.external_signals s
                  ON s.resource_scope_id = c.resource_scope_id
                 AND s.tenant_scope_id = c.tenant_scope_id
                 AND s.workspace_id = c.workspace_id
                 AND s.facility_id = c.facility_id
                 AND s.connection_id = c.id
                LEFT JOIN telemetry.signal_mappings m
                  ON m.resource_scope_id = s.resource_scope_id
                 AND m.tenant_scope_id = s.tenant_scope_id
                 AND m.workspace_id = s.workspace_id
                 AND m.facility_id = s.facility_id
                 AND m.external_signal_id = s.id
                 AND m.enabled = TRUE
                WHERE {self._scope_predicate('c')} AND c.id = %s::UUID
                  {status_clause}
                ORDER BY s.external_tag_name, s.id
                LIMIT %s OFFSET %s
                """,
                tuple(parameters),
            )
            return [_row_dict(cursor, row) or {} for row in cursor.fetchall()]

    def get_external_signal(
        self,
        scope: TelemetryRepositoryScope,
        *,
        connection_id: str,
        signal_id: str,
    ) -> dict[str, Any] | None:
        """Read one signal through its connection's complete authority scope."""
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT {_PUBLIC_SIGNAL_COLUMNS}
                FROM telemetry.data_connections c
                JOIN telemetry.external_signals s
                  ON s.resource_scope_id = c.resource_scope_id
                 AND s.tenant_scope_id = c.tenant_scope_id
                 AND s.workspace_id = c.workspace_id
                 AND s.facility_id = c.facility_id
                 AND s.connection_id = c.id
                LEFT JOIN telemetry.signal_mappings m
                  ON m.resource_scope_id = s.resource_scope_id
                 AND m.tenant_scope_id = s.tenant_scope_id
                 AND m.workspace_id = s.workspace_id
                 AND m.facility_id = s.facility_id
                 AND m.external_signal_id = s.id
                 AND m.enabled = TRUE
                WHERE {self._scope_predicate('c')} AND c.id = %s::UUID
                  AND s.id = %s::UUID
                """,
                (
                    *_scope_parameters(scope),
                    _require_uuid(connection_id, "telemetry_connection_id_invalid"),
                    _require_uuid(signal_id, "telemetry_signal_id_invalid"),
                ),
            )
            return _row_dict(cursor, cursor.fetchone())

    def list_canonical_signal_concepts(
        self,
        *,
        active_only: bool = True,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        """Read the global Neraium-owned taxonomy; no write seam is exposed."""
        active_clause = "WHERE cc.active = TRUE" if active_only else ""
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT cc.id, cc.canonical_name, cc.display_name,
                    cc.physical_dimension, cc.canonical_unit, cc.description,
                    cc.taxonomy_version, cc.active
                FROM telemetry.canonical_signal_concepts cc
                {active_clause}
                ORDER BY cc.canonical_name, cc.taxonomy_version DESC
                LIMIT %s
                """,
                (min(max(int(limit), 1), 1000),),
            )
            return [_row_dict(cursor, row) or {} for row in cursor.fetchall()]

    def get_mapping_context(
        self,
        scope: TelemetryRepositoryScope,
        *,
        connection_id: str,
        signal_id: str,
        canonical_concept_id: str,
    ) -> dict[str, Any] | None:
        """Resolve source and canonical concept through a scoped signal."""
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT s.id AS signal_id, s.connection_id, s.source_unit,
                       s.external_tag_id, s.mapping_status,
                       cc.id AS canonical_concept_id,
                       cc.canonical_name, cc.display_name,
                       cc.physical_dimension, cc.canonical_unit,
                       cc.taxonomy_version
                FROM telemetry.data_connections c
                JOIN telemetry.external_signals s
                  ON s.resource_scope_id = c.resource_scope_id
                 AND s.tenant_scope_id = c.tenant_scope_id
                 AND s.workspace_id = c.workspace_id
                 AND s.facility_id = c.facility_id
                 AND s.connection_id = c.id
                JOIN telemetry.canonical_signal_concepts cc
                  ON cc.id = %s::UUID AND cc.active = TRUE
                WHERE {self._scope_predicate('c')} AND c.id = %s::UUID
                  AND s.id = %s::UUID AND c.archived_at IS NULL
                """,
                (
                    _require_uuid(
                        canonical_concept_id,
                        "telemetry_canonical_concept_id_invalid",
                    ),
                    *_scope_parameters(scope),
                    _require_uuid(connection_id, "telemetry_connection_id_invalid"),
                    _require_uuid(signal_id, "telemetry_signal_id_invalid"),
                ),
            )
            return _row_dict(cursor, cursor.fetchone())

    def save_signal_mapping(
        self,
        scope: TelemetryRepositoryScope,
        *,
        mapping_id: str,
        event_id: str,
        connection_id: str,
        signal_id: str,
        system_id: str,
        asset_id: str | None,
        canonical_concept_id: str,
        canonical_signal_name: str,
        source_unit: str,
        canonical_unit: str,
        conversion_id: str,
        conversion_version: str,
        expected_cadence_seconds: float | None,
        source_timezone: str,
        provenance: str,
        provenance_reason: str | None,
        actor_id: str,
        authority_digest: str,
        mapped_at: datetime,
        authority_snapshot: Mapping[str, Any] | None = None,
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        """Create or revise the one enabled mapping for a scoped signal."""
        mapping_id = _require_uuid(mapping_id, "telemetry_mapping_id_invalid")
        event_id = _require_uuid(event_id, "telemetry_audit_event_id_invalid")
        connection_id = _require_uuid(connection_id, "telemetry_connection_id_invalid")
        signal_id = _require_uuid(signal_id, "telemetry_signal_id_invalid")
        canonical_concept_id = _require_uuid(
            canonical_concept_id, "telemetry_canonical_concept_id_invalid"
        )
        system_id = _require_public_identifier(system_id, "telemetry_system_id_invalid")
        asset_id = (
            _require_public_identifier(asset_id, "telemetry_asset_id_invalid")
            if asset_id is not None
            else None
        )
        canonical_signal_name = _require_public_identifier(
            canonical_signal_name, "telemetry_canonical_signal_name_invalid"
        )
        actor_id = _require_identifier(actor_id, "telemetry_mapping_actor_required")
        authority_digest = _require_identifier(
            authority_digest, "telemetry_mapping_authority_digest_required"
        )
        if not _SHA256_DIGEST.fullmatch(authority_digest):
            raise ValueError("telemetry_mapping_authority_digest_invalid")
        snapshot = (
            dict(authority_snapshot)
            if isinstance(authority_snapshot, Mapping)
            else {
                "contract_version": "telemetry-analysis-authority-snapshot.v1",
                "facility_id": scope.facility_id,
                "system_id": system_id,
                "asset_id": asset_id,
            }
        )
        if (
            str(snapshot.get("facility_id") or "") != scope.facility_id
            or str(snapshot.get("system_id") or "") != system_id
            or (str(snapshot.get("asset_id") or "").strip() or None) != asset_id
        ):
            raise ValueError("telemetry_mapping_authority_snapshot_mismatch")
        authority_snapshot_json = _safe_json(
            snapshot,
            code="telemetry_mapping_authority_snapshot_invalid",
            reject_sensitive=True,
        )
        authority_identity = build_telemetry_server_bound_system_identity(
            scope=_phase4_scope(scope),
            system_id=system_id,
            authority_record_digest=authority_digest,
        )
        authority_snapshot_id = str(
            uuid.uuid5(
                uuid.UUID("5ec0cc5f-d88f-56a3-8d3b-704b0140bdea"),
                "\0".join(
                    (
                        scope.resource_scope_id,
                        system_id,
                        asset_id or "",
                        authority_digest,
                    )
                ),
            )
        )
        if provenance not in _MAPPING_PROVENANCE:
            raise ValueError("telemetry_mapping_provenance_invalid")
        if expected_cadence_seconds is not None and (
            not math.isfinite(expected_cadence_seconds)
            or expected_cadence_seconds <= 0
            or expected_cadence_seconds > 86_400
        ):
            raise ValueError("telemetry_mapping_cadence_invalid")
        if mapped_at.tzinfo is None or mapped_at.utcoffset() is None:
            raise ValueError("telemetry_mapping_timestamp_invalid")
        if expected_revision is not None and int(expected_revision) < 1:
            raise ValueError("telemetry_mapping_revision_invalid")

        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT s.id, s.source_unit, cc.physical_dimension
                FROM telemetry.data_connections c
                JOIN telemetry.external_signals s
                  ON s.resource_scope_id = c.resource_scope_id
                 AND s.tenant_scope_id = c.tenant_scope_id
                 AND s.workspace_id = c.workspace_id
                 AND s.facility_id = c.facility_id
                 AND s.connection_id = c.id
                JOIN telemetry.canonical_signal_concepts cc
                  ON cc.id = %s::UUID AND cc.active = TRUE
                 AND cc.canonical_name = %s AND cc.canonical_unit = %s
                WHERE {self._scope_predicate('c')} AND c.id = %s::UUID
                  AND s.id = %s::UUID AND c.archived_at IS NULL
                FOR UPDATE OF s
                """,
                (
                    canonical_concept_id,
                    canonical_signal_name,
                    canonical_unit,
                    *_scope_parameters(scope),
                    connection_id,
                    signal_id,
                ),
            )
            source_context = cursor.fetchone()
            if source_context is None:
                raise TelemetryRepositoryError("telemetry_signal_or_concept_not_found")
            if isinstance(source_context, Mapping):
                discovered_unit = source_context.get("source_unit")
                physical_dimension = source_context.get("physical_dimension")
            else:
                discovered_unit = source_context[1]
                physical_dimension = source_context[2]
            if discovered_unit and _supported_unit_identity(
                str(discovered_unit)
            ) != _supported_unit_identity(source_unit):
                raise ValueError("telemetry_mapping_source_unit_mismatch")
            unit_contract = conversion_contract(
                source_unit=source_unit,
                canonical_unit=canonical_unit,
                expected_dimension=str(physical_dimension or ""),
            )
            if not unit_contract["valid"]:
                raise ValueError(
                    f"telemetry_mapping_unit_invalid:{unit_contract['reason_code']}"
                )
            if (
                conversion_id != unit_contract["conversion_id"]
                or conversion_version != unit_contract["conversion_version"]
            ):
                raise ValueError("telemetry_mapping_conversion_contract_mismatch")
            cursor.execute(
                """
                INSERT INTO telemetry.analysis_authority_snapshots (
                    id, tenant_scope_id, workspace_id, resource_scope_id,
                    facility_id, system_id, asset_id, authority_digest,
                    identity_digest, authority_snapshot, attested_by, attested_at
                ) VALUES (
                    %s::UUID, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s::JSONB, %s, %s
                )
                ON CONFLICT (
                    resource_scope_id, system_id,
                    (COALESCE(asset_id, '')), authority_digest
                ) DO UPDATE SET
                    identity_digest = EXCLUDED.identity_digest,
                    authority_snapshot = EXCLUDED.authority_snapshot,
                    attested_by = EXCLUDED.attested_by,
                    attested_at = EXCLUDED.attested_at
                WHERE telemetry.analysis_authority_snapshots.identity_digest
                          = EXCLUDED.identity_digest
                """,
                (
                    authority_snapshot_id,
                    scope.tenant_scope_id,
                    scope.workspace_id,
                    scope.resource_scope_id,
                    scope.facility_id,
                    system_id,
                    asset_id,
                    authority_digest,
                    authority_identity.identity_digest,
                    authority_snapshot_json,
                    actor_id,
                    mapped_at,
                ),
            )
            cursor.execute(
                """
                SELECT m.id, m.revision
                FROM telemetry.signal_mappings m
                WHERE m.resource_scope_id = %s AND m.tenant_scope_id = %s
                  AND m.workspace_id = %s AND m.facility_id = %s
                  AND m.connection_id = %s::UUID
                  AND m.external_signal_id = %s::UUID AND m.enabled = TRUE
                FOR UPDATE
                """,
                (*_scope_parameters(scope), connection_id, signal_id),
            )
            current = cursor.fetchone()
            current_id: str | None = None
            current_revision = 0
            if current is not None:
                current_id = str(current[0] if not isinstance(current, Mapping) else current["id"])
                current_revision = int(
                    current[1] if not isinstance(current, Mapping) else current["revision"]
                )
            if expected_revision is None and current is not None:
                raise TelemetryMappingConflict("telemetry_mapping_already_enabled")
            if expected_revision is not None and current_revision != int(expected_revision):
                raise TelemetryMappingConflict("telemetry_mapping_revision_conflict")

            cursor.execute(
                """
                SELECT 1 FROM telemetry.signal_mappings m
                WHERE m.resource_scope_id = %s AND m.tenant_scope_id = %s
                  AND m.workspace_id = %s AND m.facility_id = %s
                  AND m.connection_id = %s::UUID AND m.system_id = %s
                  AND COALESCE(m.asset_id, '') = COALESCE(%s, '')
                  AND m.canonical_concept_id = %s::UUID
                  AND m.external_signal_id <> %s::UUID AND m.enabled = TRUE
                FOR UPDATE
                """,
                (
                    *_scope_parameters(scope),
                    connection_id,
                    system_id,
                    asset_id,
                    canonical_concept_id,
                    signal_id,
                ),
            )
            if cursor.fetchone() is not None:
                raise TelemetryMappingConflict(
                    "telemetry_mapping_canonical_hierarchy_duplicate"
                )
            if current_id is not None:
                cursor.execute(
                    """
                    UPDATE telemetry.signal_mappings m
                    SET enabled = FALSE, updated_at = NOW()
                    WHERE m.resource_scope_id = %s AND m.tenant_scope_id = %s
                      AND m.workspace_id = %s AND m.facility_id = %s
                      AND m.id = %s::UUID AND m.revision = %s AND m.enabled = TRUE
                    """,
                    (*_scope_parameters(scope), current_id, current_revision),
                )
                if cursor.rowcount != 1:
                    raise TelemetryMappingConflict(
                        "telemetry_mapping_revision_conflict"
                    )
            revision = current_revision + 1
            try:
                cursor.execute(
                    """
                    INSERT INTO telemetry.signal_mappings (
                        id, tenant_scope_id, workspace_id, resource_scope_id,
                        facility_id, connection_id, external_signal_id, system_id,
                        asset_id, canonical_concept_id, canonical_signal_name,
                        source_unit, canonical_unit, conversion_id,
                        conversion_version, expected_cadence_seconds,
                        source_timezone, enabled, provenance, provenance_reason,
                        mapped_by, mapped_at, authority_digest, revision
                    ) VALUES (
                        %s::UUID, %s, %s, %s, %s, %s::UUID, %s::UUID, %s, %s,
                        %s::UUID, %s, %s, %s, %s, %s, %s, %s, TRUE, %s, %s,
                        %s, %s, %s, %s
                    )
                    RETURNING id, connection_id, external_signal_id AS signal_id,
                        facility_id, system_id, asset_id,
                        canonical_concept_id AS canonical_signal_id,
                        canonical_signal_name, source_unit, canonical_unit,
                        conversion_id, conversion_version, source_timezone,
                        expected_cadence_seconds, mapped_by AS actor_id,
                        mapped_at, revision, provenance_reason AS reason,
                        enabled, provenance
                    """,
                    (
                        mapping_id,
                        scope.tenant_scope_id,
                        scope.workspace_id,
                        scope.resource_scope_id,
                        scope.facility_id,
                        connection_id,
                        signal_id,
                        system_id,
                        asset_id,
                        canonical_concept_id,
                        canonical_signal_name,
                        source_unit,
                        canonical_unit,
                        conversion_id,
                        conversion_version,
                        expected_cadence_seconds,
                        source_timezone,
                        provenance,
                        provenance_reason,
                        actor_id,
                        mapped_at,
                        authority_digest,
                        revision,
                    ),
                )
            except Exception as error:
                if getattr(error, "sqlstate", None) == "23505" or getattr(
                    error, "pgcode", None
                ) == "23505":
                    raise TelemetryMappingConflict(
                        "telemetry_mapping_concurrent_conflict"
                    ) from None
                raise
            result = _row_dict(cursor, cursor.fetchone())
            cursor.execute(
                """
                UPDATE telemetry.external_signals s
                SET enabled = TRUE, mapping_status = 'mapped',
                    quality_state = CASE
                        WHEN quality_state = 'mapping_required' THEN NULL
                        ELSE quality_state END,
                    updated_at = NOW()
                WHERE s.resource_scope_id = %s AND s.tenant_scope_id = %s
                  AND s.workspace_id = %s AND s.facility_id = %s
                  AND s.connection_id = %s::UUID AND s.id = %s::UUID
                """,
                (*_scope_parameters(scope), connection_id, signal_id),
            )
            self._insert_audit_event(
                cursor,
                scope,
                event_id=event_id,
                connection_id=connection_id,
                actor_id=actor_id,
                action="signal_mapping_changed",
                safe_detail={
                    "signal_id": signal_id,
                    "mapping_id": mapping_id,
                    "revision": revision,
                    "provenance": provenance,
                },
            )
            if result is None:
                raise TelemetryRepositoryError("telemetry_mapping_write_failed")
            return result

    def disable_signal_mapping(
        self,
        scope: TelemetryRepositoryScope,
        *,
        connection_id: str,
        signal_id: str,
        expected_revision: int,
        actor_id: str,
        event_id: str,
        reason: str | None = None,
    ) -> dict[str, Any]:
        connection_id = _require_uuid(connection_id, "telemetry_connection_id_invalid")
        signal_id = _require_uuid(signal_id, "telemetry_signal_id_invalid")
        event_id = _require_uuid(event_id, "telemetry_audit_event_id_invalid")
        actor_id = _require_identifier(actor_id, "telemetry_mapping_actor_required")
        if int(expected_revision) < 1:
            raise ValueError("telemetry_mapping_revision_invalid")
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE telemetry.signal_mappings m
                SET enabled = FALSE, provenance_reason = COALESCE(%s, provenance_reason),
                    updated_at = NOW()
                FROM telemetry.data_connections c
                WHERE {self._scope_predicate('c')} AND c.id = %s::UUID
                  AND m.resource_scope_id = c.resource_scope_id
                  AND m.tenant_scope_id = c.tenant_scope_id
                  AND m.workspace_id = c.workspace_id
                  AND m.facility_id = c.facility_id
                  AND m.connection_id = c.id
                  AND m.external_signal_id = %s::UUID
                  AND m.revision = %s AND m.enabled = TRUE
                RETURNING m.id, m.revision
                """,
                (
                    reason,
                    *_scope_parameters(scope),
                    connection_id,
                    signal_id,
                    int(expected_revision),
                ),
            )
            row = cursor.fetchone()
            if row is None:
                raise TelemetryMappingConflict("telemetry_mapping_revision_conflict")
            cursor.execute(
                """
                UPDATE telemetry.external_signals s
                SET enabled = FALSE, mapping_status = 'disabled',
                    quality_state = 'mapping_required', updated_at = NOW()
                WHERE s.resource_scope_id = %s AND s.tenant_scope_id = %s
                  AND s.workspace_id = %s AND s.facility_id = %s
                  AND s.connection_id = %s::UUID AND s.id = %s::UUID
                """,
                (*_scope_parameters(scope), connection_id, signal_id),
            )
            self._insert_audit_event(
                cursor,
                scope,
                event_id=event_id,
                connection_id=connection_id,
                actor_id=actor_id,
                action="signal_mapping_changed",
                safe_detail={
                    "signal_id": signal_id,
                    "mapping_id": str(row[0] if not isinstance(row, Mapping) else row["id"]),
                    "revision": int(expected_revision),
                    "enabled": False,
                    "reason_recorded": reason is not None,
                },
            )
            return {
                "mapping_id": str(row[0] if not isinstance(row, Mapping) else row["id"]),
                "signal_id": signal_id,
                "revision": int(expected_revision),
                "enabled": False,
            }

    def persist_ingestion_page(
        self,
        scope: TelemetryRepositoryScope,
        *,
        connection_id: str,
        run_id: str,
        lease_token: str,
        checkpoint_mode: CheckpointMode | str,
        expected_checkpoint_revision: int,
        cursor_payload: Mapping[str, Any],
        high_water_at: datetime | None,
        observations: Sequence[Mapping[str, Any]],
        rejections: Sequence[Mapping[str, Any]],
        received_count: int | None = None,
        checkpoint_before_digest: str | None = None,
        checkpoint_after_digest: str | None = None,
    ) -> dict[str, int]:
        """Persist a normalized page and checkpoint CAS in one transaction."""
        connection_id = _require_uuid(connection_id, "telemetry_connection_id_invalid")
        run_id = _require_uuid(run_id, "telemetry_ingestion_run_id_invalid")
        lease_token = _require_uuid(lease_token, "telemetry_lease_token_invalid")
        mode = _checkpoint_mode(checkpoint_mode)
        if int(expected_checkpoint_revision) < 0:
            raise ValueError("telemetry_checkpoint_revision_invalid")
        if high_water_at is not None and (
            high_water_at.tzinfo is None or high_water_at.utcoffset() is None
        ):
            raise ValueError("telemetry_checkpoint_high_water_invalid")
        if len(observations) > 5_000 or len(rejections) > 5_000:
            raise ValueError("telemetry_ingestion_page_too_large")
        for digest in (checkpoint_before_digest, checkpoint_after_digest):
            if digest is not None and not _SHA256_DIGEST.fullmatch(str(digest)):
                raise ValueError("telemetry_checkpoint_digest_invalid")

        prepared_observations: list[dict[str, Any]] = []
        required_observation_fields = (
            "id", "system_id", "external_signal_id", "mapping_id",
            "mapping_revision", "canonical_concept_id", "canonical_signal_name",
            "external_tag_id", "source_timestamp_raw", "source_timezone",
            "timestamp_normalization_version", "observed_at_utc", "original_value",
            "normalized_value", "quality_state", "ingestion_disposition",
            "analysis_eligible", "source_record_digest",
        )
        for raw in observations:
            item = dict(raw)
            if any(item.get(field) is None for field in required_observation_fields):
                raise ValueError("telemetry_observation_contract_invalid")
            for field in ("id", "external_signal_id", "mapping_id", "canonical_concept_id"):
                item[field] = _require_uuid(str(item[field]), "telemetry_observation_identifier_invalid")
            observed_at = item["observed_at_utc"]
            if not isinstance(observed_at, datetime) or observed_at.tzinfo is None or observed_at.utcoffset() is None:
                raise ValueError("telemetry_observation_timestamp_invalid")
            item["observed_at_utc"] = observed_at.astimezone(UTC)
            item["source_metadata"] = sanitize_telemetry_public_value(item.get("source_metadata") or {})
            if not isinstance(item["source_metadata"], Mapping):
                raise ValueError("telemetry_observation_metadata_invalid")
            item["reason_codes"] = list(item.get("reason_codes") or [])
            prepared_observations.append(item)

        prepared_rejections: list[dict[str, Any]] = []
        for raw in rejections:
            item = dict(raw)
            item["id"] = _require_uuid(
                str(item.get("id") or uuid.uuid4()), "telemetry_rejection_id_invalid"
            )
            item["source_record_digest"] = _require_identifier(
                str(item.get("source_record_digest") or ""),
                "telemetry_rejection_digest_required",
            )
            item["reason_code"] = _require_public_identifier(
                str(item.get("reason_code") or ""), "telemetry_rejection_reason_invalid"
            )
            disposition = str(item.get("disposition") or "rejected")
            if disposition not in {"duplicate", "quarantined", "rejected"}:
                raise ValueError("telemetry_rejection_disposition_invalid")
            item["disposition"] = disposition
            if disposition == "duplicate":
                # The foundation table's quality CHECK predates explicit
                # dispositions; duplicate is represented by disposition while
                # retaining a schema-valid non-canonical quality classification.
                item["quality_state"] = "format_invalid"
            item["safe_context"] = sanitize_telemetry_public_value(item.get("safe_context") or {})
            prepared_rejections.append(item)

        observations_json = _safe_json_records(
            prepared_observations, code="telemetry_observation_contract_invalid"
        )
        cursor_json = _safe_json(cursor_payload, code="telemetry_checkpoint_cursor_invalid")
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT c.id
                FROM telemetry.data_connections c
                JOIN telemetry.ingestion_runs r
                  ON r.resource_scope_id = c.resource_scope_id
                 AND r.tenant_scope_id = c.tenant_scope_id
                 AND r.workspace_id = c.workspace_id
                 AND r.facility_id = c.facility_id
                 AND r.connection_id = c.id
                WHERE {self._scope_predicate('c')} AND c.id = %s::UUID
                  AND c.lease_token = %s::UUID AND c.lease_expires_at > NOW()
                  AND r.id = %s::UUID AND r.status = 'running'
                  AND r.lease_token = c.lease_token
                FOR UPDATE OF c, r
                """,
                (*_scope_parameters(scope), connection_id, lease_token, run_id),
            )
            if cursor.fetchone() is None:
                raise TelemetryLeaseLost("telemetry_connection_lease_lost")

            inserted: list[dict[str, Any]] = []
            if prepared_observations:
                cursor.execute(
                    """
                    WITH input AS (
                        SELECT * FROM jsonb_to_recordset(%s::JSONB) AS x(
                            mapping_id UUID, external_signal_id UUID,
                            mapping_revision INTEGER, system_id TEXT,
                            canonical_concept_id UUID,
                            canonical_signal_name TEXT,
                            mapping_actor_id TEXT,
                            mapping_mapped_at TIMESTAMPTZ,
                            mapping_authority_digest TEXT,
                            mapping_provenance TEXT,
                            original_unit TEXT, canonical_unit TEXT,
                            conversion_id TEXT, conversion_version TEXT,
                            source_timezone TEXT
                        )
                    )
                    SELECT COUNT(*) = COUNT(m.id)
                    FROM input x
                    LEFT JOIN telemetry.signal_mappings m
                      ON m.resource_scope_id = %s AND m.tenant_scope_id = %s
                     AND m.workspace_id = %s AND m.facility_id = %s
                     AND m.connection_id = %s::UUID AND m.id = x.mapping_id
                     AND m.external_signal_id = x.external_signal_id
                     AND m.revision = x.mapping_revision AND m.enabled = TRUE
                     AND m.system_id = x.system_id
                     AND m.canonical_concept_id = x.canonical_concept_id
                     AND m.canonical_signal_name = x.canonical_signal_name
                     AND m.mapped_by = x.mapping_actor_id
                     AND m.mapped_at = x.mapping_mapped_at
                     AND m.authority_digest = x.mapping_authority_digest
                     AND m.provenance = x.mapping_provenance
                     AND (x.original_unit IS NULL OR
                          LOWER(BTRIM(x.original_unit)) = LOWER(BTRIM(m.source_unit)))
                     AND m.canonical_unit = x.canonical_unit
                     AND m.conversion_id = x.conversion_id
                     AND m.conversion_version = x.conversion_version
                     AND m.source_timezone = x.source_timezone
                    """,
                    (observations_json, *_scope_parameters(scope), connection_id),
                )
                validation_row = cursor.fetchone()
                mapping_valid = (
                    validation_row.get("?column?")
                    if isinstance(validation_row, Mapping)
                    else validation_row[0] if validation_row else False
                )
                if not bool(mapping_valid):
                    raise TelemetryMappingConflict(
                        "telemetry_ingestion_mapping_snapshot_conflict"
                    )
                cursor.execute(
                    """
                    WITH input AS (
                        SELECT * FROM jsonb_to_recordset(%s::JSONB) AS x(
                            id UUID, system_id TEXT, asset_id TEXT,
                            external_signal_id UUID, mapping_id UUID,
                            mapping_revision INTEGER, canonical_concept_id UUID,
                            canonical_signal_name TEXT, external_tag_id TEXT,
                            provider_event_id TEXT, source_timestamp_raw TEXT,
                            source_timezone TEXT, source_offset TEXT,
                            timestamp_normalization_version TEXT,
                            observed_at_utc TIMESTAMPTZ, original_value JSONB,
                            original_unit TEXT, normalized_value DOUBLE PRECISION,
                            canonical_unit TEXT, conversion_id TEXT,
                            conversion_version TEXT, quality_state TEXT,
                            ingestion_disposition TEXT, analysis_eligible BOOLEAN,
                            reason_codes TEXT[], source_record_digest TEXT,
                            source_metadata JSONB,
                            mapping_actor_id TEXT,
                            mapping_mapped_at TIMESTAMPTZ,
                            mapping_authority_digest TEXT,
                            mapping_provenance TEXT
                        )
                    )
                    INSERT INTO telemetry.normalized_observations (
                        id, tenant_scope_id, workspace_id, resource_scope_id,
                        facility_id, system_id, asset_id, connection_id,
                        ingestion_run_id, external_signal_id, mapping_id,
                        mapping_revision, canonical_concept_id,
                        canonical_signal_name, external_tag_id, provider_event_id,
                        source_timestamp_raw, source_timezone, source_offset,
                        timestamp_normalization_version, observed_at_utc,
                        original_value, original_unit, normalized_value,
                        canonical_unit, conversion_id, conversion_version,
                        quality_state, ingestion_disposition, analysis_eligible,
                        reason_codes, source_record_digest, source_metadata,
                        mapping_provenance, mapping_actor_id, mapping_mapped_at,
                        mapping_authority_digest
                    )
                    SELECT x.id, m.tenant_scope_id, m.workspace_id,
                        m.resource_scope_id, m.facility_id, x.system_id,
                        x.asset_id, m.connection_id, %s::UUID,
                        x.external_signal_id, x.mapping_id, x.mapping_revision,
                        x.canonical_concept_id, x.canonical_signal_name,
                        x.external_tag_id, x.provider_event_id,
                        x.source_timestamp_raw, x.source_timezone, x.source_offset,
                        x.timestamp_normalization_version, x.observed_at_utc,
                        x.original_value, x.original_unit, x.normalized_value,
                        x.canonical_unit, x.conversion_id, x.conversion_version,
                        x.quality_state, x.ingestion_disposition,
                        x.analysis_eligible, COALESCE(x.reason_codes, '{}'),
                        x.source_record_digest, COALESCE(x.source_metadata, '{}'),
                        m.provenance, m.mapped_by, m.mapped_at, m.authority_digest
                    FROM input x
                    JOIN telemetry.signal_mappings m
                      ON m.resource_scope_id = %s AND m.tenant_scope_id = %s
                     AND m.workspace_id = %s AND m.facility_id = %s
                     AND m.connection_id = %s::UUID AND m.id = x.mapping_id
                     AND m.external_signal_id = x.external_signal_id
                     AND m.revision = x.mapping_revision AND m.enabled = TRUE
                     AND m.system_id = x.system_id
                     AND m.canonical_concept_id = x.canonical_concept_id
                     AND m.canonical_signal_name = x.canonical_signal_name
                     AND m.mapped_by = x.mapping_actor_id
                     AND m.mapped_at = x.mapping_mapped_at
                     AND m.authority_digest = x.mapping_authority_digest
                     AND m.provenance = x.mapping_provenance
                     AND (x.original_unit IS NULL OR
                          LOWER(BTRIM(x.original_unit)) = LOWER(BTRIM(m.source_unit)))
                     AND m.canonical_unit = x.canonical_unit
                     AND m.conversion_id = x.conversion_id
                     AND m.conversion_version = x.conversion_version
                     AND m.source_timezone = x.source_timezone
                    ON CONFLICT DO NOTHING
                    RETURNING source_record_digest, ingestion_disposition,
                              external_signal_id, observed_at_utc, quality_state
                    """,
                    (observations_json, run_id, *_scope_parameters(scope), connection_id),
                )
                inserted = [_row_dict(cursor, row) or {} for row in cursor.fetchall()]

            inserted_digests = {str(row.get("source_record_digest")) for row in inserted}
            duplicate_count = 0
            for item in prepared_observations:
                digest = str(item["source_record_digest"])
                if digest not in inserted_digests:
                    duplicate_count += 1
                    prepared_rejections.append(
                        {
                            "id": str(uuid.uuid4()),
                            "external_signal_id": item.get("external_signal_id"),
                            "external_tag_id": item.get("external_tag_id"),
                            "source_timestamp_raw": item.get("source_timestamp_raw"),
                            "source_record_digest": digest,
                            "quality_state": "format_invalid",
                            "reason_code": "duplicate_observation",
                            "disposition": "duplicate",
                            "safe_context": {},
                        }
                    )

            if prepared_rejections:
                rejections_json = _safe_json_records(
                    prepared_rejections, code="telemetry_rejection_contract_invalid"
                )
                cursor.execute(
                    """
                    WITH input AS (
                        SELECT * FROM jsonb_to_recordset(%s::JSONB) AS x(
                            id UUID, external_signal_id UUID, external_tag_id TEXT,
                            provider_event_id TEXT, mapping_id UUID,
                            source_timestamp_raw TEXT, source_record_digest TEXT,
                            original_value JSONB, original_unit TEXT,
                            reported_quality TEXT,
                            quality_state TEXT, reason_code TEXT,
                            disposition TEXT, safe_context JSONB
                        )
                    )
                    INSERT INTO telemetry.observation_rejections (
                        id, tenant_scope_id, workspace_id, resource_scope_id,
                        facility_id, connection_id, ingestion_run_id,
                        external_signal_id, external_tag_id, source_timestamp_raw,
                        provider_event_id, mapping_id, original_value,
                        original_unit, reported_quality,
                        source_record_digest, quality_state, reason_code,
                        disposition, safe_context, occurrence_count,
                        first_seen_at, last_seen_at
                    )
                    SELECT x.id, %s, %s, %s, %s, %s::UUID, %s::UUID,
                        x.external_signal_id, x.external_tag_id,
                        x.source_timestamp_raw, x.provider_event_id, x.mapping_id,
                        x.original_value, x.original_unit, x.reported_quality,
                        x.source_record_digest,
                        x.quality_state, x.reason_code, x.disposition,
                        COALESCE(x.safe_context, '{}'), 1, NOW(), NOW()
                    FROM input x
                    ON CONFLICT (resource_scope_id, connection_id,
                                 source_record_digest, reason_code)
                    DO UPDATE SET
                        ingestion_run_id = EXCLUDED.ingestion_run_id,
                        disposition = EXCLUDED.disposition,
                        provider_event_id = EXCLUDED.provider_event_id,
                        mapping_id = EXCLUDED.mapping_id,
                        original_value = EXCLUDED.original_value,
                        original_unit = EXCLUDED.original_unit,
                        reported_quality = EXCLUDED.reported_quality,
                        safe_context = EXCLUDED.safe_context,
                        occurrence_count = telemetry.observation_rejections.occurrence_count + 1,
                        last_seen_at = NOW()
                    """,
                    (
                        rejections_json,
                        scope.tenant_scope_id,
                        scope.workspace_id,
                        scope.resource_scope_id,
                        scope.facility_id,
                        connection_id,
                        run_id,
                    ),
                )

            if inserted:
                cursor.execute(
                    """
                    UPDATE telemetry.external_signals s
                    SET last_observed_at = facts.last_observed_at,
                        quality_state = facts.quality_state, updated_at = NOW()
                    FROM (
                        SELECT external_signal_id, MAX(observed_at_utc) AS last_observed_at,
                               (ARRAY_AGG(quality_state ORDER BY observed_at_utc DESC))[1]
                                   AS quality_state
                        FROM telemetry.normalized_observations
                        WHERE resource_scope_id = %s AND ingestion_run_id = %s::UUID
                        GROUP BY external_signal_id
                    ) facts
                    WHERE s.resource_scope_id = %s AND s.tenant_scope_id = %s
                      AND s.workspace_id = %s AND s.facility_id = %s
                      AND s.connection_id = %s::UUID
                      AND s.id = facts.external_signal_id
                    """,
                    (
                        scope.resource_scope_id,
                        run_id,
                        *_scope_parameters(scope),
                        connection_id,
                    ),
                )

            if int(expected_checkpoint_revision) == 0:
                cursor.execute(
                    """
                    INSERT INTO telemetry.connection_checkpoints (
                        tenant_scope_id, workspace_id, resource_scope_id,
                        facility_id, connection_id, mode, cursor_payload,
                        high_water_at, revision, updated_run_id
                    ) VALUES (%s, %s, %s, %s, %s::UUID, %s, %s::JSONB,
                              %s, 1, %s::UUID)
                    ON CONFLICT (resource_scope_id, connection_id, mode) DO NOTHING
                    RETURNING revision
                    """,
                    (
                        scope.tenant_scope_id, scope.workspace_id,
                        scope.resource_scope_id, scope.facility_id,
                        connection_id, mode, cursor_json, high_water_at, run_id,
                    ),
                )
            else:
                cursor.execute(
                    """
                    UPDATE telemetry.connection_checkpoints cp
                    SET cursor_payload = %s::JSONB, high_water_at = %s,
                        revision = cp.revision + 1, updated_run_id = %s::UUID,
                        updated_at = NOW()
                    WHERE cp.resource_scope_id = %s AND cp.tenant_scope_id = %s
                      AND cp.workspace_id = %s AND cp.facility_id = %s
                      AND cp.connection_id = %s::UUID AND cp.mode = %s
                      AND cp.revision = %s
                    RETURNING cp.revision
                    """,
                    (
                        cursor_json, high_water_at, run_id,
                        *_scope_parameters(scope), connection_id, mode,
                        int(expected_checkpoint_revision),
                    ),
                )
            checkpoint_row = cursor.fetchone()
            if not checkpoint_row:
                raise TelemetryCheckpointConflict("telemetry_checkpoint_revision_conflict")
            revision = int(
                checkpoint_row.get("revision")
                if isinstance(checkpoint_row, Mapping)
                else checkpoint_row[0]
            )
            accepted = len(inserted)
            rejected = len(prepared_rejections) - duplicate_count
            out_of_order = sum(
                str(row.get("ingestion_disposition")) == "out_of_order_accepted"
                for row in inserted
            )
            received = len(observations) + len(rejections) if received_count is None else int(received_count)
            if received < 0:
                raise ValueError("telemetry_ingestion_received_count_invalid")
            cursor.execute(
                """
                UPDATE telemetry.ingestion_runs r
                SET pages_processed = r.pages_processed + 1,
                    observations_received = r.observations_received + %s,
                    observations_accepted = r.observations_accepted + %s,
                    observations_rejected = r.observations_rejected + %s,
                    observations_duplicate = r.observations_duplicate + %s,
                    observations_out_of_order = r.observations_out_of_order + %s,
                    checkpoint_before_digest = COALESCE(
                        r.checkpoint_before_digest, %s
                    ),
                    checkpoint_after_digest = COALESCE(
                        %s, r.checkpoint_after_digest
                    ),
                    updated_at = NOW()
                WHERE r.resource_scope_id = %s AND r.tenant_scope_id = %s
                  AND r.workspace_id = %s AND r.facility_id = %s
                  AND r.connection_id = %s::UUID AND r.id = %s::UUID
                  AND r.status = 'running' AND r.lease_token = %s::UUID
                """,
                (
                    received, accepted, rejected, duplicate_count, out_of_order,
                    checkpoint_before_digest, checkpoint_after_digest,
                    *_scope_parameters(scope), connection_id, run_id, lease_token,
                ),
            )
            return {
                "checkpoint_revision": revision,
                "accepted": accepted,
                "rejected": rejected,
                "duplicate": duplicate_count,
                "out_of_order": out_of_order,
            }

    def continue_ingestion_work(
        self,
        scope: TelemetryRepositoryScope,
        *,
        connection_id: str,
        run_id: str,
        lease_token: str,
        continued_at: datetime,
        next_attempt_at: datetime,
    ) -> dict[str, Any]:
        """Requeue the same non-terminal run after a bounded provider page."""
        connection_id = _require_uuid(connection_id, "telemetry_connection_id_invalid")
        run_id = _require_uuid(run_id, "telemetry_ingestion_run_id_invalid")
        lease_token = _require_uuid(lease_token, "telemetry_lease_token_invalid")
        for value in (continued_at, next_attempt_at):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("telemetry_ingestion_schedule_timestamp_invalid")
        if next_attempt_at < continued_at:
            raise ValueError("telemetry_ingestion_schedule_invalid")
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE telemetry.ingestion_runs r
                SET status = 'pending', lease_token = NULL, worker_id = NULL,
                    updated_at = %s
                WHERE r.resource_scope_id = %s AND r.tenant_scope_id = %s
                  AND r.workspace_id = %s AND r.facility_id = %s
                  AND r.connection_id = %s::UUID AND r.id = %s::UUID
                  AND r.status = 'running' AND r.lease_token = %s::UUID
                RETURNING r.mode, r.range_start, r.range_end
                """,
                (
                    continued_at, *_scope_parameters(scope), connection_id,
                    run_id, lease_token,
                ),
            )
            row = cursor.fetchone()
            if row is None:
                raise TelemetryLeaseLost("telemetry_ingestion_run_lease_lost")
            cursor.execute(
                f"""
                UPDATE telemetry.data_connections c
                SET lease_owner = NULL, lease_token = NULL,
                    lease_expires_at = NULL, next_attempt_at = %s,
                    updated_at = %s
                WHERE {self._scope_predicate('c')} AND c.id = %s::UUID
                  AND c.lease_token = %s::UUID
                RETURNING c.id, c.next_attempt_at
                """,
                (
                    next_attempt_at, continued_at, *_scope_parameters(scope),
                    connection_id, lease_token,
                ),
            )
            result = _row_dict(cursor, cursor.fetchone())
            if result is None:
                raise TelemetryLeaseLost("telemetry_connection_lease_lost")
            run_values = dict(row) if isinstance(row, Mapping) else {
                "mode": row[0], "range_start": row[1], "range_end": row[2]
            }
            result.update(
                {
                    "run_id": run_id,
                    "run_mode": str(run_values["mode"]),
                    "range_start": run_values.get("range_start"),
                    "range_end": run_values.get("range_end"),
                    "status": "pending",
                }
            )
            return result

    def complete_ingestion_work(
        self,
        scope: TelemetryRepositoryScope,
        *,
        connection_id: str,
        run_id: str,
        lease_token: str,
        completed_at: datetime,
        next_attempt_at: datetime | None,
        partial: bool = False,
    ) -> dict[str, Any]:
        """Complete a run, schedule cadence, and release its lease atomically."""
        connection_id = _require_uuid(connection_id, "telemetry_connection_id_invalid")
        run_id = _require_uuid(run_id, "telemetry_ingestion_run_id_invalid")
        lease_token = _require_uuid(lease_token, "telemetry_lease_token_invalid")
        for value in (completed_at, next_attempt_at):
            if value is not None and (value.tzinfo is None or value.utcoffset() is None):
                raise ValueError("telemetry_ingestion_schedule_timestamp_invalid")
        if next_attempt_at is not None and next_attempt_at < completed_at:
            raise ValueError("telemetry_ingestion_schedule_invalid")
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE telemetry.ingestion_runs r
                SET status = CASE
                        WHEN %s OR r.observations_rejected > 0
                        THEN 'partial' ELSE 'succeeded'
                    END,
                    finished_at = %s, error_code = NULL,
                    error_summary = NULL,
                    latency_ms = LEAST(
                        2147483647,
                        GREATEST(
                            0,
                            FLOOR(EXTRACT(EPOCH FROM (%s - r.started_at)) * 1000)
                        )::BIGINT
                    )::INTEGER,
                    updated_at = %s
                WHERE r.resource_scope_id = %s AND r.tenant_scope_id = %s
                  AND r.workspace_id = %s AND r.facility_id = %s
                  AND r.connection_id = %s::UUID AND r.id = %s::UUID
                  AND r.status = 'running' AND r.lease_token = %s::UUID
                RETURNING r.status, r.mode, r.range_start, r.range_end,
                          COALESCE(r.actor_id, r.worker_id, 'telemetry-worker')
                              AS audit_actor,
                          r.pages_processed, r.observations_received,
                          r.observations_accepted, r.observations_rejected,
                          r.observations_duplicate
                """,
                (
                    bool(partial), completed_at, completed_at, completed_at,
                    *_scope_parameters(scope), connection_id, run_id, lease_token,
                ),
            )
            run_row = cursor.fetchone()
            if run_row is None:
                raise TelemetryLeaseLost("telemetry_ingestion_run_lease_lost")
            if isinstance(run_row, Mapping):
                run_values = dict(run_row)
            else:
                run_values = dict(
                    zip(
                        (
                            "status", "mode", "range_start", "range_end", "audit_actor",
                            "pages_processed", "observations_received",
                            "observations_accepted", "observations_rejected",
                            "observations_duplicate",
                        ),
                        run_row,
                        strict=False,
                    )
                )
            status = str(
                run_values.get("status")
                or (
                    "partial"
                    if partial or int(run_values.get("observations_rejected") or 0) > 0
                    else "succeeded"
                )
            )
            run_mode = str(run_values["mode"])
            cursor.execute(
                f"""
                UPDATE telemetry.data_connections c
                SET lease_owner = NULL, lease_token = NULL,
                    lease_expires_at = NULL, retry_count = 0,
                    next_attempt_at = %s,
                    last_success_at = CASE WHEN %s IS NOT NULL THEN %s
                                           ELSE c.last_success_at END,
                    last_error_code = NULL, last_error_summary = NULL,
                    lifecycle_status = CASE
                        WHEN %s = 'partial' THEN 'degraded'
                        WHEN %s IS NOT NULL AND c.lifecycle_status IN
                             ('validating', 'degraded', 'disconnected', 'error')
                        THEN 'connected' ELSE c.lifecycle_status END,
                    updated_at = %s
                WHERE {self._scope_predicate('c')} AND c.id = %s::UUID
                  AND c.lease_token = %s::UUID
                RETURNING c.id, c.lifecycle_status, c.next_attempt_at
                """,
                (
                    next_attempt_at, next_attempt_at, completed_at,
                    status, next_attempt_at, completed_at,
                    *_scope_parameters(scope), connection_id, lease_token,
                ),
            )
            result = _row_dict(cursor, cursor.fetchone())
            if result is None:
                raise TelemetryLeaseLost("telemetry_connection_lease_lost")
            if run_mode == "backfill" or (
                run_mode == "retry" and run_values.get("range_start") is not None
            ):
                self._insert_audit_event(
                    cursor,
                    scope,
                    event_id=str(uuid.uuid4()),
                    connection_id=connection_id,
                    actor_id=str(run_values["audit_actor"]),
                    action="backfill_completed",
                    safe_detail={
                        "run_id": run_id,
                        "status": status,
                        "pages_processed": int(run_values.get("pages_processed") or 0),
                        "observations_received": int(run_values.get("observations_received") or 0),
                        "observations_accepted": int(run_values.get("observations_accepted") or 0),
                        "observations_rejected": int(run_values.get("observations_rejected") or 0),
                        "observations_duplicate": int(run_values.get("observations_duplicate") or 0),
                    },
                )
            result.update({"run_id": run_id, "run_mode": run_mode, "status": status})
            return result

    def record_ingestion_failure(
        self,
        scope: TelemetryRepositoryScope,
        *,
        connection_id: str,
        run_id: str,
        lease_token: str,
        failed_at: datetime,
        error_code: str,
        error_summary: str | None = None,
        retryable: bool = True,
        retry_after_seconds: int | None = None,
        retry_jitter: float = 0.5,
    ) -> dict[str, Any]:
        """Record a sanitized failure, bounded retry, and lease release."""
        connection_id = _require_uuid(connection_id, "telemetry_connection_id_invalid")
        run_id = _require_uuid(run_id, "telemetry_ingestion_run_id_invalid")
        lease_token = _require_uuid(lease_token, "telemetry_lease_token_invalid")
        if failed_at.tzinfo is None or failed_at.utcoffset() is None:
            raise ValueError("telemetry_ingestion_failure_timestamp_invalid")
        try:
            jitter_unit = min(max(float(retry_jitter), 0.0), 1.0)
        except (TypeError, ValueError) as error:
            raise ValueError("telemetry_ingestion_retry_jitter_invalid") from error
        code, summary = _safe_error_fields(error_code, error_summary)
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT c.retry_count, r.mode, r.range_start, r.range_end,
                       COALESCE(r.actor_id, r.worker_id, 'telemetry-worker')
                           AS audit_actor,
                       r.pages_processed, r.observations_received,
                       r.observations_accepted, r.observations_rejected,
                       r.observations_duplicate
                FROM telemetry.data_connections c
                JOIN telemetry.ingestion_runs r
                  ON r.resource_scope_id = c.resource_scope_id
                 AND r.tenant_scope_id = c.tenant_scope_id
                 AND r.workspace_id = c.workspace_id
                 AND r.facility_id = c.facility_id
                 AND r.connection_id = c.id
                WHERE {self._scope_predicate('c')} AND c.id = %s::UUID
                  AND c.lease_token = %s::UUID AND r.id = %s::UUID
                  AND r.status = 'running' AND r.lease_token = c.lease_token
                FOR UPDATE OF c, r
                """,
                (*_scope_parameters(scope), connection_id, lease_token, run_id),
            )
            row = cursor.fetchone()
            if row is None:
                raise TelemetryLeaseLost("telemetry_ingestion_run_lease_lost")
            prior_retries = int(
                row.get("retry_count") if isinstance(row, Mapping) else row[0]
            )
            if isinstance(row, Mapping):
                failure_values = dict(row)
            else:
                failure_values = dict(
                    zip(
                        (
                            "retry_count", "mode", "range_start", "range_end",
                            "audit_actor", "pages_processed", "observations_received",
                            "observations_accepted", "observations_rejected",
                            "observations_duplicate",
                        ),
                        row,
                        strict=True,
                    )
                )
            retry_count = min(prior_retries + 1, 10)
            exhausted = not retryable or retry_count >= 10
            if not exhausted:
                exponential_cap = min(30 * (2 ** min(prior_retries, 7)), 3_600)
                # Full jitter distributes each retry uniformly across the
                # bounded exponential window. A one-second floor prevents an
                # injected zero from producing a hot retry loop.
                jitter_delay = max(1, math.ceil(exponential_cap * jitter_unit))
                bounded_retry_after = (
                    min(max(int(retry_after_seconds), 1), 86_400)
                    if retry_after_seconds is not None
                    else 0
                )
                delay = min(max(jitter_delay, bounded_retry_after), 86_400)
                next_attempt_at = failed_at + timedelta(seconds=delay)
            else:
                next_attempt_at = None
            run_status = "failed" if exhausted else "pending"
            cursor.execute(
                """
                UPDATE telemetry.ingestion_runs r
                SET status = %s, finished_at = %s,
                    retry_count = %s, error_code = %s, error_summary = %s,
                    latency_ms = CASE WHEN %s = 'failed' THEN LEAST(
                        2147483647,
                        GREATEST(
                            0,
                            FLOOR(EXTRACT(EPOCH FROM (%s - r.started_at)) * 1000)
                        )::BIGINT
                    )::INTEGER ELSE r.latency_ms END,
                    lease_token = NULL, worker_id = NULL, updated_at = %s
                WHERE r.resource_scope_id = %s AND r.tenant_scope_id = %s
                  AND r.workspace_id = %s AND r.facility_id = %s
                  AND r.connection_id = %s::UUID AND r.id = %s::UUID
                  AND r.status = 'running' AND r.lease_token = %s::UUID
                """,
                (
                    run_status, failed_at if exhausted else None,
                    retry_count, code, summary, run_status, failed_at, failed_at,
                    *_scope_parameters(scope), connection_id, run_id, lease_token,
                ),
            )
            cursor.execute(
                f"""
                UPDATE telemetry.data_connections c
                SET lease_owner = NULL, lease_token = NULL,
                    lease_expires_at = NULL, retry_count = %s,
                    next_attempt_at = %s, last_error_code = %s,
                    last_error_summary = %s,
                    lifecycle_status = CASE WHEN %s THEN 'error' ELSE 'degraded' END,
                    updated_at = %s
                WHERE {self._scope_predicate('c')} AND c.id = %s::UUID
                  AND c.lease_token = %s::UUID
                RETURNING c.id, c.retry_count, c.next_attempt_at,
                          c.lifecycle_status
                """,
                (
                    retry_count, next_attempt_at, code, summary, exhausted, failed_at,
                    *_scope_parameters(scope), connection_id, lease_token,
                ),
            )
            result = _row_dict(cursor, cursor.fetchone())
            if result is None:
                raise TelemetryLeaseLost("telemetry_connection_lease_lost")
            failure_mode = str(failure_values.get("mode") or "")
            if exhausted and (failure_mode == "backfill" or (
                failure_mode == "retry" and failure_values.get("range_start") is not None
            )):
                self._insert_audit_event(
                    cursor,
                    scope,
                    event_id=str(uuid.uuid4()),
                    connection_id=connection_id,
                    actor_id=str(failure_values.get("audit_actor") or "telemetry-worker"),
                    action="backfill_failed",
                    safe_detail={
                        "run_id": run_id,
                        "status": "failed",
                        "error_code": code,
                        "pages_processed": int(failure_values.get("pages_processed") or 0),
                        "observations_received": int(failure_values.get("observations_received") or 0),
                        "observations_accepted": int(failure_values.get("observations_accepted") or 0),
                        "observations_rejected": int(failure_values.get("observations_rejected") or 0),
                        "observations_duplicate": int(failure_values.get("observations_duplicate") or 0),
                    },
                )
            result.update({"run_id": run_id, "status": run_status, "error_code": code})
            return result

    def schedule_connection_now(
        self,
        scope: TelemetryRepositoryScope,
        *,
        connection_id: str,
        requested_at: datetime,
    ) -> bool:
        if requested_at.tzinfo is None or requested_at.utcoffset() is None:
            raise ValueError("telemetry_ingestion_schedule_timestamp_invalid")
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE telemetry.data_connections c
                SET next_attempt_at = %s, retry_count = 0, updated_at = NOW()
                WHERE {self._scope_predicate('c')} AND c.id = %s::UUID
                  AND c.enabled = TRUE AND c.archived_at IS NULL
                """,
                (
                    requested_at, *_scope_parameters(scope),
                    _require_uuid(connection_id, "telemetry_connection_id_invalid"),
                ),
            )
            return cursor.rowcount == 1

    def create_backfill_run(
        self,
        scope: TelemetryRepositoryScope,
        *,
        run_id: str,
        connection_id: str,
        range_start: datetime,
        range_end: datetime,
        actor_id: str,
        requested_at: datetime,
    ) -> dict[str, Any]:
        """Create one bounded pending backfill and make it immediately due."""
        run_id = _require_uuid(run_id, "telemetry_ingestion_run_id_invalid")
        connection_id = _require_uuid(connection_id, "telemetry_connection_id_invalid")
        actor_id = _require_identifier(actor_id, "telemetry_backfill_actor_invalid")
        if len(actor_id) > 320:
            raise ValueError("telemetry_backfill_actor_invalid")
        for value in (range_start, range_end, requested_at):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("telemetry_backfill_timestamp_invalid")
        if range_end <= range_start or range_end - range_start > timedelta(days=31):
            raise ValueError("telemetry_backfill_range_invalid")
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT c.id FROM telemetry.data_connections c
                WHERE {self._scope_predicate('c')} AND c.id = %s::UUID
                  AND c.enabled = TRUE AND c.archived_at IS NULL
                FOR UPDATE
                """,
                (*_scope_parameters(scope), connection_id),
            )
            if cursor.fetchone() is None:
                raise TelemetryRepositoryError("telemetry_connection_not_found")
            try:
                cursor.execute(
                    """
                    INSERT INTO telemetry.ingestion_runs (
                        id, tenant_scope_id, workspace_id, resource_scope_id,
                        facility_id, connection_id, mode, status, range_start,
                        range_end, started_at, actor_id
                    ) VALUES (%s::UUID, %s, %s, %s, %s, %s::UUID,
                              'backfill', 'pending', %s, %s, %s, %s)
                    """,
                    (
                        run_id, scope.tenant_scope_id, scope.workspace_id,
                        scope.resource_scope_id, scope.facility_id, connection_id,
                        range_start, range_end, requested_at, actor_id,
                    ),
                )
            except Exception as error:
                if getattr(error, "sqlstate", None) == "23505":
                    raise TelemetryRepositoryError("telemetry_backfill_already_active") from None
                raise
            # The schema has one checkpoint namespace per connection/mode.
            # Reset it only after the guarded run insert succeeds so a rejected
            # overlapping request cannot even issue the destructive statement.
            cursor.execute(
                """
                DELETE FROM telemetry.connection_checkpoints cp
                WHERE cp.resource_scope_id = %s AND cp.tenant_scope_id = %s
                  AND cp.workspace_id = %s AND cp.facility_id = %s
                  AND cp.connection_id = %s::UUID AND cp.mode = 'backfill'
                """,
                (*_scope_parameters(scope), connection_id),
            )
            cursor.execute(
                f"""
                UPDATE telemetry.data_connections c
                SET next_attempt_at = %s, retry_count = 0, updated_at = NOW()
                WHERE {self._scope_predicate('c')} AND c.id = %s::UUID
                """,
                (requested_at, *_scope_parameters(scope), connection_id),
            )
            self._insert_audit_event(
                cursor,
                scope,
                event_id=str(uuid.uuid4()),
                connection_id=connection_id,
                actor_id=actor_id,
                action="backfill_started",
                safe_detail={
                    "run_id": run_id,
                    "range_start": range_start.astimezone(UTC).isoformat(),
                    "range_end": range_end.astimezone(UTC).isoformat(),
                },
            )
            return {
                "id": run_id, "connection_id": connection_id, "mode": "backfill",
                "status": "pending", "range_start": range_start,
                "range_end": range_end, "started_at": requested_at,
                "actor_id": actor_id,
            }

    def retry_ingestion_run(
        self,
        scope: TelemetryRepositoryScope,
        *,
        run_id: str,
        actor_id: str,
        requested_at: datetime,
        new_run_id: str | None = None,
    ) -> dict[str, Any]:
        """Atomically create a due retry from an eligible terminal run."""
        source_id = _require_uuid(run_id, "telemetry_ingestion_run_id_invalid")
        retry_id = _require_uuid(
            new_run_id or str(uuid.uuid4()), "telemetry_ingestion_run_id_invalid"
        )
        actor = _require_identifier(actor_id, "telemetry_ingestion_retry_actor_invalid")
        if len(actor) > 320:
            raise ValueError("telemetry_ingestion_retry_actor_invalid")
        if requested_at.tzinfo is None or requested_at.utcoffset() is None:
            raise ValueError("telemetry_ingestion_retry_timestamp_invalid")
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT r.connection_id, r.mode, r.status, r.range_start,
                       r.range_end
                FROM telemetry.ingestion_runs r
                JOIN telemetry.data_connections c
                  ON c.resource_scope_id = r.resource_scope_id
                 AND c.tenant_scope_id = r.tenant_scope_id
                 AND c.workspace_id = r.workspace_id
                 AND c.facility_id = r.facility_id
                 AND c.id = r.connection_id
                WHERE r.resource_scope_id = %s AND r.tenant_scope_id = %s
                  AND r.workspace_id = %s AND r.facility_id = %s
                  AND r.id = %s::UUID
                  AND r.mode IN ('incremental', 'backfill', 'retry')
                  AND r.status IN ('failed', 'partial')
                  AND c.enabled = TRUE AND c.archived_at IS NULL
                FOR UPDATE OF c, r
                """,
                (*_scope_parameters(scope), source_id),
            )
            source = _row_dict(cursor, cursor.fetchone())
            if source is None:
                raise TelemetryRepositoryError("telemetry_ingestion_run_not_retryable")
            connection_id = _require_uuid(
                str(source["connection_id"]), "telemetry_connection_id_invalid"
            )
            try:
                cursor.execute(
                    """
                    INSERT INTO telemetry.ingestion_runs (
                        id, tenant_scope_id, workspace_id, resource_scope_id,
                        facility_id, connection_id, mode, status, range_start,
                        range_end, started_at, actor_id, source_run_id
                    ) VALUES (%s::UUID, %s, %s, %s, %s, %s::UUID, 'retry',
                              'pending', %s, %s, %s, %s, %s::UUID)
                    """,
                    (
                        retry_id, scope.tenant_scope_id, scope.workspace_id,
                        scope.resource_scope_id, scope.facility_id, connection_id,
                        source.get("range_start"), source.get("range_end"),
                        requested_at, actor, source_id,
                    ),
                )
            except Exception as error:
                if getattr(error, "sqlstate", None) == "23505":
                    raise TelemetryRepositoryError(
                        "telemetry_retry_already_active"
                    ) from None
                raise
            if source.get("range_start") is not None:
                # A manual retry is a new logical run. Reset the bounded range
                # only after its guarded insert succeeds. Automatic transient
                # retries stay on the same run and never reach this path.
                cursor.execute(
                    """
                    DELETE FROM telemetry.connection_checkpoints cp
                    WHERE cp.resource_scope_id = %s AND cp.tenant_scope_id = %s
                      AND cp.workspace_id = %s AND cp.facility_id = %s
                      AND cp.connection_id = %s::UUID AND cp.mode = 'backfill'
                    """,
                    (*_scope_parameters(scope), connection_id),
                )
            cursor.execute(
                """
                UPDATE telemetry.data_connections c
                SET next_attempt_at = %s, retry_count = 0, updated_at = NOW()
                WHERE c.resource_scope_id = %s AND c.tenant_scope_id = %s
                  AND c.workspace_id = %s AND c.facility_id = %s
                  AND c.id = %s::UUID
                """,
                (requested_at, *_scope_parameters(scope), connection_id),
            )
            self._insert_audit_event(
                cursor,
                scope,
                event_id=str(uuid.uuid4()),
                connection_id=connection_id,
                actor_id=actor,
                action="ingestion_retry_requested",
                safe_detail={"source_run_id": source_id, "retry_run_id": retry_id},
            )
            return {
                "id": retry_id,
                "connection_id": connection_id,
                "mode": "retry",
                "status": "pending",
                "range_start": source.get("range_start"),
                "range_end": source.get("range_end"),
                "started_at": requested_at,
                "actor_id": actor,
                "source_run_id": source_id,
            }

    def list_ingestion_runs(
        self,
        scope: TelemetryRepositoryScope,
        *,
        connection_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT r.id, r.connection_id, r.mode, r.status, r.range_start,
                       r.range_end, r.started_at, r.finished_at, r.attempt_count,
                       r.retry_count, r.pages_processed, r.observations_received,
                       r.observations_accepted, r.observations_rejected,
                       r.observations_duplicate, r.observations_out_of_order,
                       r.error_code, r.error_summary, r.actor_id, r.worker_id
                FROM telemetry.ingestion_runs r
                WHERE r.resource_scope_id = %s AND r.tenant_scope_id = %s
                  AND r.workspace_id = %s AND r.facility_id = %s
                  AND r.connection_id = %s::UUID
                ORDER BY r.created_at DESC, r.id DESC LIMIT %s OFFSET %s
                """,
                (*_scope_parameters(scope), _require_uuid(connection_id, "telemetry_connection_id_invalid"), min(max(int(limit), 1), 500), max(int(offset), 0)),
            )
            return [_row_dict(cursor, row) or {} for row in cursor.fetchall()]

    def get_ingestion_run(
        self,
        scope: TelemetryRepositoryScope,
        *,
        run_id: str,
    ) -> dict[str, Any] | None:
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT r.id, r.connection_id, r.mode, r.status, r.range_start,
                       r.range_end, r.started_at, r.finished_at, r.attempt_count,
                       r.retry_count, r.pages_processed, r.observations_received,
                       r.observations_accepted, r.observations_rejected,
                       r.observations_duplicate, r.observations_out_of_order,
                       r.error_code, r.error_summary, r.actor_id, r.worker_id
                FROM telemetry.ingestion_runs r
                WHERE r.resource_scope_id = %s AND r.tenant_scope_id = %s
                  AND r.workspace_id = %s AND r.facility_id = %s
                  AND r.id = %s::UUID
                """,
                (*_scope_parameters(scope), _require_uuid(run_id, "telemetry_ingestion_run_id_invalid")),
            )
            return _row_dict(cursor, cursor.fetchone())

    def list_ingestion_errors(
        self,
        scope: TelemetryRepositoryScope,
        *,
        connection_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT e.id, e.ingestion_run_id, e.external_signal_id,
                       e.external_tag_id, e.provider_event_id, e.mapping_id,
                       e.source_timestamp_raw, e.original_value,
                       e.original_unit, e.reported_quality,
                       e.source_record_digest, e.quality_state, e.reason_code,
                       e.disposition, e.occurrence_count, e.first_seen_at,
                       e.last_seen_at, e.safe_context
                FROM telemetry.observation_rejections e
                WHERE e.resource_scope_id = %s AND e.tenant_scope_id = %s
                  AND e.workspace_id = %s AND e.facility_id = %s
                  AND e.connection_id = %s::UUID
                ORDER BY e.last_seen_at DESC, e.id DESC LIMIT %s OFFSET %s
                """,
                (*_scope_parameters(scope), _require_uuid(connection_id, "telemetry_connection_id_invalid"), min(max(int(limit), 1), 500), max(int(offset), 0)),
            )
            return [_row_dict(cursor, row) or {} for row in cursor.fetchall()]

    def list_observations(
        self,
        scope: TelemetryRepositoryScope,
        *,
        connection_id: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT o.id, o.connection_id, o.ingestion_run_id, o.system_id,
                       o.asset_id, o.external_signal_id, o.mapping_id,
                       o.mapping_revision, o.canonical_concept_id,
                       o.canonical_signal_name, o.external_tag_id,
                       o.provider_event_id, o.source_timestamp_raw,
                       o.source_timezone, o.source_offset,
                       o.timestamp_normalization_version, o.observed_at_utc,
                       o.original_value, o.original_unit, o.normalized_value,
                       o.canonical_unit, o.conversion_id, o.conversion_version,
                       o.quality_state, o.ingestion_disposition,
                       o.analysis_eligible, o.reason_codes,
                       o.source_record_digest, o.source_metadata,
                       o.mapping_provenance, o.mapping_actor_id,
                       o.mapping_mapped_at, o.mapping_authority_digest
                FROM telemetry.normalized_observations o
                WHERE o.resource_scope_id = %s AND o.tenant_scope_id = %s
                  AND o.workspace_id = %s AND o.facility_id = %s
                  AND o.connection_id = %s::UUID
                ORDER BY o.observed_at_utc DESC, o.id DESC LIMIT %s
                """,
                (*_scope_parameters(scope), _require_uuid(connection_id, "telemetry_connection_id_invalid"), min(max(int(limit), 1), 500)),
            )
            return [_row_dict(cursor, row) or {} for row in cursor.fetchall()]

    def resolve_analysis_authority_snapshot(
        self,
        scope: TelemetryRepositoryScope,
        *,
        system_id: str,
        asset_id: str | None,
        authority_digest: str,
    ) -> ServerBoundSystemIdentityV2 | None:
        """Resolve worker authority exclusively from shared PostgreSQL state."""
        system_id = _require_public_identifier(
            system_id, "telemetry_analysis_system_id_invalid"
        )
        asset_id = (
            _require_public_identifier(asset_id, "telemetry_analysis_asset_id_invalid")
            if asset_id is not None
            else None
        )
        authority_digest = str(authority_digest or "").strip().lower()
        if not _SHA256_DIGEST.fullmatch(authority_digest):
            raise ValueError("telemetry_analysis_authority_digest_invalid")
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT a.system_id, a.asset_id, a.authority_digest,
                       a.identity_digest, a.authority_snapshot
                FROM telemetry.analysis_authority_snapshots a
                WHERE a.resource_scope_id = %s AND a.tenant_scope_id = %s
                  AND a.workspace_id = %s AND a.facility_id = %s
                  AND a.system_id = %s
                  AND a.asset_id IS NOT DISTINCT FROM %s
                  AND a.authority_digest = %s
                ORDER BY a.attested_at DESC, a.id
                LIMIT 2
                """,
                (*_scope_parameters(scope), system_id, asset_id, authority_digest),
            )
            rows = [_row_dict(cursor, row) or {} for row in cursor.fetchall()]
        if len(rows) != 1:
            return None
        row = rows[0]
        snapshot = row.get("authority_snapshot")
        if not isinstance(snapshot, Mapping) or (
            str(snapshot.get("facility_id") or "") != scope.facility_id
            or str(snapshot.get("system_id") or "") != system_id
            or (str(snapshot.get("asset_id") or "").strip() or None) != asset_id
        ):
            return None
        identity = build_telemetry_server_bound_system_identity(
            scope=_phase4_scope(scope),
            system_id=system_id,
            authority_record_digest=authority_digest,
        )
        if str(row.get("identity_digest") or "") != identity.identity_digest:
            return None
        return identity

    def list_analysis_eligible_observations(
        self,
        scope: TelemetryRepositoryScope,
        *,
        connection_id: str,
        source_run_id: str | None,
        system_id: str | None = None,
        asset_id: str | None = None,
        asset_filter_applied: bool = False,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
        authority_digest: str | None = None,
        limit: int = 5_000,
    ) -> list[dict[str, Any]]:
        """Load a bounded canonical window from current approved mappings."""
        connection_id = _require_uuid(connection_id, "telemetry_connection_id_invalid")
        if source_run_id is not None:
            source_run_id = _require_uuid(
                source_run_id, "telemetry_ingestion_run_id_invalid"
            )
        if system_id is not None:
            system_id = _require_identifier(system_id, "telemetry_analysis_system_id_invalid")
        if asset_id is not None:
            asset_id = _require_identifier(asset_id, "telemetry_analysis_asset_id_invalid")
        if authority_digest is not None:
            authority_digest = str(authority_digest).strip().lower()
            if not _SHA256_DIGEST.fullmatch(authority_digest):
                raise ValueError("telemetry_analysis_authority_digest_invalid")
        for value in (window_start, window_end):
            if value is not None and (value.tzinfo is None or value.utcoffset() is None):
                raise ValueError("telemetry_analysis_window_timestamp_invalid")
        if window_start is not None and window_end is not None and window_end <= window_start:
            raise ValueError("telemetry_analysis_window_range_invalid")
        bounded_limit = min(max(int(limit), 1), 5_000)
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT o.id, o.tenant_scope_id, o.workspace_id,
                       o.resource_scope_id, o.facility_id, o.system_id,
                       o.asset_id, o.connection_id, o.ingestion_run_id,
                       o.external_signal_id, o.mapping_id, o.mapping_revision,
                       o.canonical_concept_id, o.canonical_signal_name,
                       o.external_tag_id, o.provider_event_id,
                       o.source_timestamp_raw, o.source_timezone,
                       o.source_offset, o.timestamp_normalization_version,
                       o.observed_at_utc, o.ingested_at_utc, o.original_value,
                       o.original_unit, o.normalized_value, o.canonical_unit,
                       o.conversion_id, o.conversion_version,
                       o.quality_state, o.ingestion_disposition,
                       o.analysis_eligible, o.reason_codes,
                       o.source_record_digest, o.source_metadata,
                       o.mapping_provenance, o.mapping_actor_id,
                       o.mapping_mapped_at, o.mapping_authority_digest
                FROM telemetry.normalized_observations o
                JOIN telemetry.signal_mappings m
                  ON m.resource_scope_id = o.resource_scope_id
                 AND m.tenant_scope_id = o.tenant_scope_id
                 AND m.workspace_id = o.workspace_id
                 AND m.facility_id = o.facility_id
                 AND m.connection_id = o.connection_id
                 AND m.external_signal_id = o.external_signal_id
                 AND m.id = o.mapping_id AND m.revision = o.mapping_revision
                 AND m.enabled = TRUE
                WHERE o.resource_scope_id = %s AND o.tenant_scope_id = %s
                  AND o.workspace_id = %s AND o.facility_id = %s
                  AND o.connection_id = %s::UUID
                  AND (%s::UUID IS NULL OR o.ingestion_run_id = %s::UUID)
                  AND (%s::TEXT IS NULL OR o.system_id = %s::TEXT)
                  AND (%s = FALSE OR o.asset_id IS NOT DISTINCT FROM %s::TEXT)
                  AND (%s::TIMESTAMPTZ IS NULL OR
                       o.observed_at_utc >= %s::TIMESTAMPTZ)
                  AND (%s::TIMESTAMPTZ IS NULL OR
                       o.observed_at_utc < %s::TIMESTAMPTZ)
                  AND (%s::TEXT IS NULL OR o.mapping_authority_digest = %s::TEXT)
                  AND o.analysis_eligible = TRUE
                  AND o.quality_state = 'good'
                  AND o.ingestion_disposition IN
                      ('accepted', 'out_of_order_accepted')
                ORDER BY o.observed_at_utc, o.id
                LIMIT %s
                """,
                (
                    *_scope_parameters(scope), connection_id,
                    source_run_id, source_run_id,
                    system_id, system_id, bool(asset_filter_applied), asset_id,
                    window_start, window_start, window_end, window_end,
                    authority_digest, authority_digest,
                    bounded_limit + 1,
                ),
            )
            rows = [_row_dict(cursor, row) or {} for row in cursor.fetchall()]
            if len(rows) > bounded_limit:
                raise TelemetryRepositoryError(
                    "telemetry_analysis_observation_limit_exceeded"
                )
            return rows

    def get_analysis_window(
        self,
        scope: TelemetryRepositoryScope,
        *,
        window_id: str,
    ) -> dict[str, Any] | None:
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT w.id, w.facility_id, w.system_id, w.asset_id,
                       w.source_ingestion_run_id, w.window_start, w.window_end,
                       w.status, w.authority_digest, w.quality_summary,
                       w.execution_claim_token, w.execution_claim_expires_at,
                       w.execution_attempt_count, w.result_digest,
                       w.result_metadata, w.evidence_lineage, w.completed_at,
                       w.created_at, w.updated_at
                FROM telemetry.analysis_windows w
                WHERE w.resource_scope_id = %s AND w.tenant_scope_id = %s
                  AND w.workspace_id = %s AND w.facility_id = %s
                  AND w.id = %s::UUID
                """,
                (*_scope_parameters(scope), _require_uuid(window_id, "telemetry_analysis_window_id_invalid")),
            )
            return _row_dict(cursor, cursor.fetchone())

    def persist_analysis_window(
        self,
        scope: TelemetryRepositoryScope,
        *,
        window_record: Mapping[str, Any],
        observation_links: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        """Persist an immutable window and its exact observation set atomically."""
        record = dict(window_record)
        expected_scope = {
            "tenant_scope_id": scope.tenant_scope_id,
            "workspace_id": scope.workspace_id,
            "resource_scope_id": scope.resource_scope_id,
            "facility_id": scope.facility_id,
        }
        if any(str(record.get(key) or "") != value for key, value in expected_scope.items()):
            raise ValueError("telemetry_analysis_window_scope_mismatch")
        window_id = _require_uuid(str(record.get("id") or ""), "telemetry_analysis_window_id_invalid")
        source_run_id = _require_uuid(
            str(record.get("source_ingestion_run_id") or ""),
            "telemetry_ingestion_run_id_invalid",
        )
        system_id = _require_identifier(
            str(record.get("system_id") or ""), "telemetry_analysis_system_id_invalid"
        )
        asset_id = record.get("asset_id")
        if asset_id is not None:
            asset_id = _require_identifier(str(asset_id), "telemetry_analysis_asset_id_invalid")
        window_start = record.get("window_start")
        window_end = record.get("window_end")
        if not isinstance(window_start, datetime) or not isinstance(window_end, datetime):
            raise ValueError("telemetry_analysis_window_timestamp_invalid")
        if (
            window_start.tzinfo is None
            or window_start.utcoffset() is None
            or window_end.tzinfo is None
            or window_end.utcoffset() is None
            or window_end <= window_start
        ):
            raise ValueError("telemetry_analysis_window_range_invalid")
        status = str(record.get("status") or "")
        if status not in {"eligible", "ineligible"}:
            raise ValueError("telemetry_analysis_window_initial_status_invalid")
        authority_digest = str(record.get("authority_digest") or "").strip().lower()
        if not _SHA256_DIGEST.fullmatch(authority_digest):
            raise ValueError("telemetry_analysis_window_authority_digest_invalid")
        quality_summary = record.get("quality_summary") or {}
        if not isinstance(quality_summary, Mapping):
            raise ValueError("telemetry_analysis_window_quality_invalid")
        quality_json = _safe_json(
            quality_summary,
            code="telemetry_analysis_window_quality_invalid",
            reject_sensitive=True,
        )

        link_ids: list[str] = []
        for raw in observation_links:
            link = dict(raw)
            if any(str(link.get(key) or "") != value for key, value in expected_scope.items()):
                raise ValueError("telemetry_analysis_window_link_scope_mismatch")
            if str(link.get("analysis_window_id") or "") != window_id:
                raise ValueError("telemetry_analysis_window_link_identity_mismatch")
            link_ids.append(
                _require_uuid(
                    str(link.get("observation_id") or ""),
                    "telemetry_analysis_observation_id_invalid",
                )
            )
        if len(link_ids) != len(set(link_ids)):
            raise ValueError("telemetry_analysis_window_link_duplicate")
        if status == "eligible" and not link_ids:
            raise ValueError("telemetry_analysis_window_observations_required")
        if status == "ineligible" and link_ids:
            raise ValueError("telemetry_analysis_ineligible_window_has_observations")

        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT r.id, r.connection_id FROM telemetry.ingestion_runs r
                WHERE r.resource_scope_id = %s AND r.tenant_scope_id = %s
                  AND r.workspace_id = %s AND r.facility_id = %s
                  AND r.id = %s::UUID
                FOR SHARE
                """,
                (*_scope_parameters(scope), source_run_id),
            )
            source_run_row = cursor.fetchone()
            if source_run_row is None:
                raise TelemetryRepositoryError("telemetry_ingestion_run_not_found")
            source_connection_id = str(
                source_run_row.get("connection_id")
                if isinstance(source_run_row, Mapping)
                else source_run_row[1]
            )
            if link_ids:
                cursor.execute(
                    """
                    SELECT COUNT(DISTINCT o.id) AS membership_count,
                           COUNT(DISTINCT o.id) FILTER (
                               WHERE o.ingestion_run_id = %s::UUID
                           ) AS trigger_count
                    FROM telemetry.normalized_observations o
                    JOIN telemetry.signal_mappings m
                      ON m.resource_scope_id = o.resource_scope_id
                     AND m.tenant_scope_id = o.tenant_scope_id
                     AND m.workspace_id = o.workspace_id
                     AND m.facility_id = o.facility_id
                     AND m.connection_id = o.connection_id
                     AND m.id = o.mapping_id AND m.revision = o.mapping_revision
                     AND m.enabled = TRUE
                    WHERE o.resource_scope_id = %s AND o.tenant_scope_id = %s
                      AND o.workspace_id = %s AND o.facility_id = %s
                      AND o.connection_id = %s::UUID
                      AND o.system_id = %s
                      AND o.asset_id IS NOT DISTINCT FROM %s
                      AND o.observed_at_utc >= %s AND o.observed_at_utc < %s
                      AND o.analysis_eligible = TRUE AND o.quality_state = 'good'
                      AND o.mapping_authority_digest = %s
                      AND o.ingestion_disposition IN
                          ('accepted', 'out_of_order_accepted')
                      AND o.id = ANY(%s::UUID[])
                    """,
                    (
                        source_run_id, *_scope_parameters(scope),
                        source_connection_id, system_id, asset_id,
                        window_start, window_end, authority_digest, link_ids,
                    ),
                )
                membership_row = cursor.fetchone()
                if isinstance(membership_row, Mapping):
                    membership_count = int(
                        membership_row.get("membership_count") or 0
                    )
                    trigger_count = int(membership_row.get("trigger_count") or 0)
                else:
                    membership_count = int(membership_row[0]) if membership_row else 0
                    trigger_count = int(membership_row[1]) if membership_row else 0
                if membership_count != len(link_ids) or trigger_count < 1:
                    raise TelemetryMappingConflict(
                        "telemetry_analysis_window_observation_membership_conflict"
                    )
            cursor.execute(
                """
                INSERT INTO telemetry.analysis_windows (
                    id, tenant_scope_id, workspace_id, resource_scope_id,
                    facility_id, system_id, asset_id, source_ingestion_run_id,
                    window_start, window_end, status, authority_digest,
                    quality_summary
                ) VALUES (%s::UUID, %s, %s, %s, %s, %s, %s, %s::UUID,
                          %s, %s, %s, %s, %s::JSONB)
                ON CONFLICT (id) DO NOTHING
                RETURNING id
                """,
                (
                    window_id, scope.tenant_scope_id, scope.workspace_id,
                    scope.resource_scope_id, scope.facility_id, system_id,
                    asset_id, source_run_id, window_start, window_end, status,
                    authority_digest, quality_json,
                ),
            )
            inserted = cursor.fetchone() is not None
            if not inserted:
                cursor.execute(
                    """
                    SELECT w.id
                    FROM telemetry.analysis_windows w
                    WHERE w.resource_scope_id = %s AND w.tenant_scope_id = %s
                      AND w.workspace_id = %s AND w.facility_id = %s
                      AND w.id = %s::UUID AND w.system_id = %s
                      AND w.asset_id IS NOT DISTINCT FROM %s
                      AND w.source_ingestion_run_id = %s::UUID
                      AND w.window_start = %s AND w.window_end = %s
                      AND w.authority_digest = %s
                      AND w.quality_summary = %s::JSONB
                    FOR UPDATE
                    """,
                    (
                        *_scope_parameters(scope), window_id, system_id, asset_id,
                        source_run_id, window_start, window_end,
                        authority_digest, quality_json,
                    ),
                )
                if cursor.fetchone() is None:
                    raise TelemetryMappingConflict(
                        "telemetry_analysis_window_identity_conflict"
                    )
            if link_ids:
                cursor.execute(
                    """
                    WITH input AS (
                        SELECT DISTINCT observation_id
                        FROM unnest(%s::UUID[]) AS observation_id
                    )
                    INSERT INTO telemetry.analysis_window_observations (
                        tenant_scope_id, workspace_id, resource_scope_id,
                        facility_id, analysis_window_id, observation_id
                    )
                    SELECT %s, %s, %s, %s, %s::UUID, input.observation_id
                    FROM input
                    ON CONFLICT (resource_scope_id, analysis_window_id,
                                 observation_id) DO NOTHING
                    """,
                    (
                        link_ids, scope.tenant_scope_id, scope.workspace_id,
                        scope.resource_scope_id, scope.facility_id, window_id,
                    ),
                )
            cursor.execute(
                """
                SELECT COUNT(*) AS total_count,
                       COUNT(*) FILTER (
                           WHERE link.observation_id = ANY(%s::UUID[])
                       ) AS matched_count
                FROM telemetry.analysis_window_observations link
                WHERE link.resource_scope_id = %s AND link.tenant_scope_id = %s
                  AND link.workspace_id = %s AND link.facility_id = %s
                  AND link.analysis_window_id = %s::UUID
                """,
                (link_ids, *_scope_parameters(scope), window_id),
            )
            count_row = cursor.fetchone()
            if isinstance(count_row, Mapping):
                total_count = int(count_row.get("total_count") or 0)
                matched_count = int(count_row.get("matched_count") or 0)
            else:
                total_count = int(count_row[0]) if count_row else 0
                matched_count = int(count_row[1]) if count_row else 0
            if total_count != len(link_ids) or matched_count != len(link_ids):
                raise TelemetryMappingConflict(
                    "telemetry_analysis_window_link_set_conflict"
                )
            cursor.execute(
                """
                SELECT w.id, w.facility_id, w.system_id, w.asset_id,
                       w.source_ingestion_run_id, w.window_start, w.window_end,
                       w.status, w.authority_digest, w.quality_summary,
                       w.execution_claim_token, w.execution_claim_expires_at,
                       w.execution_attempt_count, w.result_digest,
                       w.result_metadata, w.evidence_lineage, w.completed_at,
                       w.created_at, w.updated_at
                FROM telemetry.analysis_windows w
                WHERE w.resource_scope_id = %s AND w.tenant_scope_id = %s
                  AND w.workspace_id = %s AND w.facility_id = %s
                  AND w.id = %s::UUID
                """,
                (*_scope_parameters(scope), window_id),
            )
            result = _row_dict(cursor, cursor.fetchone())
            if result is None:
                raise TelemetryRepositoryError("telemetry_analysis_window_not_found")
            return result

    def update_analysis_window_status(
        self,
        scope: TelemetryRepositoryScope,
        *,
        window_id: str,
        expected_status: str,
        target_status: str,
        reason_code: str | None = None,
    ) -> dict[str, Any]:
        transitions = {
            "eligible": {"running"},
            "running": {"completed", "failed", "ineligible"},
        }
        if target_status not in transitions.get(expected_status, set()):
            raise ValueError("telemetry_analysis_window_status_transition_invalid")
        if reason_code is not None:
            reason_code = _require_public_identifier(
                reason_code, "telemetry_analysis_window_reason_invalid"
            )
            if target_status not in {"failed", "ineligible"}:
                raise ValueError("telemetry_analysis_window_reason_status_invalid")
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE telemetry.analysis_windows w
                SET status = %s,
                    quality_summary = CASE
                        WHEN %s::TEXT IS NULL THEN w.quality_summary
                        ELSE w.quality_summary || jsonb_build_object(
                            'status_reason_code', %s::TEXT
                        )
                    END,
                    updated_at = NOW()
                WHERE w.resource_scope_id = %s AND w.tenant_scope_id = %s
                  AND w.workspace_id = %s AND w.facility_id = %s
                  AND w.id = %s::UUID AND w.status = %s
                RETURNING w.id, w.facility_id, w.system_id, w.asset_id,
                          w.source_ingestion_run_id, w.window_start,
                          w.window_end, w.status, w.authority_digest,
                          w.quality_summary, w.created_at, w.updated_at
                """,
                (
                    target_status, reason_code, reason_code,
                    *_scope_parameters(scope),
                    _require_uuid(window_id, "telemetry_analysis_window_id_invalid"),
                    expected_status,
                ),
            )
            result = _row_dict(cursor, cursor.fetchone())
            if result is None:
                raise TelemetryCheckpointConflict(
                    "telemetry_analysis_window_status_conflict"
                )
            return result

    def claim_analysis_window_execution(
        self,
        scope: TelemetryRepositoryScope,
        *,
        window_id: str,
        claim_token: str,
        claimed_at: datetime,
        claim_expires_at: datetime,
    ) -> dict[str, Any]:
        """Claim one eligible window; SII execution is never auto-retried."""
        window_id = _require_uuid(window_id, "telemetry_analysis_window_id_invalid")
        claim_token = _require_uuid(
            claim_token, "telemetry_analysis_execution_claim_invalid"
        )
        for value in (claimed_at, claim_expires_at):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("telemetry_analysis_execution_claim_time_invalid")
        if claim_expires_at <= claimed_at or claim_expires_at > claimed_at + timedelta(
            minutes=30
        ):
            raise ValueError("telemetry_analysis_execution_claim_range_invalid")
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE telemetry.analysis_windows w
                SET status = 'running', execution_claim_token = %s::UUID,
                    execution_claim_expires_at = %s,
                    execution_attempt_count = w.execution_attempt_count + 1,
                    updated_at = %s
                WHERE w.resource_scope_id = %s AND w.tenant_scope_id = %s
                  AND w.workspace_id = %s AND w.facility_id = %s
                  AND w.id = %s::UUID AND w.status = 'eligible'
                  AND w.execution_claim_token IS NULL
                RETURNING w.id, w.status, w.execution_claim_token,
                          w.execution_claim_expires_at,
                          w.execution_attempt_count, w.quality_summary
                """,
                (
                    claim_token,
                    claim_expires_at,
                    claimed_at,
                    *_scope_parameters(scope),
                    window_id,
                ),
            )
            result = _row_dict(cursor, cursor.fetchone())
            if result is None:
                raise TelemetryCheckpointConflict(
                    "telemetry_analysis_execution_claim_conflict"
                )
            return result

    def recover_stale_analysis_window_execution(
        self,
        scope: TelemetryRepositoryScope,
        *,
        window_id: str,
        recovered_at: datetime,
    ) -> dict[str, Any] | None:
        """Fail closed after an expired claim; never issue a second SII call."""
        if recovered_at.tzinfo is None or recovered_at.utcoffset() is None:
            raise ValueError("telemetry_analysis_execution_recovery_time_invalid")
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE telemetry.analysis_windows w
                SET status = 'failed', execution_claim_token = NULL,
                    execution_claim_expires_at = NULL, completed_at = %s,
                    quality_summary = w.quality_summary || jsonb_build_object(
                        'status_reason_code',
                        'telemetry_analysis_execution_claim_expired'
                    ),
                    updated_at = %s
                WHERE w.resource_scope_id = %s AND w.tenant_scope_id = %s
                  AND w.workspace_id = %s AND w.facility_id = %s
                  AND w.id = %s::UUID AND w.status = 'running'
                  AND (w.execution_claim_expires_at IS NULL
                       OR w.execution_claim_expires_at <= %s)
                RETURNING w.id, w.status, w.execution_attempt_count,
                          w.quality_summary, w.completed_at
                """,
                (
                    recovered_at,
                    recovered_at,
                    *_scope_parameters(scope),
                    _require_uuid(
                        window_id, "telemetry_analysis_window_id_invalid"
                    ),
                    recovered_at,
                ),
            )
            return _row_dict(cursor, cursor.fetchone())

    def finish_analysis_window_execution(
        self,
        scope: TelemetryRepositoryScope,
        *,
        window_id: str,
        claim_token: str,
        completed_at: datetime,
        target_status: str,
        reason_code: str | None = None,
        result_digest: str | None = None,
        result_metadata: Mapping[str, Any] | None = None,
        evidence_lineage: Mapping[str, Any] | None = None,
        result_artifact: CanonicalResultArtifact | None = None,
    ) -> dict[str, Any]:
        """Atomically publish the canonical artifact and terminal window state."""
        if target_status not in {"completed", "failed", "ineligible"}:
            raise ValueError("telemetry_analysis_window_status_transition_invalid")
        if completed_at.tzinfo is None or completed_at.utcoffset() is None:
            raise ValueError("telemetry_analysis_completion_time_invalid")
        if target_status == "completed":
            if not isinstance(result_artifact, CanonicalResultArtifact):
                raise ValueError("telemetry_analysis_result_artifact_required")
            normalized_window_id = _require_uuid(
                window_id, "telemetry_analysis_window_id_invalid"
            )
            artifact_window_id = _require_uuid(
                result_artifact.analysis_window_id,
                "telemetry_analysis_result_window_id_invalid",
            )
            if artifact_window_id != normalized_window_id:
                raise ValueError("telemetry_analysis_result_window_id_mismatch")
            artifact_source_run_id = _require_uuid(
                result_artifact.source_run_id,
                "telemetry_analysis_result_source_run_id_invalid",
            )
            if result_artifact.result_id != canonical_result_id(
                window_id=artifact_window_id,
                execution_contract_version=(
                    result_artifact.execution_contract_version
                ),
            ):
                raise ValueError("telemetry_analysis_result_id_mismatch")
            digest = result_artifact.payload_digest
            if not _SHA256_DIGEST.fullmatch(digest):
                raise ValueError("telemetry_analysis_result_digest_invalid")
            supplied_digest = str(result_digest or digest).strip().lower()
            if supplied_digest != digest:
                raise ValueError("telemetry_analysis_result_digest_mismatch")
            if not isinstance(result_metadata, Mapping) or not isinstance(
                evidence_lineage, Mapping
            ):
                raise ValueError("telemetry_analysis_result_metadata_required")
            lineage_count = evidence_lineage.get("observation_count")
            lineage_digest = str(
                evidence_lineage.get("observation_lineage_digest") or ""
            ).lower()
            if (
                int(lineage_count if lineage_count is not None else -1)
                != result_artifact.observation_count
                or lineage_digest != result_artifact.observation_lineage_digest
            ):
                raise ValueError("telemetry_analysis_result_lineage_mismatch")
            completion_metadata = {
                **dict(result_metadata),
                "canonical_result_id": result_artifact.result_id,
                "artifact_schema_version": result_artifact.artifact_schema_version,
                "execution_contract_version": result_artifact.execution_contract_version,
                "analysis_schema_version": result_artifact.analysis_schema_version,
                "analysis_contract_version": result_artifact.analysis_contract_version,
                "artifact_payload_digest": result_artifact.payload_digest,
                "artifact_payload_uncompressed_bytes": (
                    result_artifact.payload_uncompressed_bytes
                ),
                "artifact_payload_stored_bytes": result_artifact.payload_stored_bytes,
                "artifact_serialization_ms": result_artifact.serialization_ms,
            }
            metadata_json = _safe_json(
                completion_metadata,
                code="telemetry_analysis_result_metadata_invalid",
                reject_sensitive=True,
            )
            lineage_json = _safe_json(
                evidence_lineage,
                code="telemetry_analysis_evidence_lineage_invalid",
                reject_sensitive=True,
            )
            if len(lineage_json.encode("utf-8")) > 65_536:
                raise ValueError("telemetry_analysis_evidence_lineage_invalid")
            reference_json = _safe_json(
                result_artifact.reference_metadata,
                code="telemetry_analysis_result_reference_metadata_invalid",
                reject_sensitive=True,
            )
            if len(reference_json.encode("utf-8")) > 32_768:
                raise ValueError("telemetry_analysis_result_reference_metadata_invalid")
            finding_ids_json = _safe_json(
                result_artifact.finding_ids,
                code="telemetry_analysis_result_finding_ids_invalid",
            )
            evidence_ids_json = _safe_json(
                result_artifact.evidence_ids,
                code="telemetry_analysis_result_evidence_ids_invalid",
            )
            if len(finding_ids_json.encode("utf-8")) + len(
                evidence_ids_json.encode("utf-8")
            ) > 65_536:
                raise ValueError("telemetry_analysis_result_ids_invalid")
            reason_code = None
        else:
            if result_artifact is not None:
                raise ValueError("telemetry_analysis_result_artifact_status_invalid")
            digest = None
            metadata_json = "{}"
            lineage_json = "{}"
            reason_code = _require_public_identifier(
                str(reason_code or ""),
                "telemetry_analysis_window_reason_invalid",
            )
        artifact_inserted = False
        with self._connection() as connection, connection.cursor() as cursor:
            if result_artifact is not None:
                cursor.execute(
                    """
                    INSERT INTO telemetry.analysis_result_artifacts (
                        id, tenant_scope_id, workspace_id, resource_scope_id,
                        facility_id, analysis_window_id, connection_id,
                        source_ingestion_run_id, system_id, asset_id,
                        window_start, window_end, authority_digest,
                        artifact_schema_version, execution_contract_version,
                        analysis_schema_version, analysis_contract_version,
                        engine_name, engine_version, reference_metadata,
                        observation_count, observation_lineage_digest,
                        finding_ids, evidence_ids, payload_encoding,
                        payload_digest, payload_uncompressed_bytes,
                        payload_stored_bytes, serialization_ms, payload
                    )
                    SELECT %s::UUID, w.tenant_scope_id, w.workspace_id,
                           w.resource_scope_id, w.facility_id, w.id,
                           r.connection_id, w.source_ingestion_run_id,
                           w.system_id, w.asset_id, w.window_start, w.window_end,
                           w.authority_digest, %s, %s, %s, %s, %s, %s,
                           %s::JSONB, %s, %s, %s::JSONB, %s::JSONB, %s,
                           %s, %s, %s, %s, %s
                    FROM telemetry.analysis_windows w
                    JOIN telemetry.ingestion_runs r
                      ON r.resource_scope_id = w.resource_scope_id
                     AND r.tenant_scope_id = w.tenant_scope_id
                     AND r.workspace_id = w.workspace_id
                     AND r.facility_id = w.facility_id
                     AND r.id = w.source_ingestion_run_id
                    WHERE w.resource_scope_id = %s AND w.tenant_scope_id = %s
                      AND w.workspace_id = %s AND w.facility_id = %s
                      AND w.id = %s::UUID AND w.status = 'running'
                      AND w.source_ingestion_run_id = %s::UUID
                      AND w.execution_claim_token = %s::UUID
                      AND w.execution_claim_expires_at > %s
                    ON CONFLICT (resource_scope_id, tenant_scope_id,
                                 workspace_id, facility_id,
                                 analysis_window_id) DO NOTHING
                    RETURNING id
                    """,
                    (
                        result_artifact.result_id,
                        result_artifact.artifact_schema_version,
                        result_artifact.execution_contract_version,
                        result_artifact.analysis_schema_version,
                        result_artifact.analysis_contract_version,
                        result_artifact.engine_name,
                        result_artifact.engine_version,
                        reference_json,
                        result_artifact.observation_count,
                        result_artifact.observation_lineage_digest,
                        finding_ids_json,
                        evidence_ids_json,
                        result_artifact.payload_encoding,
                        result_artifact.payload_digest,
                        result_artifact.payload_uncompressed_bytes,
                        result_artifact.payload_stored_bytes,
                        result_artifact.serialization_ms,
                        result_artifact.payload,
                        *_scope_parameters(scope),
                        normalized_window_id,
                        artifact_source_run_id,
                        _require_uuid(
                            claim_token,
                            "telemetry_analysis_execution_claim_invalid",
                        ),
                        completed_at,
                    ),
                )
                artifact_inserted = cursor.fetchone() is not None
                cursor.execute(
                    """
                    SELECT a.id, a.analysis_window_id,
                           a.source_ingestion_run_id,
                           a.artifact_schema_version,
                           a.execution_contract_version,
                           a.analysis_schema_version,
                           a.analysis_contract_version, a.engine_name,
                           a.engine_version, a.reference_metadata,
                           a.observation_count,
                           a.observation_lineage_digest, a.finding_ids,
                           a.evidence_ids, a.payload_encoding,
                           a.payload_digest, a.payload_uncompressed_bytes,
                           a.payload_stored_bytes, a.serialization_ms,
                           a.payload
                    FROM telemetry.analysis_result_artifacts a
                    WHERE a.resource_scope_id = %s
                      AND a.tenant_scope_id = %s
                      AND a.workspace_id = %s AND a.facility_id = %s
                      AND a.analysis_window_id = %s::UUID
                    FOR UPDATE
                    """,
                    (
                        *_scope_parameters(scope),
                        _require_uuid(
                            window_id, "telemetry_analysis_window_id_invalid"
                        ),
                    ),
                )
                existing_artifact = _row_dict(cursor, cursor.fetchone())
                if existing_artifact is None:
                    raise TelemetryCheckpointConflict(
                        "telemetry_analysis_execution_completion_conflict"
                    )
                stored_payload = existing_artifact.get("payload")
                if isinstance(stored_payload, memoryview):
                    stored_payload = stored_payload.tobytes()
                expected_artifact = {
                    "id": result_artifact.result_id,
                    "analysis_window_id": _require_uuid(
                        window_id, "telemetry_analysis_window_id_invalid"
                    ),
                    "source_ingestion_run_id": artifact_source_run_id,
                    "artifact_schema_version": result_artifact.artifact_schema_version,
                    "execution_contract_version": result_artifact.execution_contract_version,
                    "analysis_schema_version": result_artifact.analysis_schema_version,
                    "analysis_contract_version": result_artifact.analysis_contract_version,
                    "engine_name": result_artifact.engine_name,
                    "engine_version": result_artifact.engine_version,
                    "reference_metadata": dict(result_artifact.reference_metadata),
                    "observation_count": result_artifact.observation_count,
                    "observation_lineage_digest": result_artifact.observation_lineage_digest,
                    "finding_ids": dict(result_artifact.finding_ids),
                    "evidence_ids": dict(result_artifact.evidence_ids),
                    "payload_encoding": result_artifact.payload_encoding,
                    "payload_digest": result_artifact.payload_digest,
                    "payload_uncompressed_bytes": result_artifact.payload_uncompressed_bytes,
                    "payload_stored_bytes": result_artifact.payload_stored_bytes,
                    "payload": result_artifact.payload,
                }
                actual_artifact = {
                    key: existing_artifact.get(key) for key in expected_artifact
                }
                actual_artifact["id"] = str(actual_artifact["id"])
                actual_artifact["analysis_window_id"] = str(
                    actual_artifact["analysis_window_id"]
                )
                actual_artifact["source_ingestion_run_id"] = str(
                    actual_artifact["source_ingestion_run_id"]
                )
                actual_artifact["payload"] = stored_payload
                if actual_artifact != expected_artifact:
                    raise TelemetryResultArtifactConflict(
                        "telemetry_analysis_result_artifact_conflict"
                    )
            cursor.execute(
                """
                UPDATE telemetry.analysis_windows w
                SET status = %s, result_digest = %s,
                    result_metadata = %s::JSONB,
                    evidence_lineage = %s::JSONB,
                    completed_at = %s,
                    execution_claim_token = NULL,
                    execution_claim_expires_at = NULL,
                    quality_summary = CASE
                        WHEN %s::TEXT IS NULL THEN w.quality_summary
                        ELSE w.quality_summary || jsonb_build_object(
                            'status_reason_code', %s::TEXT
                        )
                    END,
                    updated_at = %s
                WHERE w.resource_scope_id = %s AND w.tenant_scope_id = %s
                  AND w.workspace_id = %s AND w.facility_id = %s
                  AND w.id = %s::UUID AND w.status = 'running'
                  AND w.execution_claim_token = %s::UUID
                  AND w.execution_claim_expires_at > %s
                RETURNING w.id, w.status, w.execution_attempt_count,
                          w.result_digest, w.result_metadata,
                          w.evidence_lineage, w.quality_summary, w.completed_at
                """,
                (
                    target_status,
                    digest,
                    metadata_json,
                    lineage_json,
                    completed_at,
                    reason_code,
                    reason_code,
                    completed_at,
                    *_scope_parameters(scope),
                    _require_uuid(
                        window_id, "telemetry_analysis_window_id_invalid"
                    ),
                    _require_uuid(
                        claim_token, "telemetry_analysis_execution_claim_invalid"
                    ),
                    completed_at,
                ),
            )
            result = _row_dict(cursor, cursor.fetchone())
            if result is None:
                raise TelemetryCheckpointConflict(
                    "telemetry_analysis_execution_completion_conflict"
                )
        if result_artifact is not None:
            logger.info(
                "telemetry_canonical_result_persisted"
                if artifact_inserted
                else "telemetry_canonical_result_already_exists",
                extra={
                    "event": (
                        "telemetry_canonical_result_persisted"
                        if artifact_inserted
                        else "telemetry_canonical_result_already_exists"
                    ),
                    "result_id": result_artifact.result_id,
                    "window_id": window_id,
                    "payload_digest": result_artifact.payload_digest,
                    "payload_uncompressed_bytes": (
                        result_artifact.payload_uncompressed_bytes
                    ),
                    "payload_stored_bytes": result_artifact.payload_stored_bytes,
                    "serialization_ms": result_artifact.serialization_ms,
                },
            )
            result["canonical_result_id"] = result_artifact.result_id
        return result

    def list_analysis_result_artifacts(
        self,
        scope: TelemetryRepositoryScope,
        *,
        connection_id: str,
        source_run_id: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """List bounded immutable-result identities for one exact scoped run."""
        connection_uuid = _require_uuid(
            connection_id, "telemetry_connection_id_invalid"
        )
        run_uuid = _require_uuid(
            source_run_id, "telemetry_ingestion_run_id_invalid"
        )
        bounded_limit = min(max(int(limit), 1), 200)
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT a.id, a.analysis_window_id, a.connection_id,
                       a.source_ingestion_run_id, a.facility_id, a.system_id,
                       a.asset_id, a.window_start, a.window_end,
                       a.artifact_schema_version,
                       a.execution_contract_version,
                       a.analysis_schema_version,
                       a.analysis_contract_version, a.engine_name,
                       a.engine_version, a.reference_metadata,
                       a.observation_count,
                       a.observation_lineage_digest, a.finding_ids,
                       a.evidence_ids, a.payload_encoding, a.payload_digest,
                       a.payload_uncompressed_bytes, a.payload_stored_bytes,
                       a.serialization_ms, a.created_at, w.result_metadata
                FROM telemetry.analysis_result_artifacts a
                JOIN telemetry.analysis_windows w
                  ON w.resource_scope_id = a.resource_scope_id
                 AND w.tenant_scope_id = a.tenant_scope_id
                 AND w.workspace_id = a.workspace_id
                 AND w.facility_id = a.facility_id
                 AND w.id = a.analysis_window_id
                 AND w.status = 'completed'
                 AND w.result_digest = a.payload_digest
                WHERE a.resource_scope_id = %s AND a.tenant_scope_id = %s
                  AND a.workspace_id = %s AND a.facility_id = %s
                  AND a.connection_id = %s::UUID
                  AND a.source_ingestion_run_id = %s::UUID
                ORDER BY a.window_start DESC, a.system_id,
                         COALESCE(a.asset_id, ''), a.id
                LIMIT %s
                """,
                (
                    *_scope_parameters(scope),
                    connection_uuid,
                    run_uuid,
                    bounded_limit,
                ),
            )
            return [_row_dict(cursor, row) or {} for row in cursor.fetchall()]

    def get_analysis_result_artifact(
        self,
        scope: TelemetryRepositoryScope,
        *,
        connection_id: str,
        source_run_id: str,
        system_id: str,
        asset_id: str | None,
        result_id: str,
    ) -> dict[str, Any] | None:
        """Read one artifact only through its complete authorized identity."""
        connection_uuid = _require_uuid(
            connection_id, "telemetry_connection_id_invalid"
        )
        run_uuid = _require_uuid(
            source_run_id, "telemetry_ingestion_run_id_invalid"
        )
        result_uuid = _require_uuid(result_id, "telemetry_analysis_result_id_invalid")
        system = _require_public_identifier(
            system_id, "telemetry_analysis_system_id_invalid"
        )
        asset = (
            _require_public_identifier(
                asset_id, "telemetry_analysis_asset_id_invalid"
            )
            if asset_id is not None
            else None
        )
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT a.id, a.tenant_scope_id, a.workspace_id,
                       a.resource_scope_id, a.facility_id,
                       a.analysis_window_id, a.connection_id,
                       a.source_ingestion_run_id, a.system_id, a.asset_id,
                       a.window_start, a.window_end, a.authority_digest,
                       a.artifact_schema_version,
                       a.execution_contract_version,
                       a.analysis_schema_version,
                       a.analysis_contract_version, a.engine_name,
                       a.engine_version, a.reference_metadata,
                       a.observation_count,
                       a.observation_lineage_digest, a.finding_ids,
                       a.evidence_ids, a.payload_encoding, a.payload_digest,
                       a.payload_uncompressed_bytes, a.payload_stored_bytes,
                       a.serialization_ms, a.payload, a.created_at
                FROM telemetry.analysis_result_artifacts a
                JOIN telemetry.analysis_windows w
                  ON w.resource_scope_id = a.resource_scope_id
                 AND w.tenant_scope_id = a.tenant_scope_id
                 AND w.workspace_id = a.workspace_id
                 AND w.facility_id = a.facility_id
                 AND w.id = a.analysis_window_id
                 AND w.status = 'completed'
                 AND w.result_digest = a.payload_digest
                WHERE a.resource_scope_id = %s AND a.tenant_scope_id = %s
                  AND a.workspace_id = %s AND a.facility_id = %s
                  AND a.connection_id = %s::UUID
                  AND a.source_ingestion_run_id = %s::UUID
                  AND a.system_id = %s
                  AND a.asset_id IS NOT DISTINCT FROM %s
                  AND a.id = %s::UUID
                """,
                (
                    *_scope_parameters(scope),
                    connection_uuid,
                    run_uuid,
                    system,
                    asset,
                    result_uuid,
                ),
            )
            return _row_dict(cursor, cursor.fetchone())

    def get_analysis_result_artifact_metadata(
        self,
        scope: TelemetryRepositoryScope,
        *,
        connection_id: str,
        source_run_id: str,
        system_id: str,
        asset_id: str | None,
        result_id: str,
    ) -> dict[str, Any] | None:
        """Read immutable identity metadata without loading artifact bytes."""
        connection_uuid = _require_uuid(
            connection_id, "telemetry_connection_id_invalid"
        )
        run_uuid = _require_uuid(
            source_run_id, "telemetry_ingestion_run_id_invalid"
        )
        result_uuid = _require_uuid(result_id, "telemetry_analysis_result_id_invalid")
        system = _require_public_identifier(
            system_id, "telemetry_analysis_system_id_invalid"
        )
        asset = (
            _require_public_identifier(
                asset_id, "telemetry_analysis_asset_id_invalid"
            )
            if asset_id is not None
            else None
        )
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT a.id, a.analysis_window_id, a.connection_id,
                       a.source_ingestion_run_id, a.system_id, a.asset_id,
                       a.authority_digest, a.observation_count,
                       a.observation_lineage_digest, a.payload_digest
                FROM telemetry.analysis_result_artifacts a
                JOIN telemetry.analysis_windows w
                  ON w.resource_scope_id = a.resource_scope_id
                 AND w.tenant_scope_id = a.tenant_scope_id
                 AND w.workspace_id = a.workspace_id
                 AND w.facility_id = a.facility_id
                 AND w.id = a.analysis_window_id
                 AND w.status = 'completed'
                 AND w.result_digest = a.payload_digest
                WHERE a.resource_scope_id = %s AND a.tenant_scope_id = %s
                  AND a.workspace_id = %s AND a.facility_id = %s
                  AND a.connection_id = %s::UUID
                  AND a.source_ingestion_run_id = %s::UUID
                  AND a.system_id = %s
                  AND a.asset_id IS NOT DISTINCT FROM %s
                  AND a.id = %s::UUID
                """,
                (
                    *_scope_parameters(scope),
                    connection_uuid,
                    run_uuid,
                    system,
                    asset,
                    result_uuid,
                ),
            )
            return _row_dict(cursor, cursor.fetchone())

    def list_analysis_result_lineage_records(
        self,
        scope: TelemetryRepositoryScope,
        *,
        connection_id: str,
        source_run_id: str,
        system_id: str,
        asset_id: str | None,
        result_id: str,
    ) -> list[dict[str, Any]]:
        """Load the exact membership used by one fully scoped result."""
        connection_uuid = _require_uuid(
            connection_id, "telemetry_connection_id_invalid"
        )
        run_uuid = _require_uuid(
            source_run_id, "telemetry_ingestion_run_id_invalid"
        )
        result_uuid = _require_uuid(result_id, "telemetry_analysis_result_id_invalid")
        system = _require_public_identifier(
            system_id, "telemetry_analysis_system_id_invalid"
        )
        asset = (
            _require_public_identifier(
                asset_id, "telemetry_analysis_asset_id_invalid"
            )
            if asset_id is not None
            else None
        )
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT o.id AS observation_id, o.connection_id,
                       o.ingestion_run_id, o.external_signal_id, o.mapping_id,
                       o.mapping_revision,
                       o.canonical_concept_id AS canonical_signal_id,
                       o.canonical_signal_name, o.system_id, o.asset_id,
                       o.external_tag_id, o.source_timestamp_raw,
                       o.source_timezone, o.source_offset,
                       o.timestamp_normalization_version,
                       o.observed_at_utc, o.original_unit, o.canonical_unit,
                       o.conversion_id, o.conversion_version,
                       o.source_record_digest, o.mapping_authority_digest
                FROM telemetry.analysis_result_artifacts a
                JOIN telemetry.analysis_windows w
                  ON w.resource_scope_id = a.resource_scope_id
                 AND w.tenant_scope_id = a.tenant_scope_id
                 AND w.workspace_id = a.workspace_id
                 AND w.facility_id = a.facility_id
                 AND w.id = a.analysis_window_id
                 AND w.status = 'completed'
                 AND w.result_digest = a.payload_digest
                JOIN telemetry.analysis_window_observations link
                  ON link.resource_scope_id = a.resource_scope_id
                 AND link.tenant_scope_id = a.tenant_scope_id
                 AND link.workspace_id = a.workspace_id
                 AND link.facility_id = a.facility_id
                 AND link.analysis_window_id = a.analysis_window_id
                JOIN telemetry.normalized_observations o
                  ON o.resource_scope_id = link.resource_scope_id
                 AND o.tenant_scope_id = link.tenant_scope_id
                 AND o.workspace_id = link.workspace_id
                 AND o.facility_id = link.facility_id
                 AND o.id = link.observation_id
                WHERE a.resource_scope_id = %s AND a.tenant_scope_id = %s
                  AND a.workspace_id = %s AND a.facility_id = %s
                  AND a.connection_id = %s::UUID
                  AND a.source_ingestion_run_id = %s::UUID
                  AND a.system_id = %s
                  AND a.asset_id IS NOT DISTINCT FROM %s
                  AND a.id = %s::UUID
                ORDER BY o.id
                LIMIT 5001
                """,
                (
                    *_scope_parameters(scope),
                    connection_uuid,
                    run_uuid,
                    system,
                    asset,
                    result_uuid,
                ),
            )
            rows = [_row_dict(cursor, row) or {} for row in cursor.fetchall()]
        if len(rows) > 5_000:
            raise TelemetryRepositoryError(
                "telemetry_analysis_result_lineage_limit_exceeded"
            )
        return rows

    def load_connection_health_inputs(
        self,
        scope: TelemetryRepositoryScope,
        *,
        connection_id: str,
    ) -> dict[str, Any] | None:
        """Load only server-persisted facts used by deterministic health policy."""
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT c.id AS connection_id, c.enabled, c.lifecycle_status,
                       c.polling_interval_seconds, c.last_telemetry_at,
                       c.last_healthy_at,
                       COUNT(DISTINCT s.id)::INTEGER AS discovered_signal_count,
                       COUNT(DISTINCT s.id) FILTER (WHERE s.mapping_status = 'mapped')::INTEGER
                           AS mapped_signal_count,
                       COUNT(DISTINCT s.id) FILTER (WHERE s.mapping_status = 'mapped'
                           AND s.quality_state = 'good')::INTEGER AS healthy_signal_count,
                       COUNT(DISTINCT s.id) FILTER (WHERE s.mapping_status = 'mapped'
                           AND s.quality_state = 'stale')::INTEGER AS stale_signal_count,
                       MAX(cp.updated_at) FILTER (WHERE cp.mode = 'incremental')
                           AS checkpoint_updated_at,
                       h.reachability_state, h.authentication_state,
                       h.details AS previous_details
                FROM telemetry.data_connections c
                LEFT JOIN telemetry.external_signals s
                  ON s.resource_scope_id = c.resource_scope_id
                 AND s.tenant_scope_id = c.tenant_scope_id
                 AND s.workspace_id = c.workspace_id
                 AND s.facility_id = c.facility_id
                 AND s.connection_id = c.id
                LEFT JOIN telemetry.connection_checkpoints cp
                  ON cp.resource_scope_id = c.resource_scope_id
                 AND cp.tenant_scope_id = c.tenant_scope_id
                 AND cp.workspace_id = c.workspace_id
                 AND cp.facility_id = c.facility_id
                 AND cp.connection_id = c.id
                LEFT JOIN telemetry.connection_health h
                  ON h.resource_scope_id = c.resource_scope_id
                 AND h.tenant_scope_id = c.tenant_scope_id
                 AND h.workspace_id = c.workspace_id
                 AND h.facility_id = c.facility_id
                 AND h.connection_id = c.id
                WHERE {self._scope_predicate('c')} AND c.id = %s::UUID
                  AND c.archived_at IS NULL
                GROUP BY c.id, h.reachability_state, h.authentication_state,
                         h.details
                """,
                (
                    *_scope_parameters(scope),
                    _require_uuid(connection_id, "telemetry_connection_id_invalid"),
                ),
            )
            return _row_dict(cursor, cursor.fetchone())

    def save_connection_health(
        self,
        scope: TelemetryRepositoryScope,
        *,
        connection_id: str,
        health: Mapping[str, Any],
    ) -> dict[str, Any]:
        connection_id = _require_uuid(connection_id, "telemetry_connection_id_invalid")
        aggregate = ConnectionHealthState(health["aggregate_status"]).value
        facet_names = (
            "reachability",
            "authentication",
            "telemetry_freshness",
            "mapping_completeness",
            "data_quality",
            "worker_checkpoint",
        )
        facets = {
            name: HealthFacetStatus(health[f"{name}_state"]).value
            for name in facet_names
        }
        details = health.get("details") or {}
        if not isinstance(details, Mapping):
            raise ValueError("telemetry_health_details_invalid")
        details_json = _safe_json(
            details,
            code="telemetry_health_details_invalid",
            reject_sensitive=True,
        )
        counts = {
            name: int(health.get(name, 0))
            for name in (
                "discovered_signal_count",
                "mapped_signal_count",
                "healthy_signal_count",
                "stale_signal_count",
            )
        }
        if (
            min(counts.values()) < 0
            or counts["mapped_signal_count"] > counts["discovered_signal_count"]
            or counts["healthy_signal_count"] > counts["mapped_signal_count"]
            or counts["stale_signal_count"] > counts["mapped_signal_count"]
        ):
            raise ValueError("telemetry_health_counts_invalid")
        evaluated_at = health["last_evaluated_at"]
        last_healthy_at = health.get("last_healthy_at")
        if evaluated_at.tzinfo is None or evaluated_at.utcoffset() is None or (
            last_healthy_at is not None
            and (last_healthy_at.tzinfo is None or last_healthy_at.utcoffset() is None)
        ):
            raise ValueError("telemetry_health_timestamp_invalid")
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""
                INSERT INTO telemetry.connection_health (
                    tenant_scope_id, workspace_id, resource_scope_id, facility_id,
                    connection_id, aggregate_status, reachability_state,
                    authentication_state, telemetry_freshness_state,
                    mapping_completeness_state, data_quality_state,
                    worker_checkpoint_state, discovered_signal_count,
                    mapped_signal_count, healthy_signal_count, stale_signal_count,
                    last_healthy_at, last_evaluated_at, details
                )
                SELECT c.tenant_scope_id, c.workspace_id, c.resource_scope_id,
                    c.facility_id, c.id, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s::JSONB
                FROM telemetry.data_connections c
                WHERE {self._scope_predicate('c')} AND c.id = %s::UUID
                  AND c.archived_at IS NULL
                ON CONFLICT (resource_scope_id, connection_id) DO UPDATE SET
                    aggregate_status = EXCLUDED.aggregate_status,
                    reachability_state = EXCLUDED.reachability_state,
                    authentication_state = EXCLUDED.authentication_state,
                    telemetry_freshness_state = EXCLUDED.telemetry_freshness_state,
                    mapping_completeness_state = EXCLUDED.mapping_completeness_state,
                    data_quality_state = EXCLUDED.data_quality_state,
                    worker_checkpoint_state = EXCLUDED.worker_checkpoint_state,
                    discovered_signal_count = EXCLUDED.discovered_signal_count,
                    mapped_signal_count = EXCLUDED.mapped_signal_count,
                    healthy_signal_count = EXCLUDED.healthy_signal_count,
                    stale_signal_count = EXCLUDED.stale_signal_count,
                    last_healthy_at = EXCLUDED.last_healthy_at,
                    last_evaluated_at = EXCLUDED.last_evaluated_at,
                    details = EXCLUDED.details
                RETURNING connection_id, aggregate_status, reachability_state,
                    authentication_state, telemetry_freshness_state,
                    mapping_completeness_state, data_quality_state,
                    worker_checkpoint_state, discovered_signal_count,
                    mapped_signal_count, healthy_signal_count, stale_signal_count,
                    last_healthy_at, last_evaluated_at, details
                """,
                (
                    aggregate,
                    facets["reachability"],
                    facets["authentication"],
                    facets["telemetry_freshness"],
                    facets["mapping_completeness"],
                    facets["data_quality"],
                    facets["worker_checkpoint"],
                    counts["discovered_signal_count"],
                    counts["mapped_signal_count"],
                    counts["healthy_signal_count"],
                    counts["stale_signal_count"],
                    last_healthy_at,
                    evaluated_at,
                    details_json,
                    *_scope_parameters(scope),
                    connection_id,
                ),
            )
            result = _row_dict(cursor, cursor.fetchone())
            if result is None:
                raise TelemetryRepositoryError("telemetry_connection_not_found")
            return result

    def get_connection_health(
        self,
        scope: TelemetryRepositoryScope,
        *,
        connection_id: str,
    ) -> dict[str, Any] | None:
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT h.connection_id, h.aggregate_status,
                    h.reachability_state, h.authentication_state,
                    h.telemetry_freshness_state, h.mapping_completeness_state,
                    h.data_quality_state, h.worker_checkpoint_state,
                    h.discovered_signal_count, h.mapped_signal_count,
                    h.healthy_signal_count, h.stale_signal_count,
                    h.last_healthy_at, h.last_evaluated_at, h.details
                FROM telemetry.data_connections c
                JOIN telemetry.connection_health h
                  ON h.resource_scope_id = c.resource_scope_id
                 AND h.tenant_scope_id = c.tenant_scope_id
                 AND h.workspace_id = c.workspace_id
                 AND h.facility_id = c.facility_id
                 AND h.connection_id = c.id
                WHERE {self._scope_predicate('c')} AND c.id = %s::UUID
                """,
                (
                    *_scope_parameters(scope),
                    _require_uuid(connection_id, "telemetry_connection_id_invalid"),
                ),
            )
            return _row_dict(cursor, cursor.fetchone())

    @staticmethod
    def _insert_audit_event(
        cursor: Any,
        scope: TelemetryRepositoryScope,
        *,
        event_id: str,
        connection_id: str,
        actor_id: str,
        action: str,
        safe_detail: Mapping[str, Any],
        before_digest: str | None = None,
        after_digest: str | None = None,
    ) -> None:
        cursor.execute(
            """
            INSERT INTO telemetry.telemetry_audit_events (
                id, tenant_scope_id, workspace_id, resource_scope_id, facility_id,
                connection_id, actor_id, action, before_digest, after_digest,
                safe_detail
            ) VALUES (
                %s::UUID, %s, %s, %s, %s, %s::UUID, %s, %s, %s, %s,
                %s::JSONB
            )
            """,
            (
                event_id,
                scope.tenant_scope_id,
                scope.workspace_id,
                scope.resource_scope_id,
                scope.facility_id,
                connection_id,
                actor_id,
                action,
                before_digest,
                after_digest,
                _safe_audit_detail(safe_detail),
            ),
        )

    def record_audit_event(
        self,
        scope: TelemetryRepositoryScope,
        *,
        event_id: str,
        connection_id: str,
        actor_id: str,
        action: str,
        safe_detail: Mapping[str, Any],
        before_digest: str | None = None,
        after_digest: str | None = None,
    ) -> None:
        with self._connection() as connection, connection.cursor() as cursor:
            self._insert_audit_event(
                cursor,
                scope,
                event_id=_require_uuid(
                    event_id, "telemetry_audit_event_id_invalid"
                ),
                connection_id=_require_uuid(
                    connection_id, "telemetry_audit_connection_id_invalid"
                ),
                actor_id=_require_identifier(
                    actor_id, "telemetry_audit_actor_required"
                ),
                action=action,
                before_digest=before_digest,
                after_digest=after_digest,
                safe_detail=safe_detail,
            )


def repository_sql_contract() -> dict[str, Sequence[str]]:
    """Expose stable security/locking markers for deployment contract checks."""
    return {
        "scope_columns": (
            "resource_scope_id",
            "tenant_scope_id",
            "workspace_id",
            "facility_id",
        ),
        "public_secret_fields": (),
        "lease_primitives": ("FOR UPDATE SKIP LOCKED", "lease_token"),
        "checkpoint_primitives": ("revision", "ON CONFLICT", "FOR UPDATE"),
    }
