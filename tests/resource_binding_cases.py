"""Controlled producer assessments; no production temporal continuation."""
from copy import deepcopy
from functools import lru_cache
from datetime import datetime, timezone

from app.services.relationship_evidence_binding import SOURCE, source_evidence, finalize
from app.services.resource_relationship_binding import LINEAGE, ownership, finalize_resources
from test_relationship_temporal_persistence import edge, analyze


@lru_cache(maxsize=4)
def assessment(history=8, columns=('flow', 'load')):
    state = None
    for day in range(1, history + 1):
        raw = edge(day, columns=list(columns))
        start = datetime.fromtimestamp((day - history) * 86400, timezone.utc).isoformat()
        end = datetime.fromtimestamp((day - history) * 86400 + 21600, timezone.utc).isoformat()
        raw['time_window'].update(current_start=start, current_end=end)
        raw['source_rows'] = [{'window': 'recent_end', 'source_row': day * 48,
                              'timestamp': end}]
        raw[SOURCE] = source_evidence(raw, columns=columns,
            baseline_rows=[{columns[0]: 1, columns[1]: 2, 't': -86400}],
            current_rows=[{columns[0]: 2, columns[1]: 1, 't': (day-history)*86400}],
            timestamp_column='t')
        graph = analyze(raw, state)
        state = graph['relationship_persistence_state']
    model = {'relationship_graph': {'edges': [raw]}, 'top_relationship_changes': [deepcopy(raw)]}
    registry = finalize(model, graph, scope='resource-test')
    return model['top_relationship_changes'][0], registry


def bind_fixture(finding, expected):
    assertion, registry = assessment()
    finding.update(ownership(assertion))
    for resource in expected['expected_values']:
        resource[LINEAGE] = assertion['relationship_source_ref']
    finalize_resources(expected, registry, authorized_scope=registry['scope'])
    return registry
