"""Prospective current processing and immutable historical compatibility."""
import json
from pathlib import Path
from app.services import aletheia_governance as legacy
from app.services.sii_intelligence import build_sample_intelligence, build_upload_intelligence
from test_complete_upload_semantics import RETAINED


def test_sample_has_no_legacy_admission(tmp_path, monkeypatch):
    monkeypatch.setattr(legacy, 'EVP_LOG_PATH', tmp_path / 'evp.jsonl')
    result = build_sample_intelligence()
    assert 'aletheia_gate' not in result
    assert not legacy.EVP_LOG_PATH.exists()
    assert result['core_sii_outputs']


def test_upload_builder_preserves_analytical_candidate(tmp_path, monkeypatch):
    monkeypatch.setattr(legacy, 'EVP_LOG_PATH', tmp_path / 'evp.jsonl')
    from app.services import sii_intelligence
    captured = []
    def obsolete_gate(candidate):
        captured.append(candidate)
        return {'gate_outcome': 'NO_PASS'}
    monkeypatch.setattr(sii_intelligence, 'govern_candidate', obsolete_gate, raising=False)
    result = build_upload_intelligence(filename='test.csv', row_count=0,
        data_quality={}, baseline_analysis={}, engine_result={}, driver_attribution={},
        operator_report={}, timestamp_profile={})
    assert 'aletheia_gate' not in result
    assert not captured
    assert not legacy.EVP_LOG_PATH.exists()
    assert result['core_sii_outputs']


def test_historical_reader_preserves_versions_and_bytes(tmp_path, monkeypatch):
    files = list((RETAINED.parent / 'complete-upload-repair').rglob('evp_records.jsonl'))
    assert files
    records = [json.loads(line) for p in files for line in p.read_text().splitlines() if line.strip()]
    assert any('content_identity' in r for r in records)
    assert any('content_identity' not in r for r in records)
    path = tmp_path / 'evp.jsonl'
    raw = ''.join(json.dumps(r) + '\n' for r in records).encode()
    path.write_bytes(raw)
    monkeypatch.setattr(legacy, 'EVP_LOG_PATH', path)
    assert legacy.list_evp_records(limit=1000) == records[::-1][:1000]
    assert path.read_bytes() == raw


def test_current_execution_has_no_legacy_gate_calls():
    for name in ('sii_intelligence', 'upload_pipeline', 'upload_jobs'):
        text = (Path(__file__).parents[1] / f'backend/app/services/{name}.py').read_text()
        assert 'govern_candidate' not in text
        assert 'aletheia_gate' not in text
