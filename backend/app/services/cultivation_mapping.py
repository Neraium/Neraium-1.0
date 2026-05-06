from collections import OrderedDict
from typing import Any

CATEGORY_KEYWORDS = OrderedDict(
    [
        ("temperature", ("canopy_temp", "temperature", "temp")),
        ("humidity", ("relative_humidity", "humidity", "rh")),
        ("HVAC", ("cooling", "heating", "hvac", "ac")),
        ("airflow", ("airflow", "fan", "cfm", "vent")),
        ("irrigation", ("irrigation", "fertigation", "water", "pump", "ec", "ph")),
        ("lighting", ("light", "ppfd", "par", "dli", "lux")),
        ("CO2", ("carbon_dioxide", "co2")),
        ("sensor network", ("sensor", "device", "gateway", "node")),
    ]
)

CATEGORIES = [
    "temperature",
    "humidity",
    "HVAC",
    "airflow",
    "irrigation",
    "lighting",
    "CO2",
    "sensor network",
    "unknown",
]


def map_cultivation_columns(columns: list[str]) -> dict[str, Any]:
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
    coverage_percent = round(
        (mapped_column_count / len(columns) * 100) if columns else 0,
        4,
    )
    warnings = []
    if unknown_column_count:
        warnings.append("Some columns could not be mapped to a cultivation system category.")

    return {
        "categories": categories,
        "mapped_column_count": mapped_column_count,
        "unknown_column_count": unknown_column_count,
        "coverage_percent": coverage_percent,
        "warnings": warnings,
    }


def category_for_column(column: str) -> str:
    normalized = normalize_column(column)
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword in normalized for keyword in keywords):
            return category
    return "unknown"


def normalize_column(column: str) -> str:
    return column.strip().lower().replace(" ", "_").replace("-", "_")
