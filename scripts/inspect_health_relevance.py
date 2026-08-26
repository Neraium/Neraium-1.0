#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Sequence


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.auth_store import normalize_role  # noqa: E402
from app.services.health_relevance import (  # noqa: E402
    HealthRelevanceInputError,
    HealthRelevanceNotFoundError,
    inspect_health_relevance,
)
from app.services.validated_outcomes import (  # noqa: E402
    HealthRelevanceAccessError,
    authorize_internal_access,
)
from app.services.workspace_authorization import (  # noqa: E402
    WorkspaceAuthorizationError,
    resolve_workspace_context,
)


_OPAQUE_ERROR = "Health Relevance state not found."


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect one exact-scope internal Health Relevance version (read only)."
    )
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--facility-id", required=True)
    parser.add_argument("--system-id", required=True)
    parser.add_argument(
        "--subject-type",
        required=True,
        choices=("signal", "relationship", "asset_equipment", "subsystem"),
    )
    parser.add_argument("--subject-id", required=True)
    parser.add_argument("--subject-mapping-version", required=True)
    parser.add_argument("--context-fingerprint", required=True)
    parser.add_argument("--compatibility-epoch", required=True)
    parser.add_argument(
        "--method",
        required=True,
        choices=("bayesian_shrinkage_v1", "outcome_conditioned_information_v1"),
    )
    parser.add_argument(
        "--as-of",
        help="Optional timezone-aware ISO-8601 timestamp for read-time freshness inspection.",
    )
    return parser


def _parse_as_of(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise HealthRelevanceInputError("as_of_invalid") from error
    if parsed.tzinfo is None:
        raise HealthRelevanceInputError("as_of_timezone_required")
    return parsed.astimezone(UTC)


def inspect_from_args(args: argparse.Namespace) -> dict[str, object]:
    """Resolve the configured service identity and perform one exact read."""

    if not os.getenv("NERAIUM_API_TOKEN", "").strip():
        raise HealthRelevanceNotFoundError(_OPAQUE_ERROR)
    workspace = resolve_workspace_context(
        subject="service-token",
        requested_workspace_id=args.workspace_id,
        auth_source="service_token",
    )
    access = authorize_internal_access(
        scope=workspace.dataset_scope,
        facility_id=args.facility_id,
        system_id=args.system_id,
        actor="service-token",
        auth_source="service_token",
        role=normalize_role(os.getenv("NERAIUM_API_TOKEN_ROLE"), "admin"),
        workspace_authorized=True,
    )
    return inspect_health_relevance(
        access,
        subject_type=args.subject_type,
        subject_id=args.subject_id,
        subject_mapping_version=args.subject_mapping_version,
        context_fingerprint=args.context_fingerprint,
        compatibility_epoch=args.compatibility_epoch,
        method_class=args.method,
        as_of=_parse_as_of(args.as_of),
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = inspect_from_args(args)
    except (
        HealthRelevanceAccessError,
        HealthRelevanceInputError,
        HealthRelevanceNotFoundError,
        ValueError,
        WorkspaceAuthorizationError,
    ):
        print(json.dumps({"error": _OPAQUE_ERROR}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
