from collections import OrderedDict
from typing import Any


CATEGORY_KEYWORDS = OrderedDict(
    [
        ("thermal", ("temp", "temperature", "cool", "heat", "chiller", "boiler")),
        ("moisture", ("humidity", "rh", "moisture", "dewpoint")),
        ("flow", ("airflow", "flow", "fan", "cfm", "vent", "pressure")),
        ("chemical", ("co2", "ph", "ec", "conductivity", "ppm", "gas")),
        ("energy", ("power", "voltage", "current", "kw", "kwh", "amp")),
        ("timing", ("schedule", "runtime", "cycle", "duration", "latency")),
        ("network", ("sensor", "device", "gateway", "node", "signal", "packet")),
        ("location", ("room", "zone", "line", "bay", "cell", "station")),
    ]
)

CATEGORIES = [*CATEGORY_KEYWORDS.keys(), "unknown"]


def map_schema_columns(columns: list[str]) -> dict[str, Any]:
    categories = {category: [] for category in CATEGORIES}

    for column in columns:
        category = category_for_column(column)
        categories[category].append(column)

    mapped_column_count = sum(
        len(mapped_columns)
        for category, mapped_columns in categories.items()
        if category != "unknown"
    )
    unknown_column_count = len(categories["unknown"])
    coverage_percent = round((mapped_column_count / len(columns) * 100) if columns else 0, 4)

    warnings = []
    if unknown_column_count:
        warnings.append("Some columns could not be mapped to a generic signal category.")

    return {
        "categories": categories,
        "mapped_column_count": mapped_column_count,
        "unknown_column_count": unknown_column_count,
        "coverage_percent": coverage_percent,
        "warnings": warnings,
        "mapping_version": "schema-generic-v1",
    }


def category_for_column(column: str) -> str:
    normalized = normalize_column(column)
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword in normalized for keyword in keywords):
            return category
    return "unknown"


def normalize_column(column: str) -> str:
    return column.strip().lower().replace(" ", "_").replace("-", "_")
