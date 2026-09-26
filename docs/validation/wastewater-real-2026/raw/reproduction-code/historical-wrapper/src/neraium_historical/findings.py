from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .replay import Evaluation


def _identity(insight: dict[str, Any]) -> str:
    """Conservative presentation identity; never infer relationships or classification."""
    classification = insight.get('classification') or {}
    relationships = insight.get('contributing_relationships') or insight.get('affected_relationships') or []
    relationship_keys = [
        {k: rel[k] for k in ('columns', 'relationship_type', 'change_type') if k in rel}
        if isinstance(rel, dict) and rel.get('columns') else rel
        for rel in relationships
    ]
    identity = {
        'type': classification.get('type'), 'title': insight.get('title'),
        'systems': sorted(insight.get('affected_systems') or ([insight['system']] if insight.get('system') else [])),
        'tags': sorted(insight.get('source_tags') or []),
        'relationships': sorted(relationship_keys, key=lambda value: json.dumps(value, sort_keys=True)),
        'prior': insight.get('relationship_prior_id'),
    }
    if not any(identity.values()):
        identity['fallback'] = insight.get('id') or insight
    return json.dumps(identity, sort_keys=True, separators=(',', ':'))


@dataclass
class FindingEpisode:
    key: str
    first_observed: str
    last_observed: str
    evaluations: int = 0
    insight: dict[str, Any] = field(default_factory=dict)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    observations: list[dict[str, Any]] = field(default_factory=list)


def consolidate(evaluations: list[Evaluation]) -> list[FindingEpisode]:
    episodes = []
    active: dict[str, FindingEpisode] = {}
    previous_index = None
    for evaluation in evaluations:
        if previous_index is None or evaluation.index != previous_index + 1:
            active = {}
        current = {}
        analysis = evaluation.result['analysis_result']
        for insight in analysis['insights']:
            key = _identity(insight)
            episode = current.get(key) or active.get(key)
            if episode is None:
                episode = FindingEpisode(key, evaluation.comparison_end, evaluation.comparison_end, insight=insight)
                episodes.append(episode)
            if key not in current:
                episode.evaluations += 1
            current[key] = episode
            episode.last_observed = evaluation.comparison_end
            # IDs and evidence are scoped to the evaluation; preserve every observation.
            observation = {'evaluation_index': evaluation.index,
                           'comparison_start': evaluation.comparison_start, 'comparison_end': evaluation.comparison_end,
                           'insight': insight, 'evidence_refs': insight.get('evidence_refs', [])}
            episode.observations.append(observation)
            for ref in observation['evidence_refs']:
                episode.evidence.append({'evaluation_index': evaluation.index, 'evidence_ref': ref,
                                         'comparison_start': evaluation.comparison_start,
                                         'comparison_end': evaluation.comparison_end,
                                         'item': analysis['evidence_index'][ref]})
        active = current
        previous_index = evaluation.index
    return episodes
