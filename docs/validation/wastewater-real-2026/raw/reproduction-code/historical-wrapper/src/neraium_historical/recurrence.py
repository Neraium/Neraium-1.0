"""Offline recurrence hypothesis over immutable authoritative checkpoints.

No telemetry labels, no engine calls, no production state writes. Episode counts
are offline evidence, never governed findings. Numeric gates come from each
saved engine result; sensor-health penalties remain embedded in those gates.
"""
from collections import defaultdict
from datetime import datetime, timedelta
from statistics import median
import csv
import json
import math
from pathlib import Path
from .daily_replay import digest
from .quality_source import file_hash

POLICY = {'version':1, 'minimum_episodes':3, 'minimum_support_per_episode':2,
          'maximum_episode_days':3, 'minimum_baseline_windows_between':1,
          'recurrence_window_days':30, 'maximum_median_delta_spread':.10,
          'direction':'identical signed displacement; any opposite supported episode vetoes',
          'identity':'exact production persistence identity including modes',
          'gates':'saved eligibility, confidence and data quality with production sensor health penalties',
          'aggregation':'distinct episodes and median similarity; never sum deltas'}


def episodes_and_recurrence(rows, policy=POLICY):
    """Rows must include every chronological window, including unavailable ones."""
    episodes=[]; current=[]; baseline_gap=[]; boundary_gap=[]
    def finish():
        if not current: return
        first,last=current[0],current[-1]
        episodes.append({'start':first['start'],'end_exclusive':last['end_exclusive'],
            'direction':first['vote'], 'identity':first['identity'],
            'support_count':len(current), 'median_delta':median(r['delta'] for r in current),
            'duration_days':(datetime.fromisoformat(last['end_exclusive'])-datetime.fromisoformat(first['start'])).total_seconds()/86400,
            'baseline_gap_before':list(boundary_gap), 'windows':list(current),
            'production_temporal_support':any(r['temporal_supported'] for r in current)})
        current.clear()
    previous=None
    for r in rows:
        if previous is not None and (r['index'] != previous['index']+1 or r['start'] != previous['end_exclusive']):
            raise ValueError('Noncontiguous chronological evidence')
        previous=r
        if r['vote']:
            if current and (r['vote']!=current[-1]['vote'] or r['identity']!=current[-1]['identity']):
                finish(); baseline_gap=[]
            if not current: boundary_gap=list(baseline_gap)
            current.append(r); baseline_gap=[]
        else:
            finish()
            if r['baseline_return']: baseline_gap.append(r['index'])
            else: baseline_gap=[]  # Missing/poor quality never establishes recovery.
    finish()
    for ep in episodes:
        ep['qualified_episode'] = (ep['support_count']>=policy['minimum_support_per_episode']
                                  and ep['duration_days']<=policy['maximum_episode_days']
                                  and not ep['production_temporal_support'])
    candidates=[]
    for i,last in enumerate(episodes):
        if not last['qualified_episode']: continue
        cutoff=datetime.fromisoformat(last['end_exclusive'])-timedelta(days=policy['recurrence_window_days'])
        eligible=[e for e in episodes[:i+1] if e['qualified_episode'] and datetime.fromisoformat(e['start'])>=cutoff]
        # Do not cherry-pick same-sign episodes around contrary evidence.
        if len(eligible)<policy['minimum_episodes']: continue
        if len({e['direction'] for e in eligible})!=1: continue
        if any(e['identity']!=last['identity'] for e in eligible): continue
        if any(len(e['baseline_gap_before'])<policy['minimum_baseline_windows_between'] for e in eligible[1:]): continue
        medians=[e['median_delta'] for e in eligible]
        if max(medians)-min(medians)>policy['maximum_median_delta_spread']: continue
        candidates.append({'observed_at':last['windows'][-1]['observed_at'],
                           'direction':last['direction'],'episode_indices':[episodes.index(e) for e in eligible],
                           'episode_count':len(eligible),'median_delta_range':[min(medians),max(medians)]})
    return {'episodes':episodes, 'recurrence_supported':bool(candidates),'recurrence_observations':candidates,
            'production_continuous_support':any(r['temporal_supported'] for r in rows)}


def analyze(checkpoints, output):
    checkpoints,output=Path(checkpoints),Path(output)
    if output.exists(): raise FileExistsError(output)
    manifest=json.loads((checkpoints/'manifest.json').read_text())
    pairs=defaultdict(list); previous=None; prior_hash=None; files={}; thresholds=None
    paths=sorted(checkpoints.glob('[0-9][0-9][0-9].json'))
    if not paths: raise ValueError('No checkpoints')
    from itertools import combinations
    expected={tuple(sorted(p)) for p in combinations(manifest['config']['signal_units'],2)}
    for i,path in enumerate(paths):
        if path.stem!=f'{i:03d}': raise ValueError('Missing checkpoint')
        files[str(path)]=file_hash(path); s=json.loads(path.read_text()); result=s['result']; a=s['attempt']
        assert s['checkpoint_sha256']==digest({k:v for k,v in s.items() if k!='checkpoint_sha256'})
        assert s['handoff']['previous_checkpoint_sha256']==prior_hash
        assert s['handoff']['incoming_state_sha256']==digest(previous)
        assert result and a['status']!='failed'
        assert not result['processing_trace']['modules_failed'] and not result['processing_trace']['storage_writes']
        graph=result['relationship_graph']; state=graph['relationship_persistence_state']; th=graph['thresholds']
        if thresholds is not None: assert thresholds==th
        thresholds=th
        assert s['handoff']['outgoing_state_sha256']==digest(state)
        edges={tuple(sorted(e['columns'])):e for e in graph['edges']}
        assert len(edges)==len(graph['edges']) and edges.keys()<=expected
        for pair in sorted(expected):
            row={'index':i,'start':a['boundary_start'],'end_exclusive':a['boundary_end_exclusive'],
                 'checkpoint':str(path), 'checkpoint_sha256':s['checkpoint_sha256'],
                 'checkpoint_file_sha256':files[str(path)], 'vote':0,'baseline_return':False,
                 'temporal_supported':False,'promoted':False, 'present':pair in edges}
            if pair in edges:
                e=edges[pair]; delta=e['signed_correlation_delta']
                assert math.isfinite(delta)
                ps=state[json.dumps(list(pair),separators=(',',':'))]
                observation=ps['observations'][-1]
                acceptable=(e['eligible'] and observation['acceptable']
                            and e['edge_confidence']>=th['minimum_edge_confidence']
                            and e['data_quality_factor']>=th['minimum_data_quality_factor'])
                material=abs(delta)>=th['temporal_persistence']['minimum_displacement']
                row.update(delta=delta,baseline_correlation=e['baseline_correlation'],current_correlation=e['current_correlation'],
                    vote=(1 if delta>0 else -1) if acceptable and material else 0,
                    baseline_return=bool(acceptable and not material),identity=ps['identity'],
                    eligible=e['eligible'],acceptable=acceptable,edge_confidence=e['edge_confidence'],
                    data_quality_factor=e['data_quality_factor'],sensor_health_context=e['sensor_health_context'],
                    temporal_supported=e['temporal_persistence_supported'],promoted=e['promoted_changed_edge'],
                    support_count=e['temporal_persistence_supporting_observations'],
                    direction_agreement=e['temporal_persistence_direction_agreement'],
                    single_window_change_type=e['single_window_change_type'],change_type=e['change_type'],
                    observed_at=observation['observed_at'], source_dataset_id=e['source_dataset_id'],
                    reference_dataset_id=e['reference_dataset_id'], time_window=e['time_window'],source_rows=e['source_rows'],
                    reference_input_hash=result['supplied_reference']['reference']['input_hash'],
                    comparison_input_hash=result['supplied_reference']['comparison']['input_hash'])
            pairs[pair].append(row)
        previous=state; prior_hash=s['checkpoint_sha256']
    reports=[{'pair':list(pair),**episodes_and_recurrence(rows)} for pair,rows in sorted(pairs.items())]
    report={'offline_only':True,'policy':POLICY,'engine_thresholds':thresholds,'checkpoint_files':files,
            'engine':manifest['engine'],'source_sha256':manifest['source_sha256'],
            'checkpoint_count':len(paths),'pairs':reports}
    output.mkdir(parents=True)
    (output/'recurrence-analysis.json').write_text(json.dumps(report,indent=2)+'\n')
    fields=['pair','index','start','end_exclusive','present','baseline_correlation','current_correlation','delta','vote',
            'baseline_return','eligible','acceptable','edge_confidence','data_quality_factor','sensor_health_context',
            'temporal_supported','support_count','direction_agreement','promoted','single_window_change_type','change_type',
            'observed_at','identity','reference_dataset_id','source_dataset_id','reference_input_hash','comparison_input_hash',
            'checkpoint','checkpoint_sha256','checkpoint_file_sha256','source_rows']
    with (output/'pair-window-evidence.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader()
        for pair,rows in sorted(pairs.items()):
            for r in rows:
                row={k:r.get(k) for k in fields}; row['pair']=' | '.join(pair)
                w.writerow({k:json.dumps(v,sort_keys=True) if isinstance(v,(dict,list)) else v for k,v in row.items()})
    with (output/'pair-summary.csv').open('w',newline='') as f:
        w=csv.writer(f); w.writerow(['pair','material_windows','gated_support_windows','temporal_windows','promoted_windows','qualified_episodes','recurrence_supported'])
        for p in reports:
            rows=pairs[tuple(p['pair'])]
            w.writerow([' | '.join(p['pair']),sum(abs(r.get('delta',0))>=thresholds['temporal_persistence']['minimum_displacement'] for r in rows),
                sum(bool(r['vote']) for r in rows),sum(r['temporal_supported'] for r in rows),sum(r['promoted'] for r in rows),
                sum(e['qualified_episode'] for e in p['episodes']),p['recurrence_supported']])
    assert all(file_hash(Path(p))==h for p,h in files.items())
    (output/'blind-complete.json').write_text(json.dumps({'completed_at_utc':datetime.now().isoformat(),
        'analysis_sha256':file_hash(output/'recurrence-analysis.json'), 'pair_windows_sha256':file_hash(output/'pair-window-evidence.csv'),
        'manifest_accessed':False,'policy_sha256':digest(POLICY)},indent=2)+'\n')
    return report
