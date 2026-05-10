from app.engine.schemas import RESULT_ELEVATED, RESULT_NEEDS_REVIEW, RESULT_NORMAL


def determine_overall_result(signals: list[dict], limitations: list[str]) -> str:
    if any(signal["level"] == "elevated" for signal in signals):
        return RESULT_ELEVATED
    if signals:
        return RESULT_NEEDS_REVIEW
    if has_material_limitations(limitations):
        return RESULT_NEEDS_REVIEW
    return RESULT_NORMAL


def has_material_limitations(limitations: list[str]) -> bool:
    material_markers = (
        "not enough rows",
        "not ready",
        "missing values",
        "timestamp coverage is missing",
        "timestamp coverage could not be parsed",
        "data quality warnings are present",
    )
    return any(
        any(marker in str(limitation).lower() for marker in material_markers)
        for limitation in limitations
    )


def build_summary(overall_result: str, signals: list[dict], limitations: list[str]) -> str:
    if overall_result == RESULT_NORMAL:
        return (
            "Neraium SII v1 reviewed the uploaded cultivation data as system behavior. "
            "The engine did not find corroborated baseline movement or relationship "
            "changes requiring operator review."
        )
    if overall_result == RESULT_ELEVATED:
        return (
            "Neraium SII v1 found elevated system behavior changes across the uploaded "
            "cultivation data. Review the grouped evidence, persistence notes, and "
            "operator checks before using this file for operational decisions."
        )
    if signals:
        return (
            "Neraium SII v1 found system behavior signals that should be checked "
            "against facility context and operator logs."
        )
    if limitations:
        return (
            "Neraium SII v1 was limited by the available cultivation data. Review "
            "the listed limitations before relying on this upload."
        )
    return "The engine pass completed with no additional findings."


def base_limitations() -> list[str]:
    return [
        "Neraium SII v1 uses only the uploaded CSV profile, cultivation mapping, baseline comparison, and paired numeric relationships.",
        "It does not forecast crop stress, equipment failure, yield impact, or root cause.",
        "No data is stored permanently and no AI or LLM analysis is used.",
    ]
