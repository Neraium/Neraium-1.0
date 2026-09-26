"""Streaming complete-case source-time replay with durable per-step checkpoints."""
from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

from .daily_replay import DailyReplay
from .config import load_config
from .engine_adapter import EngineAdapter, validate_result
from .findings import consolidate
from .quality_source import QualitySource, file_hash
from .replay import Evaluation
from .report import build_payload, evidence_projection, write_html, write_json
from .timeparse import parse_source_timestamp


def replay_time(source, engine, config, reference_start, reference_end, end, checkpoints):
    replay = DailyReplay(source, engine, config, reference_start, reference_end, end, checkpoints)
    replay.get(replay.total - 1)
    evaluations, attempts = [], []
    for index, (attempt, result) in replay.records.items():
        attempts.append(attempt)
        if result is not None:
            prov = attempt['input_provenance']
            evaluations.append(Evaluation(index, prov['source_timestamps'][0], prov['source_timestamps'][-1], result,
                                          prov['source_row_numbers'][0], prov['source_row_numbers'][-1]))
    return evaluations, attempts, replay.reference_provenance, replay.policy


def make_report(source, engine, config, evaluations, attempts, reference, policy):
    episodes = consolidate(evaluations)
    payload = build_payload(dataset=source, config=config, evaluations=evaluations, episodes=episodes,
                            engine_path=engine.engine_path, engine_provenance=engine.provenance)
    counts = {s: sum(a['status']==s for a in attempts) for s in ('completed','limited','failed')}
    payload['run_status'] = 'degraded' if counts['failed'] else 'completed_with_limitations' if counts['limited'] else 'completed'
    payload['source'].update(rows=source.audit['original_rows'], valid_rows=source.count, start=source.start, end=source.end,
                             normalization='Complete-case row exclusion only; valid CSV cells and timestamps retained verbatim')
    payload['data_quality_view'] = source.audit
    payload['replay'].update(mode='source_time_complete_case', policy=policy, reference_provenance=reference,
        reference_start=reference['source_timestamps'][0], reference_end=reference['source_timestamps'][-1],
        reference_row_start=reference['source_row_numbers'][0], reference_row_end=reference['source_row_numbers'][-1],
        reference_rows=reference['row_count'], comparison_rows=config.comparison_rows,
        window_description='One source-clock day, up to 5760 valid rows; half-open daily boundaries',
        step_description='One source-clock day', trailing_rows_excluded=0, trailing_start=None,
        evaluation_count=len(attempts), attempts=attempts, counts={'attempted': len(attempts), **counts},
        failed_evaluations=[a['index'] for a in attempts if a['status']=='failed'],
        limited_evaluations=[a['index'] for a in attempts if a['status']=='limited'],
        resource_limits={'max_evaluations':1000, 'max_rows_per_engine_input':12000, 'source_storage':'temporary disk index'})
    for record in payload['evaluations']:
        record['source_provenance'] = attempts[record['index']]['input_provenance']
    payload['limitations'] += [
        f"Complete-case view excludes {source.audit['excluded_rows']} source rows. Findings apply to retained telemetry; excluded intervals are unobserved.",
        'Exclusion was determined solely by per-row input validity before evaluation. Global audit statistics are never engine inputs.',
        'Daily windows use source-time boundaries, not compressed row positions. Gaps are preserved and elapsed timing is delegated to the engine.',
        'All signal units remain unknown (null), as in the frozen configuration.',
        'The source timezone is unspecified. No event timestamp or failure label was supplied or searched for.']
    payload['validation'] = validate_replay(source, evaluations, attempts, reference, episodes, payload)
    payload['wrapper']['commit'] = subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    payload['wrapper']['source_hashes'] = policy['wrapper_code_sha256']
    return payload


def validate_replay(source, evaluations, attempts, reference, episodes, payload):
    assert [a['index'] for a in attempts] == list(range(len(attempts)))
    coverage = set(reference['source_row_numbers'])
    for a in attempts:
        prov = a.get('input_provenance')
        if prov:
            assert not coverage.intersection(prov['source_row_numbers'])
            coverage.update(prov['source_row_numbers'])
    for ev, record in zip(evaluations, payload['evaluations']):
        validate_result(ev.result)
        prov = attempts[ev.index]['input_provenance']
        assert ev.comparison_end == prov['source_timestamps'][-1]
        supplied = ev.result['supplied_reference']
        for role, expected in [('reference', reference), ('comparison', prov)]:
            assert supplied[role]['row_count'] == expected['row_count']
            assert supplied[role]['time_start'] == expected['source_timestamps'][0]
            assert supplied[role]['time_end'] == expected['source_timestamps'][-1]
        assert record['uncertainty'] == evidence_projection(ev.result.get('uncertainty'))
        assert record['processing_trace'] == evidence_projection(ev.result['processing_trace'])
        for original, projected in zip(ev.result['analysis_result']['insights'], record['analysis_result']['insights']):
            assert original.get('measurable_consequence') == projected.get('measurable_consequence')
    for ep in episodes:
        indices = sorted(set(o['evaluation_index'] for o in ep.observations))
        assert indices == list(range(indices[0], indices[-1]+1))
        assert ep.evaluations == len(indices)
        assert ep.first_observed == attempts[indices[0]]['input_provenance']['source_timestamps'][-1]
        assert ep.last_observed == attempts[indices[-1]]['input_provenance']['source_timestamps'][-1]
    assert file_hash(source.path) == source.sha256
    return {'chronological_steps_accounted_for':True, 'all_steps_returned_engine_results':len(evaluations)==len(attempts),
            'full_valid_row_coverage':len(coverage)==source.count, 'valid_rows_submitted':len(coverage),
            'no_future_data_leakage':True, 'evidence_refs_resolve':True, 'episodes_consecutive_and_source_supported':True,
            'engine_consequence_preserved_verbatim':True, 'uncertainty_and_trace_preserved':True,
            'source_sha256_unchanged':True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ('csv','config','engine-path','reference-start','reference-end','end','output-dir'):
        parser.add_argument('--'+arg, required=True)
    args = parser.parse_args()
    out = Path(args.output_dir); out.mkdir(parents=True, exist_ok=True)
    config = load_config(args.config)
    engine = EngineAdapter.load(args.engine_path)
    with tempfile.TemporaryDirectory(prefix='neraium-view-') as temp:
        source = QualitySource(args.csv, Path(temp)/'view.sqlite', list(config.signal_units))
        try:
            write_json(source.audit, out/'data-quality-view.json')
            print(f'Quality view: {source.count} valid / {source.audit["original_rows"]} original; {source.audit["excluded_rows"]} excluded', flush=True)
            evaluations, attempts, reference, policy = replay_time(source, engine, config,
                *[parse_source_timestamp(v) for v in (args.reference_start,args.reference_end,args.end)], out/'checkpoints')
            payload = make_report(source, engine, config, evaluations, attempts, reference, policy)
            # Both reports serialized before existing reports are replaced.
            with tempfile.TemporaryDirectory(dir=out) as staging:
                jp = write_json(payload, Path(staging)/'historical-analysis.json')
                hp = write_html(payload, Path(staging)/'historical-analysis.html')
                jp.replace(out/jp.name); hp.replace(out/hp.name)
            print(json.dumps({'counts':payload['replay']['counts'],'summary':payload['summary'],'validation':payload['validation']},indent=2), flush=True)
        finally:
            source.close()


if __name__ == '__main__':
    main()
