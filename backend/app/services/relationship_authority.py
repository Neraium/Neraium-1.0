"""Prospective qualification boundary; analytical assessments remain producer-owned."""
from app.services.relationship_evidence_binding import REGISTRY, resolve
from app.services.resource_relationship_binding import ownership

VERSION = "relationship-authority.v1"
VERSION_FIELD = "relationship_authority_version"
FINDINGS = "relationship_findings"


def enabled(result):
    return (result.get("sii_result") or result).get(VERSION_FIELD) == VERSION


def registry_for(result):
    return (result.get("sii_result") or result).get(REGISTRY) or {}


def group_persistence():
    return {
        "status": "not_assessed", "persistent": False, "scope": "group",
        "summary": "Persistence is qualified separately for each exact relationship assessment.",
    }


def relationship_persistence(relationship, registry):
    record = resolve(relationship, registry, authorized_scope=registry.get("scope"),
                     require_temporal=True)
    persistent = bool(record is not None
                      and record["qualification"].get("eligible") is True
                      and record["temporal"]["assessment"].get("persistent_relationship_change") is True)
    summary = ("The exact relationship assessment establishes temporal persistence."
               if persistent else "The exact relationship assessment does not establish temporal persistence.")
    return {
        "status": "persistent" if persistent else "not_assessed" if record is None else "not_established",
        "persistent": persistent, "scope": "relationship", "summary": summary,
        "reasons": [summary], **(ownership(relationship) or {}),
    }
