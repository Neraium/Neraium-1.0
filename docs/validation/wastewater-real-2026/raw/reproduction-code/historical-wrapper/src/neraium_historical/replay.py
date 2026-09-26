from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from .config import ReplayConfig
from .csv_loader import LoadedCsv
from .engine_adapter import EngineAdapter
from .timeparse import validate_ordered_unique


@dataclass(frozen=True)
class Evaluation:
    index: int
    comparison_start: str
    comparison_end: str
    result: dict[str, Any]
    source_row_start: int = 0
    source_row_end: int = 0


def replay(dataset: LoadedCsv, config: ReplayConfig, engine: EngineAdapter, *,
           relationship_persistence_state: dict[str, Any] | None = None,
           relationship_recurrence_state: dict[str, Any] | None = None) -> list[Evaluation]:
    """Carry engine-owned state in chronological order, scoped to this replay."""
    config.validate(dataset.numeric_columns)
    validate_ordered_unique(dataset.rows, dataset.timestamp_column)
    minimum = config.reference_rows + config.comparison_rows
    if len(dataset.rows) < minimum:
        raise ValueError(
            f"CSV needs at least {minimum} rows for this replay configuration; found {len(dataset.rows)}"
        )
    count = 1 + (len(dataset.rows) - minimum) // config.step_rows
    if count > 1000:
        raise ValueError(f'replay exceeds 1000 evaluation resource limit; requested {count}')
    reference = dataset.rows[: config.reference_rows]
    evaluations: list[Evaluation] = []
    start = config.reference_rows
    index = 0
    while start + config.comparison_rows <= len(dataset.rows):
        comparison = dataset.rows[start : start + config.comparison_rows]
        try:
            result = engine.evaluate_pair(
                columns=dataset.columns,
                reference_rows=reference,
                comparison_rows=comparison,
                numeric_profiles=dataset.numeric_profiles,
                timestamp_column=dataset.timestamp_column,
                signal_units=config.signal_units,
                relationship_persistence_state=deepcopy(relationship_persistence_state),
                relationship_recurrence_state=deepcopy(relationship_recurrence_state),
            )
        except Exception as exc:
            raise RuntimeError(f'Engine evaluation {index} failed (data rows {start + 1}–{start + len(comparison)}): {exc}') from exc
        relationship_persistence_state = result['relationship_graph']['relationship_persistence_state']
        relationship_recurrence_state = result['relationship_graph']['relationship_recurrence_state']
        evaluations.append(
            Evaluation(
                index=index,
                comparison_start=str(comparison[0][dataset.timestamp_column]),
                comparison_end=str(comparison[-1][dataset.timestamp_column]),
                result=result,
                source_row_start=start + 1,
                source_row_end=start + len(comparison),
            )
        )
        index += 1
        start += config.step_rows
    return evaluations
