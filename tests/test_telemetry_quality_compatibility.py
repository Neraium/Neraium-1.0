"""HEAD admission outcomes are fixed independently of source-quality provenance."""
from dataclasses import replace
import json

import pytest

from app.connectors.https_telemetry import _HttpsConfig, _observation
from app.services.telemetry_ingestion import stable_source_record_digest, validate_source_representation
from test_https_telemetry_connector import configuration
from test_telemetry_ingestion import mapping, scope, prepare, NOW

# These outcomes were reproduced against d79cdb6 before correcting Phase 2.
@pytest.mark.parametrize('payload,source_quality,admission,eligible', [
    ({}, None, 'good', True),
    ({'quality': None}, None, 'good', True),
    ({'quality': 'GOOD'}, 'good', 'good', True),
    ({'quality': 'uncertain'}, 'uncertain', 'invalid_value', False),
    ({'quality': 'suspect'}, 'uncertain', 'invalid_value', False),
    ({'quality': 'bad'}, 'bad', 'invalid_value', False),
    ({'quality': 'invalid'}, 'bad', 'invalid_value', False),
    ({'quality': 'unknown'}, 'unknown', 'format_invalid', False),
    ({'quality': []}, 'unknown', 'good', True),
    ({'quality': {}}, 'unknown', 'good', True),
    ({'quality': ['good']}, 'unknown', 'good', True),
    ({'quality': {'good': ''}}, 'unknown', 'good', True),
    ({'quality': ['bad']}, 'unknown', 'invalid_value', False),
    ({'quality': {'status': 'bad'}}, 'unknown', 'format_invalid', False),
    ({'quality': ''}, 'unknown', 'good', True),
    ({'quality': 0}, 'good', 'good', True),
])
def test_https_source_quality_is_independent_of_legacy_admission(
    scope, mapping, payload, source_quality, admission, eligible,
):
    observation = _observation({
        'tag': {'id': mapping.external_tag_id, 'name': 'Temperature'},
        'observed_at': '2026-08-25T07:00:00-04:00', 'value': 77.0, 'unit': 'degF', **payload,
    }, _HttpsConfig.from_mapping(configuration()))
    native = payload.get('quality')
    assert observation.native_quality == native
    assert observation.reported_quality == (None if native is None else str(native))
    page = prepare(scope=scope, mapping=mapping, observations=(observation,))
    record = (page.observations or page.rejections)[0]
    representation = validate_source_representation(record.source_representation)
    assert representation['quality_state'] == source_quality
    assert representation['reported_quality'] == (
        {'type': 'null', 'value': None} if native is None
        else {'type': 'str', 'value': str(native)}
    )
    encoded = representation['native_quality']
    if isinstance(native, (list, dict)):
        assert encoded['type'] == 'json'
        assert json.loads(encoded['value']) == native
    elif native is None:
        assert encoded == {'type': 'null', 'value': None}
    elif isinstance(native, str):
        assert encoded == {'type': 'str', 'value': native}
    else:
        assert encoded == {'type': 'int', 'value': str(native)}
    assert record.quality_state.value == admission
    assert record.analysis_eligible is eligible
    assert page.accepted_count == int(eligible)
    assert page.rejected_count == int(not eligible)
    if eligible:
        assert record.normalized_value == 25.0
    # Neither richer native quality nor acquisition/retry clocks enter v1 identity.
    legacy = replace(observation, native_quality=None)
    retry = replace(observation, acquired_at_utc=NOW, metadata={'worker_id': 'retry-worker'})
    assert record.source_record_digest == stable_source_record_digest(legacy)
    assert stable_source_record_digest(retry) == stable_source_record_digest(legacy)


@pytest.mark.parametrize('encoded', ['null', '"GOOD"', '{broken', '{"authorization":"secret"}'])
def test_structured_quality_provenance_validation_remains_closed(scope, mapping, encoded):
    observation = _observation({
        'tag': {'id': mapping.external_tag_id}, 'observed_at': NOW.isoformat(),
        'value': 77.0, 'unit': 'degF', 'quality': [],
    }, _HttpsConfig.from_mapping(configuration()))
    page = prepare(scope=scope, mapping=mapping, observations=(observation,))
    representation = validate_source_representation(page.observations[0].source_representation)
    representation['native_quality'] = {'type': 'json', 'value': encoded}
    with pytest.raises(ValueError, match='source_representation_scalar_invalid'):
        validate_source_representation(representation)
