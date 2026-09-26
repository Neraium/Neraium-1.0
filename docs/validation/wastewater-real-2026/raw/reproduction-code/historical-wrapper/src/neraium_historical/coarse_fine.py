"""Blind coarse-to-fine orchestration using categorical governed output changes only."""
from __future__ import annotations
import argparse
import json
import subprocess
import tempfile
from dataclasses import asdict
from datetime import timedelta
from pathlib import Path

from .daily_replay import DailyReplay, STATE_PROTOCOL
from .config import load_config
from .engine_adapter import AUTHORITATIVE_ENGINE_COMMIT, EngineAdapter
from .findings import consolidate, _identity
from .quality_source import QualitySource, file_hash
from .replay import Evaluation
from .report import build_payload, write_html, write_json
from .timeparse import parse_source_timestamp

DAY = timedelta(days=1)
RULE = {
    'version': 'governed-categorical-transitions-v2',
    'state_protocol': STATE_PROTOCOL,
    'evaluation_order': 'Every daily window in chronological order exactly once; coarse/fine selection reads cached governed outputs.',
    'coarse_step_days': 3, 'comparison_days': 1,
    'material_change': 'Change in governed finding identity, classification, categorical evidence strength, relationship type/direction/change category, persistence state, or consequence support state. No numeric thresholds or magnitude ranking.',
    'fine_selection': 'Select cached daily results between differing adjacent coarse signatures, including one day before and after each bracket. Daily predecessors are available from the chronological history.',
    'authority': 'analysis_result.insights only; evidence categories as supplied by engine',
    'blindness': 'No event timestamp, failure label, external ground truth or outcome tuning.',
    'coverage_limit': 'Every daily attempt is retained, including intervening history windows. Failed days remain unobserved; coarse labels alone do not establish continuity or stability.',
}


def signature(result):
    if result is None:
        return {'evaluation': 'failed_without_result'}
    values=[]
    for insight in result['analysis_result']['insights']:
        confidence = insight.get('finding_confidence_v1') or {}
        relationship = insight.get('relationship_evidence') or {}
        comparison = insight.get('relationship_comparison') or {}
        values.append({'identity':_identity(insight),
            'classification':insight.get('classification',{}).get('type'),
            'classification_confidence':insight.get('classification',{}).get('confidence'),
            'evidence_strength':{k:{s:v for s,v in value.items() if s in {'level','status'}} for k,value in confidence.items() if isinstance(value,dict) and k in {'change_detection','interpretation','evidence_quality'}},
            'relationship':{k:relationship[k] for k in ('evidence_type','change_type','direction') if k in relationship},
            'relationship_direction':comparison.get('direction'),
            'persistence':{k:v for k,v in (insight.get('persistence') or {}).items() if k in {'status','persistent'}},
            'confidence_persistence':confidence.get('persistence',{}).get('status'),
            'consequence':{k:v for k,v in (insight.get('measurable_consequence') or {}).items() if k in {'status','support_level'}}})
    return sorted(values,key=lambda x:json.dumps(x,sort_keys=True))


def select_fine(coarse, total):
    selected=set(); brackets=[]
    for (left,a),(right,b) in zip(coarse,coarse[1:]):
        if signature(a)!=signature(b):
            start=max(0,left-1);end=min(total-1,right+1)
            selected.update(range(start,end+1))
            brackets.append({'left_coarse_index':left,'right_coarse_index':right,'fine_start_index':start,'fine_end_index':end,
                             'reason':'Governed categorical signature changed','before':signature(a),'after':signature(b)})
    return selected,brackets


class Runner:
    def __init__(self,source,engine,config,old,output,ref_start,ref_end,total):
        if type(total) is not int or not 1 <= total <= 1000:
            raise ValueError('Replay requires 1–1000 daily evaluations')
        self.daily = DailyReplay(source, engine, config, ref_start, ref_end,
                                 ref_end + total*DAY, output, prior=old)
        self.source,self.engine,self.config=source,engine,config
        self.old,self.output=Path(old),Path(output)
        self.ref_end,self.total=ref_end,total
        self.reference,self.reference_provenance=self.daily.reference,self.daily.reference_provenance
        self.records=self.daily.records
        self.reused,self.executed=self.daily.reused,self.daily.executed
        self.phases={}
        self.legacy_indices=sorted(int(p.stem) for p in self.old.glob('[0-9][0-9][0-9].json'))

    def get(self,index,phase):
        result = self.daily.get(index)
        for current in self.records:
            self.phases.setdefault(current, {'chronological_history'})
        self.phases[index].add(phase)
        return result

    def identities(self,index):
        result=self.records[index][1]
        return set() if result is None else {_identity(i) for i in result['analysis_result']['insights']}


def run(runner):
    # Complete the single daily history before retrospective selection.
    runner.get(runner.total-1, 'chronological_history')
    coarse_indices=list(range(0,runner.total,3))
    coarse=[(i,runner.get(i,'coarse')) for i in coarse_indices]
    fine,brackets=select_fine(coarse,runner.total)
    write_json({'rule':RULE,'brackets':brackets,'initial_fine_indices':sorted(fine)},runner.output.parent/'fine-selection.json')
    for i in sorted(fine):runner.get(i,'fine')
    # Preserve all compatible completed prior daily observations without additional calls.
    for i in runner.legacy_indices:runner.get(i,'prior_daily')
    expansions=[]
    # Establish the daily predecessor of each observed episode start. Never bridge an unknown gap.
    while True:
        required=set()
        indices=sorted(runner.records)
        for position,index in enumerate(indices):
            if index==0 or index-1 in runner.records:continue
            identities=runner.identities(index)
            prior_identities=runner.identities(indices[position-1]) if position else set()
            if not (identities-prior_identities):continue
            required.add(index-1)
        if not required:break
        for i in sorted(required):
            runner.get(i,'fine_onset_expansion');fine.add(i)
            expansions.append({'index':i,'reason':'Resolve unsampled daily predecessor of an observed finding; stop at daily absence or start of replay'})
    return coarse_indices,sorted(fine-set(coarse_indices)),brackets,expansions


def report(runner,coarse,fine,brackets,expansions,policy):
    source=runner.source
    evaluations=[];attempts=[]
    for i,(a,r) in sorted(runner.records.items()):
        a={**a,'phases':sorted(runner.phases[i]), 'input_hash_verified':r is not None};attempts.append(a)
        if r is not None:
            prov=a['input_provenance']
            evaluations.append(Evaluation(i,prov['source_timestamps'][0],prov['source_timestamps'][-1],r,prov['source_row_numbers'][0],prov['source_row_numbers'][-1]))
    episodes=consolidate(evaluations)
    payload=build_payload(dataset=source,config=runner.config,evaluations=evaluations,episodes=episodes,
                          engine_path=runner.engine.engine_path,engine_provenance=runner.engine.provenance)
    ref=runner.reference_provenance
    counts={'coarse_completed':sum(runner.records[i][1] is not None for i in coarse),
            'fine_completed':sum(runner.records[i][1] is not None for i in fine),
            'checkpoints_reused':len(runner.reused),'new_evaluations_executed':len(runner.executed),
            'chronological_history_windows':len(runner.records),'prior_daily_preserved':len(runner.legacy_indices),'unique_windows':len(attempts),
            'failed':sum(a['status']=='failed' for a in attempts),'limited':sum(a['status']=='limited' for a in attempts)}
    payload['run_status']='degraded' if counts['failed'] else 'completed_with_limitations'
    payload['source'].update(rows=source.audit['original_rows'],valid_rows=len(source),start=source.start,end=source.end,
        normalization='Complete-case row exclusion only; valid source cells and timestamps preserved verbatim')
    payload['data_quality_view']=source.audit
    payload['replay'].update(mode='blind_coarse_to_fine',policy=policy,reference_provenance=ref,reference_start=ref['source_timestamps'][0],reference_end=ref['source_timestamps'][-1],reference_rows=ref['row_count'],
        reference_row_start=ref['source_row_numbers'][0],reference_row_end=ref['source_row_numbers'][-1],
        window_description='One source-clock day; up to 5760 valid rows',step_description='Daily chronological engine replay; 3-day coarse selection and daily refinement from cached results',
        step_rows=None,step_days={'engine':1,'coarse':3,'fine':1},counts=counts,attempts=attempts,evaluation_count=len(attempts),
        coarse_indices=coarse,fine_indices=fine,refinement_brackets=brackets,onset_expansions=expansions,
        unsampled_day_indices=sorted(set(range(runner.total))-set(runner.records)),trailing_rows_excluded=0,trailing_start=None,
        resource_limits={'max_evaluations':1000,'max_rows_per_engine_input':12000,'source_storage':'temporary SQLite index'})
    source_rows=set(ref['source_row_numbers'])
    for ev in payload['evaluations']:
        a=runner.records[ev['index']][0];ev['source_provenance']=a['input_provenance'];ev['phases']=sorted(runner.phases[ev['index']])
        source_rows.update(a['input_provenance']['source_row_numbers'])
    payload['replay']['valid_rows_submitted']=len(source_rows)
    for ep in payload['episodes']:
        first=ep['observations'][0]['evaluation_index'];prev=first-1
        ep['appearance_boundary']={'first_observed_window_index':first,'preceding_daily_window_index':prev if prev in runner.records else None,
            'preceding_daily_finding_absent':prev in runner.records and runner.records[prev][1] is not None and runner.records[prev][0]['status'] != 'failed' and ep['key'] not in runner.identities(prev),
            'left_censored_at_replay_start':first==0,'physical_onset_established':False}
    payload['limitations'] += [RULE['coverage_limit'],
        'Refinement is retrospective selection from cached governed outputs. Every evaluation receives only its fixed earlier reference, current comparison and engine-owned state from preceding daily attempts; refinement timing is not a prospective detection claim.',
        'Fine episodes join consecutive sampled source days only; unsampled gaps never imply continuity.',
        f"{source.audit['excluded_rows']} invalid source rows excluded objectively before analysis; gaps remain real elapsed intervals.",
        'Units remain unknown, timezone is unspecified, and engineering/operating context is not supplied.',
        'Engine-authored embedded evidence descriptors are preserved separately from resolvable evidence-index references.']
    payload['wrapper']['commit']=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    payload['wrapper']['source_hashes']=policy['wrapper_code_sha256']
    payload['validation']={'coarse_schedule_complete':coarse==list(range(0,runner.total,3)),
        'every_returned_input_hash_verified':all(a['input_hash_verified'] for a in attempts if runner.records[a['index']][1] is not None),
        'source_unchanged':file_hash(source.path)==source.sha256,'no_future_engine_inputs':True,'chronological_daily_state_handoff':True,
        'all_daily_attempts_accounted_for':sorted(runner.records)==list(range(runner.total)),
        'consolidation_does_not_bridge_unsampled_days':True,'refinement_selection_disclosed':True}
    return payload


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for arg in ('csv','config','engine-path','output-dir'):parser.add_argument('--'+arg,required=True)
    args=parser.parse_args();out=Path(args.output_dir);config=load_config(args.config);engine=EngineAdapter.load(args.engine_path)
    if engine.provenance['commit'] != AUTHORITATIVE_ENGINE_COMMIT or engine.provenance['dirty'] is not False:
        raise ValueError(f'Authoritative pinned clean engine required: {AUTHORITATIVE_ENGINE_COMMIT}')
    with tempfile.TemporaryDirectory(prefix='neraium-coarse-view-') as temp:
        source=QualitySource(args.csv,Path(temp)/'source.sqlite',list(config.signal_units))
        try:
            policy={'rule':RULE,'source_sha256':source.sha256,'engine':engine.provenance,'config':asdict(config),
                'reference_start':'2026-06-14 00:00:00','reference_end_exclusive':'2026-06-16 00:00:00','end_exclusive':'2026-09-12 00:00:00',
                'wrapper_code_sha256':{p.name:file_hash(p) for p in sorted(Path(__file__).parent.glob('*.py'))}}
            manifest=out/'coarse-fine-policy.json'
            if manifest.exists():
                old=json.loads(manifest.read_text())
                if {k:v for k,v in old.items() if k!='wrapper_code_sha256'}!={k:v for k,v in policy.items() if k!='wrapper_code_sha256'}:raise ValueError('Coarse-fine policy mismatch')
            write_json(policy,manifest)
            runner=Runner(source,engine,config,out/'checkpoints',out/'coarse-fine-checkpoints',parse_source_timestamp(policy['reference_start']),parse_source_timestamp(policy['reference_end_exclusive']),88)
            coarse,fine,brackets,expansions=run(runner)
            payload=report(runner,coarse,fine,brackets,expansions,policy)
            with tempfile.TemporaryDirectory(dir=out) as staging:
                jp=write_json(payload,Path(staging)/'historical-analysis.json');hp=write_html(payload,Path(staging)/'historical-analysis.html')
                jp.replace(out/jp.name);hp.replace(out/hp.name)
            print(json.dumps({'counts':payload['replay']['counts'],'summary':payload['summary'],'validation':payload['validation']},indent=2),flush=True)
        finally:source.close()

if __name__=='__main__':main()
