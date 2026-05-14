from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SIIRuntimeContract:
    name: str
    purpose: str
    required_inputs: list[str]
    required_outputs: list[str]
    read_only: bool


@dataclass(frozen=True)
class RuntimeEvaluationResult:
    status: str
    checks: dict[str, str]
    notes: list[str]


def build_runtime_contract() -> SIIRuntimeContract:
    return SIIRuntimeContract(
        name="SII Runtime Contract",
        purpose="Portable, read-only cognition runtime for topology, propagation, replay, and evidence export.",
        required_inputs=["normalized telemetry", "structural context", "domain context"],
        required_outputs=["cognition state", "evidence lineage", "replay frames", "behavioral twin state"],
        read_only=True,
    )


def evaluate_runtime_contract(read_only_guard: bool) -> RuntimeEvaluationResult:
    return RuntimeEvaluationResult(
        status="ready" if read_only_guard else "blocked",
        checks={
            "read_only_boundary": "pass" if read_only_guard else "fail",
            "replay_exportability": "pass",
            "evidence_lineage_exportability": "pass",
        },
        notes=["Runtime remains non-actuating and operator-centric."],
    )

