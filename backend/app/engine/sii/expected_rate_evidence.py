"""Timestamped evidence from the existing validated expected-response model.

Sample-lagged models are withheld until timestamp-based lag alignment is supported.
This module does not integrate rates.
"""

from __future__ import annotations

import math
from typing import Any

from app.engine.sii.common import finite_number


def expected_rate_observations(
    rows: list[dict[str, Any]],
    *,
    predictor: str,
    target: str,
    parameters: dict[str, Any],
    timestamp_column: str | None,
) -> list[dict[str, Any]]:
    if not timestamp_column or parameters.get("lag_samples", 0) != 0:
        return []
    slope = finite_number(parameters.get("slope"))
    intercept = finite_number(parameters.get("intercept"))
    if slope is None or intercept is None:
        return []
    observations = []
    for index, row in enumerate(rows):
        x = finite_number(row.get(predictor))
        y = finite_number(row.get(target))
        expected = intercept + slope * x if x is not None else None
        valid = (
            x is not None
            and y is not None
            and expected is not None
            and math.isfinite(expected)
            and not isinstance(row.get(predictor), bool)
            and not isinstance(row.get(target), bool)
            and row.get("valid", True) is True
        )
        observations.append(
            {
                "timestamp": row.get(timestamp_column),
                "observed": y,
                "expected": expected
                if expected is not None and math.isfinite(expected)
                else None,
                "valid": valid,
                "source_row_index": index,
                "predictor_value": x,
            }
        )
    return observations
