"""Bounded, read-only episode evidence, independent of continuous persistence."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import math
from typing import Any

from app.engine.relationship_change import MINIMUM_DATA_QUALITY, MINIMUM_EDGE_CONFIDENCE

RECURRENCE_RULES = {
    "minimum_episodes": 3,
    "minimum_support_per_episode": 2,
    "minimum_displacement": 0.15,
    "maximum_age_days": 30,
    "maximum_observations": 256,
}


def _time(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def relationship_recurrence_evidence(
    edge: dict[str, Any], previous: dict[str, Any] | None, *, identity: dict[str, Any],
    minimum_confidence: float = MINIMUM_EDGE_CONFIDENCE,
    minimum_quality: float = MINIMUM_DATA_QUALITY,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Count completed episodes, never individual deltas or sample counts.

    Non-overlapping windows are required. Only acceptable neutral observations
    close/separate episodes. Unknown windows break consecutive support, but do
    not establish a return. A supported opposite run vetoes the whole horizon,
    even before it closes. State is caller-carried, detached and identity scoped.
    """
    state = {"version": 1, "identity": deepcopy(identity), "observations": [],
             "requires_initial_return": False, "overflow_until": None}
    if previous and previous.get("version") == 1 and previous.get("identity") == identity:
        state = deepcopy(previous)
    evidence = {
        "evidence_model": "relationship_recurrence_v1",
        "status": "limited", "supported": False, "direction": 0,
        "episode_count": 0, "opposite_direction_veto": False,
        "identity": deepcopy(identity), "policy": dict(RECURRENCE_RULES),
        "gates": {"minimum_edge_confidence": minimum_confidence,
                  "minimum_data_quality_factor": minimum_quality},
        "episodes": [], "evaluated_at": None, "reason": "invalid_or_nonchronological_window",
    }

    def acceptable(item):
        return bool(item["eligible"] and item["acceptable"]
                    and math.isfinite(item["signed_correlation_delta"])
                    and item["edge_confidence"] >= minimum_confidence
                    and item["data_quality_factor"] >= minimum_quality)

    window = edge.get("time_window") or {}
    observation = {
        "time_window": deepcopy(window), "source_rows": deepcopy(edge.get("source_rows", [])),
        "source_dataset_id": edge.get("source_dataset_id"),
        "signed_correlation_delta": edge["signed_correlation_delta"],
        "edge_confidence": edge["edge_confidence"], "data_quality_factor": edge["data_quality_factor"],
        "eligible": edge["eligible"], "acceptable": True,
        "sensor_health_context": deepcopy(edge.get("sensor_health_context", [])),
    }
    observation["acceptable"] = acceptable(observation)
    try:
        start, end = _time(window.get("current_start")), _time(window.get("current_end"))
        if start >= end:
            return evidence, state
        observation["observed_at"] = end.isoformat()
        observations = state["observations"]
        # Validate retained chronology too; retried observations must be identical.
        last_end = None
        for item in observations:
            item_start = _time(item["time_window"]["current_start"])
            item_end = _time(item["observed_at"])
            if item_start >= item_end or (last_end is not None and item_start < last_end):
                return evidence, state
            last_end = item_end
        if observations and end == last_end:
            if observation != observations[-1]:
                return evidence, state
        elif last_end is not None and start < last_end:
            return evidence, state
        else:
            observations = [*observations, observation]
        cutoff = end - timedelta(days=RECURRENCE_RULES["maximum_age_days"])
        retained = [item for item in observations if _time(item["time_window"]["current_start"]) >= cutoff]
        if len(retained) != len(observations):
            state["requires_initial_return"] = True
        cap = RECURRENCE_RULES["maximum_observations"]
        if len(retained) > cap:
            # Never silently drop a veto while it could still be in the horizon.
            state["overflow_until"] = (
                _time(retained[-cap-1]["observed_at"]) + timedelta(days=RECURRENCE_RULES["maximum_age_days"])
            ).isoformat()
            state["requires_initial_return"] = True
        state["observations"] = retained[-cap:]
        evidence["evaluated_at"] = end.isoformat()
        if state["overflow_until"] and end <= _time(state["overflow_until"]):
            evidence["reason"] = "observation_capacity_exceeded"
            return evidence, state
        state["overflow_until"] = None
    except (ValueError, TypeError, KeyError):
        return evidence, state

    episodes = []
    supported_directions = set()
    armed = not state["requires_initial_return"]
    opening_return = None
    support = []
    directions = set()
    run_direction, run_count, maximum_run = 0, 0, 0
    for item in state["observations"]:
        valid = acceptable(item)
        delta = item["signed_correlation_delta"]
        neutral = valid and abs(delta) < RECURRENCE_RULES["minimum_displacement"]
        direction = (1 if delta > 0 else -1) if valid and not neutral else 0
        if neutral:
            if armed and len(directions) == 1 and maximum_run >= RECURRENCE_RULES["minimum_support_per_episode"]:
                episodes.append({
                    "direction": next(iter(directions)), "support_count": len(support),
                    "maximum_consecutive_support": maximum_run,
                    "started_at": support[0]["time_window"]["current_start"],
                    "last_supported_at": support[-1]["observed_at"],
                    "closed_at": item["observed_at"],
                    "supporting_windows": deepcopy(support),
                    "opening_return": deepcopy(opening_return), "closing_return": deepcopy(item),
                })
            armed, opening_return = True, item
            support, directions = [], set()
            run_direction, run_count, maximum_run = 0, 0, 0
        elif direction:
            directions.add(direction)
            support.append(item)
            run_count = run_count + 1 if run_direction == direction else 1
            run_direction = direction
            maximum_run = max(maximum_run, run_count)
            if run_count >= RECURRENCE_RULES["minimum_support_per_episode"]:
                supported_directions.add(direction)
        else:
            run_direction, run_count = 0, 0

    veto = len(supported_directions) > 1
    direction = next(iter(supported_directions)) if len(supported_directions) == 1 else 0
    supported = bool(len(episodes) >= RECURRENCE_RULES["minimum_episodes"] and direction
                     and not veto and observation["acceptable"])
    evidence.update({
        "status": "supported" if supported else "unconfirmed", "supported": supported,
        "direction": direction, "episode_count": len(episodes), "episodes": episodes,
        "opposite_direction_veto": veto,
        "reason": "opposite_direction_episode" if veto else None if supported else "insufficient_evidence",
    })
    return evidence, state
