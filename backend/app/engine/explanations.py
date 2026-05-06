from app.engine.schemas import RESULT_ELEVATED, RESULT_NEEDS_REVIEW, RESULT_NORMAL


def determine_overall_result(signals: list[dict], limitations: list[str]) -> str:
    if any(signal["level"] == "elevated" for signal in signals):
        return RESULT_ELEVATED
    if signals or limitations:
        return RESULT_NEEDS_REVIEW
    return RESULT_NORMAL


def build_summary(overall_result: str, signals: list[dict], limitations: list[str]) -> str:
    if overall_result == RESULT_NORMAL:
        return (
            "The uploaded cultivation data appears usable and the first engine pass "
            "did not flag baseline drift or relationship changes requiring review."
        )
    if overall_result == RESULT_ELEVATED:
        return (
            "The uploaded cultivation data contains elevated review signals from "
            "baseline or relationship comparison. Review the evidence before using "
            "this file for operational decisions."
        )
    if signals:
        return (
            "The uploaded cultivation data contains review signals that should be "
            "checked against facility context."
        )
    if limitations:
        return (
            "The engine pass was limited by the available data. Review the listed "
            "limitations before relying on this upload."
        )
    return "The engine pass completed with no additional findings."


def base_limitations() -> list[str]:
    return [
        "This deterministic engine pass uses only the uploaded CSV profile, mapping, baseline comparison, and paired numeric relationships.",
        "It does not predict crop stress, equipment failure, yield impact, or root cause.",
        "No data is stored permanently and no AI or LLM analysis is used.",
    ]
