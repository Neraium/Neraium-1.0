from __future__ import annotations

import html
import json
import os
import tempfile
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import __version__
from .config import ReplayConfig
from .csv_loader import LoadedCsv
from .findings import FindingEpisode
from .replay import Evaluation

# Presentation exclusions only. No evidence, classification or consequence is computed here.
EXCLUDED_FIELDS = frozenset({
    'recommendations', 'recommended_checks', 'investigation_guidance', 'recommended_investigation',
    'recommended_first_action', 'first_check', 'recommended_check', 'operator_check',
    'recommended_action', 'recommendation', 'recommended_operator_check', 'likely_contributors',
    'possible_consequence', 'possible_operational_consequence', 'why_it_matters',
    'activity_timeline',
    'lead_time_estimate', 'lead_time', 'predicted_failure', 'root_cause', 'diagnosis',
})


def evidence_projection(value: Any) -> Any:
    if isinstance(value, dict):
        return {('engine_evidence_descriptors' if k == 'evidence_refs' and isinstance(v, list) and any(isinstance(x, dict) or (isinstance(x, str) and x.startswith('{')) for x in v) else k): (v if k in {'measurable_consequence', 'relationship_persistence_state', 'relationship_recurrence_state', 'recurrence_evidence'} else {name: evidence_projection(item) for name, item in v.items()}
                    if k in {'evidence_index', 'signal_units'} and isinstance(v, dict)
                    else evidence_projection(v))
                for k, v in value.items() if k not in EXCLUDED_FIELDS}
    if isinstance(value, list):
        return [evidence_projection(v) for v in value]
    return value


def build_payload(*, dataset: LoadedCsv, config: ReplayConfig, evaluations: list[Evaluation],
                  episodes: list[FindingEpisode], engine_path: str,
                  engine_provenance: dict[str, Any] | None = None) -> dict[str, Any]:
    timestamp = dataset.timestamp_column
    end_row = evaluations[-1].source_row_end if evaluations else 0
    limitations = [
        'This report describes supplied historical telemetry; insufficient evidence is a valid result.',
        'First and last observed are comparison-window completion times, not physical onset or resolution times.',
        'Episodes join matching findings in consecutive evaluations only. Reappearance after absence starts a new episode.',
        'Supported evaluation counts are presentation bookkeeping, not elapsed persistence or independent confirmations. Windows may overlap.',
        'Persistence, relationship ranking, classification and measurable consequence are reported only as supplied by Neraium; overlapping consequence windows are never summed.',
        'Incomplete trailing windows are excluded; no interpolation, resampling, unit conversion or missing-value imputation is performed.',
        'No cause, diagnosis, future failure, corrective action, actuation or live monitoring is established by this report.',
        'Engine-authored local evidence timestamps are retained verbatim; original source bounds and supplied-reference provenance define replay timing.',
    ]
    records = []
    for ev in evaluations:
        result = ev.result
        analysis = result['analysis_result']
        for text in [*(result.get('uncertainty', {}).get('limitations') or []),
                     *(result.get('supplied_reference', {}).get('limitations') or [])]:
            if text not in limitations:
                limitations.append(text)
        records.append({
            'index': ev.index, 'comparison_start': ev.comparison_start, 'comparison_end': ev.comparison_end,
            'source_row_start': ev.source_row_start, 'source_row_end': ev.source_row_end,
            'engine_status': result.get('status'),
            'analysis_result': {k: analysis[k] for k in (
                'schema_version', 'status', 'analysis_id', 'generated_at', 'insights', 'evidence_index',
                'relationships', 'sii_evidence', 'data_quality', 'warnings', 'errors', 'analysis_metadata'
            ) if k in analysis},
            'supplied_reference': result.get('supplied_reference'),
            'processing_trace': result.get('processing_trace'), 'uncertainty': result.get('uncertainty'),
            'engine': result.get('engine'),
            'relationship_graph': result.get('relationship_graph'),
            'strongest_relationship_changes': result.get('compatibility', {}).get('relationship_model', {}).get('top_relationship_changes', []),
            'relationship_ranking_source': 'evaluate_sii.compatibility.relationship_model.top_relationship_changes (engine order)',
        })
    failed = [ev.index for ev in evaluations if ev.result.get('processing_trace', {}).get('modules_failed')
              or ev.result.get('status') in {'failed', 'error'} or ev.result['analysis_result'].get('errors')]
    limited = [ev.index for ev in evaluations if ev.result.get('processing_trace', {}).get('modules_limited')
               or ev.result.get('status') in {'limited', 'unavailable', 'insufficient_evidence'}]
    observed = [ev.comparison_end for ev in evaluations if ev.result['analysis_result']['insights']]
    payload = {
        'report_type': 'neraium_historical_analysis/v1',
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'run_status': 'degraded' if failed else 'completed_with_limitations' if limited else 'completed' if evaluations else 'not_evaluated',
        'wrapper': {'name': 'neraium-historical-analysis', 'version': __version__},
        'source': {'filename': dataset.path.name, 'sha256': dataset.sha256, 'rows': len(dataset.rows),
                   'signals': dataset.numeric_columns, 'numeric_profiles': dataset.numeric_profiles,
                   'timestamp_column': timestamp, 'start': dataset.rows[0][timestamp], 'end': dataset.rows[-1][timestamp],
                   'timestamp_mode': 'source_clock_timezone_not_supplied' if len(str(dataset.rows[0][timestamp])) == 19 and ' ' in str(dataset.rows[0][timestamp]) else 'timezone_aware',
                   'normalization': 'UTF-8 BOM accepted; numeric cells parsed as finite floats; names and timestamps preserved',
                   'row_numbering': '1-based data rows; header excluded'},
        'engine': {'authority': 'Neraium-1.0 app.engine.sii_engine.evaluate_sii', 'path': engine_path,
                   **(engine_provenance or {}),
                   'reported_identity': evaluations[0].result.get('engine') if evaluations else None},
        'replay': {**asdict(config), 'evaluation_count': len(evaluations),
                   'mode': 'supplied_reference', 'reference_start': dataset.rows[0][timestamp],
                   'reference_end': dataset.rows[min(config.reference_rows, len(dataset.rows)) - 1][timestamp],
                   'analyzed_start': evaluations[0].comparison_start if evaluations else None,
                   'analyzed_end': evaluations[-1].comparison_end if evaluations else None,
                   'reference_row_start': 1, 'reference_row_end': min(config.reference_rows, len(dataset.rows)),
                   'trailing_rows_excluded': len(dataset.rows) - end_row if evaluations else len(dataset.rows),
                   'trailing_start': dataset.rows[end_row][timestamp] if evaluations and end_row < len(dataset.rows) else None,
                   'failed_evaluations': failed, 'limited_evaluations': limited,
                   'resource_limits': {'max_evaluations': 1000, 'max_csv_bytes': 67108864}},
        'summary': {'finding_episode_count': len(episodes),
                    'first_observed_finding': observed[0] if observed else None,
                    'last_observed_finding': observed[-1] if observed else None},
        'episodes': [asdict(ep) for ep in episodes], 'evaluations': records, 'limitations': limitations,
        'projection': {'omitted_engine_fields': sorted(EXCLUDED_FIELDS),
                       'note': 'Evidence-focused projection, not the full engine response. Recommendations and speculative consequence text are omitted; measurable_consequence is retained verbatim. Embedded engine evidence descriptors are named engine_evidence_descriptors; actual evidence-index IDs retain evidence_refs. Activity timelines are omitted because they mix observations with prescriptive text.'},
    }
    return evidence_projection(payload)


def _atomic_write(target: Path, content: str) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=target.parent, delete=False) as out:
            name = out.name
            out.write(content)
        os.replace(name, target)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)
    return target


def write_json(payload: dict[str, Any], path: str | Path) -> Path:
    return _atomic_write(Path(path), json.dumps(payload, indent=2, allow_nan=False) + '\n')


def _escape(value: Any) -> str:
    return html.escape(str(value if value is not None else 'Not supplied'))


def _details(label: str, value: Any) -> str:
    return f'<details><summary>{_escape(label)}</summary><pre>{_escape(json.dumps(value, indent=2, allow_nan=False))}</pre></details>'


def _facts(items) -> str:
    return '<dl>' + ''.join(f'<dt>{_escape(k)}</dt><dd>{_escape(v)}</dd>' for k, v in items) + '</dl>'


def _finding(ep: dict) -> str:
    insight = ep['insight']
    classification = insight.get('classification') or {}
    latest = ep['observations'][-1]['insight'] if ep['observations'] else insight
    persistence = latest.get('persistence') or {}
    consequence = latest.get('measurable_consequence') or {}
    result = f'<article class="episode"><span class="badge">{_escape(classification.get("label") or classification.get("type") or "Classification not supplied")}</span><h3>{_escape(insight.get("title") or "Governed finding")}</h3>'
    result += f'<p>{_escape(insight.get("what_changed") or insight.get("explanation") or "See supporting evidence.")}</p>'
    result += _facts([('First observed', ep['first_observed']), ('Last observed', ep['last_observed']),
                      ('Supporting evaluations', ep['evaluations']),
                      ('Source signals', ', '.join(insight.get('source_tags') or []) or 'See evidence'),
                      ('Engine persistence (latest observation)', persistence.get('summary') or persistence.get('status') or 'Not supplied'),
                      ('Measurable consequence (latest observation)', consequence.get('statement') or 'Not supplied by engine')])
    result += f'<p class="note">{_escape(latest.get("certainty_limit") or "Interpretation remains bounded by the recorded evidence.")}</p>'
    result += '<h4>Evidence windows</h4><div class="table-wrap"><table><thead><tr><th>Evaluation</th><th>Comparison period</th><th>Evidence references</th></tr></thead><tbody>'
    for obs in ep['observations']:
        result += f'<tr><td><a href="#evaluation-{obs["evaluation_index"]}">{obs["evaluation_index"] + 1}</a></td><td>{_escape(obs["comparison_start"])}<br>{_escape(obs["comparison_end"])}</td><td>{len(obs["evidence_refs"])}</td></tr>'
    result += '</tbody></table></div>'
    result += _details('Governed observations, uncertainty, persistence and consequence', ep['observations'])
    result += _details('Resolved evidence, scoped by evaluation', ep['evidence'])
    return result + '</article>'


def write_html(payload: dict[str, Any], path: str | Path) -> Path:
    source, replay, summary = payload['source'], payload['replay'], payload['summary']
    cards = ''.join(f'<div class="card"><span>{_escape(k)}</span><strong>{_escape(v)}</strong></div>' for k, v in (
        ('Source rows', source['rows']), ('Signals', len(source['signals'])),
        ('Evaluated windows', replay['evaluation_count']), ('Finding episodes', summary['finding_episode_count'])))
    facts = _facts([('Source dataset', source['filename']), ('Source time range', f'{source["start"]} → {source["end"]}'),
                    ('Analyzed time range', f'{replay["analyzed_start"]} → {replay["analyzed_end"]}'),
                    ('Fixed reference period', f'{replay["reference_start"]} → {replay["reference_end"]}'),
                    ('Replay windows', replay.get('window_description') or f'{replay["reference_rows"]} reference / {replay["comparison_rows"]} comparison / {replay["step_rows"]} step rows'),
                    ('Replay step', replay.get('step_description', replay['step_rows'])),
                    ('Trailing rows excluded', replay['trailing_rows_excluded']), ('Timestamp basis', source['timestamp_mode']),
                    ('Declared units', ', '.join(f'{k}: {v if v is not None else "unknown"}' for k, v in replay['signal_units'].items()))])
    findings = ''.join(_finding(ep) for ep in payload['episodes']) or '<p class="note">No governed finding was produced. This does not establish normal operation; review evaluation status, uncertainty and evidence limitations below.</p>'
    windows = ''
    for ev in payload['evaluations']:
        trace = ev['processing_trace'] or {}
        windows += f'<article id="evaluation-{ev["index"]}"><h3>Evaluation {ev["index"] + 1}</h3><p>{_escape(ev["comparison_start"])} → {_escape(ev["comparison_end"])}</p>'
        windows += _facts([('Engine status', ev['engine_status']), ('Data rows', f'{ev["source_row_start"]}–{ev["source_row_end"]}'),
                           ('Modules failed', ', '.join(trace.get('modules_failed') or []) or 'None'),
                           ('Modules limited', ', '.join(trace.get('modules_limited') or []) or 'None')])
        relationships = ev['strongest_relationship_changes']
        windows += '<h4>Strongest relationship changes · engine-ranked</h4>'
        if relationships:
            windows += '<div class="table-wrap"><table><thead><tr><th>Signals</th><th>Reference correlation</th><th>Comparison correlation</th><th>Engine change</th></tr></thead><tbody>'
            for rel in relationships:
                windows += '<tr>' + ''.join(f'<td>{_escape(v)}</td>' for v in (
                    ' / '.join(rel.get('columns') or rel.get('source_tags') or []) or rel.get('relationship'), rel.get('baseline_correlation'),
                    rel.get('recent_correlation', rel.get('current_correlation')), rel.get('correlation_delta'))) + '</tr>'
            windows += '</tbody></table></div>' + _details('Engine-ranked relationship evidence', relationships)
        else:
            windows += '<p>No ranked relationship change supplied by the engine.</p>'
        windows += _details('Uncertainty and limitations', ev['uncertainty'])
        windows += _details('Governed analysis and evidence', ev['analysis_result'])
        windows += _details('Temporal relationship evidence and state', ev.get('relationship_graph'))
        windows += _details('Processing trace and supplied-reference provenance', {'processing_trace': trace, 'supplied_reference': ev['supplied_reference']}) + '</article>'
    if replay.get('attempts'):
        windows += _details('All planned steps, status, errors and original source row mapping', replay['attempts'])
    quality = ''
    if payload.get('data_quality_view'):
        audit = payload['data_quality_view']
        quality = '<h2>Data-quality analysis view</h2>' + _facts([('Original rows', audit['original_rows']), ('Excluded rows', audit['excluded_rows']), ('Valid rows', audit['valid_rows']), ('Exclusion rule', audit['rule'])])
        quality += _details('Quality audit and exact excluded-row provenance', audit)
    if replay.get('mode') == 'blind_coarse_to_fine':
        quality += '<h2>Coarse-to-fine coverage</h2>' + _facts([(k.replace('_', ' '), v) for k,v in replay['counts'].items()])
        quality += '<p class="note">Engine evaluations run daily in chronological order. Coarse observations use a three-day step; fine selection reads cached governed outputs. All daily history windows are retained. Failed days do not establish absence or continuity.</p>'
        quality += _details('Coarse schedule, fine windows and unsampled days (zero-based day indices after reference)', {k:replay[k] for k in ('coarse_indices','fine_indices','unsampled_day_indices')})
        quality += _details('Governed refinement selection and onset expansion', {k:replay[k] for k in ('refinement_brackets','onset_expansions')})
    provenance = _facts([('Source SHA-256', source['sha256']), ('Engine authority', payload['engine']['authority']),
                         ('Engine identity', json.dumps(payload['engine']['reported_identity'])),
                         ('Engine commit', payload['engine'].get('commit')), ('Engine working tree modified', payload['engine'].get('dirty')),
                         ('Wrapper version', payload['wrapper']['version']), ('Report generated', payload['generated_at'])])
    css = '''body{font-family:system-ui,-apple-system,sans-serif;margin:0;background:#f3f6f8;color:#172b3a;line-height:1.55}main{max-width:1080px;margin:auto;padding:48px 24px 80px}header{border-top:5px solid #147b77;padding-top:24px}h1{font-size:38px;line-height:1.2;margin:12px 0}h2{margin-top:38px}h3{margin:10px 0;font-size:22px}h4{margin-bottom:12px}.eyebrow{font-weight:700;letter-spacing:.13em;color:#146661;font-size:12px}.sub,dt,.card span{color:#506674}.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:26px 0}.card,article{background:white;border:1px solid #d6e0e5;border-radius:12px;padding:22px}.card strong{display:block;font-size:30px}.card span{font-size:13px}article{margin:16px 0;scroll-margin:20px}.badge{display:inline-block;background:#e7f1f0;color:#155e59;padding:4px 10px;border-radius:20px;font-size:13px;font-weight:600}.note{border-left:3px solid #9b7b31;padding:12px 16px;background:#fcf8ec}dl{display:grid;grid-template-columns:230px 1fr;gap:8px 20px}dd{margin:0;overflow-wrap:anywhere}dt{font-size:14px}details{border-top:1px solid #d6e0e5;margin-top:14px;padding-top:12px}summary{cursor:pointer;font-weight:600}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px;background:#f3f6f8;padding:16px}.table-wrap{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:14px}th,td{padding:12px 8px;border-bottom:1px solid #d6e0e5;text-align:left;vertical-align:top}th{color:#506674}a{color:#126963}li{margin-bottom:8px}footer{color:#506674;font-size:13px;margin-top:40px}@media(max-width:700px){.grid{grid-template-columns:1fr 1fr}dl{grid-template-columns:1fr;gap:3px}dd{margin-bottom:12px}main{padding:24px 16px}h1{font-size:30px}}@media print{body{background:white}main{padding:0}.card,article{break-inside:avoid}pre{font-size:9px}a{color:inherit}details{display:block}}'''
    doc = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'"><title>Neraium Historical Analysis — {_escape(source['filename'])}</title><style>{css}</style></head><body><main><header><div class="eyebrow">NERAIUM / HISTORICAL EVIDENCE</div><h1>What changed. When it was observed.</h1><p class="sub">Historical Analysis · Supplied-reference chronological replay</p><span class="badge">{_escape(payload['run_status'].replace('_', ' '))}</span></header><div class="grid">{cards}</div><h2>Dataset &amp; replay scope</h2>{facts}{quality}<p class="note">Observations describe completed comparison windows. A finding may report stability or insufficient evidence. Repeated observations do not establish elapsed persistence.</p><h2>Finding timeline</h2>{findings}<h2>Evaluation record</h2><p>Relationship order and values are supplied by Neraium. These supporting measurements do not create additional findings.</p>{windows}<h2>Uncertainty &amp; interpretation limits</h2><ul>{''.join(f'<li>{_escape(x)}</li>' for x in payload['limitations'])}</ul><h2>Provenance</h2>{provenance}{_details('Engine source and report projection', {'engine': payload['engine'], 'projection': payload['projection']})}<footer>Neraium Historical Analysis · Evidence record accompanies this report as historical-analysis.json.</footer></main></body></html>'''
    return _atomic_write(Path(path), doc)
