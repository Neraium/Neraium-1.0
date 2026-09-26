#!/usr/bin/env python3
"""Frozen-engine validation. No production configuration or decision overrides.
All generated inputs, complete outputs and exceptions are retained in gzip JSONL.
"""
from __future__ import annotations
import argparse, copy, csv, gzip, hashlib, json, math, os, sys, tempfile, time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

def digest(x):
    return hashlib.sha256(json.dumps(x, sort_keys=True, separators=(',', ':'), default=str).encode()).hexdigest()

def write(path, x):
    path.write_text(json.dumps(x, indent=2, sort_keys=True, default=str)+'\n')

def check_freeze(path):
    freeze=json.loads(path.read_text())
    changed=[p for p,h in freeze['files_sha256'].items() if hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=h]
    if changed: raise RuntimeError(f'frozen_source_changed:{changed}')
    return {'changed_files': changed, 'commit':freeze['commit']}

PAIR=['flow','differential_pressure']
def rows(seed, day, rho, *, noisy=False, n=96):
    rng=np.random.default_rng(seed + day*10000)
    if noisy:
        a=rng.normal(size=n); b=rng.normal(size=n)
    else:
        a=np.sin(np.arange(n)*2*np.pi/n + seed*.17)
        b=np.cos(np.arange(n)*2*np.pi/n + seed*.17)
    start=datetime(2026,1,1,tzinfo=timezone.utc)+timedelta(days=day)
    return [{'timestamp':(start+timedelta(minutes=5*i)).isoformat(), PAIR[0]:float(100+10*a[i]),PAIR[1]:float(40+4*(rho*a[i]+math.sqrt(1-rho*rho)*b[i]))} for i in range(n)]

def args_for(ref, cur, signals=PAIR):
    return {'columns':['timestamp',*signals], 'reference_rows':ref, 'comparison_rows':cur,
            'numeric_profiles':[{'column':c} for c in signals], 'timestamp_column':'timestamp',
            'signal_units':{c:None for c in signals}}

def plan():
    cases=[]
    # A symmetric grid, declared before execution; boundary outcomes are descriptive.
    for base in [-.65,.65]:
        for sign in [-1,1]:
            for magnitude in [0,.05,.10,.15,.20,.25,.30]:
                for seed in [0,1,2]:
                    cases.append({'id':f'grid_{base}_{sign}_{magnitude}_{seed}','family':'sensitivity',
                                  'base':base,'deltas':[sign*magnitude]*8,'seed':seed,'magnitude':magnitude})
    for seed in range(10):
        for kind,ds in [('stable',[0]*8),('stationary_noise',[0]*8),('transient',[0,0,.2,0,0,0,0,0]),
                        ('alternating',[.2,-.2]*4),('recovery',[.2]*8+[0]*4)]:
            cases.append({'id':f'{kind}_{seed}','family':kind,'base':.65,'deltas':ds,'seed':seed,'noisy':kind=='stationary_noise'})
    for kind in ['missing','nonfinite','duplicate_time','reversed_time','too_short','irregular','flatline','outlier','level_compensation','response_change','new_context']:
        cases.append({'id':kind,'family':'stress','base':.65,'deltas':[.2]*8,'seed':0,'transform':kind})
    return {'version':'prize-validation-v1','cases':cases,'engine_configuration':'defaults; no threshold overrides',
            'primary_endpoint':'graph edge temporal_persistence_supported; separately promoted_changed_edge and governed persistent_relationship_change',
            'negative_endpoint':'any temporal support in stable, stationary_noise, transient, alternating sequences',
            'sensitivity':'observational grid; no target detection rate; all outcomes retained',
            'repeatability':'repeat last evaluation with identical incoming state; exact graph excluding graph runtime_seconds, governed sii_evidence, supplied_reference, and returned states',
            'historical':'optional unchanged preexisting synthetic CHW source; first 576 rows fixed reference; 58 nonoverlapping 288-row windows; all 12 signals',
            'limitations':['same author designed and scored cases','controlled results are not field accuracy','finite noisy control sample; no calibrated population error rate','temporal windows not statistical independence claims']}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--output',type=Path,required=True); ap.add_argument('--freeze',type=Path,required=True); ap.add_argument('--historical',type=Path)
    a=ap.parse_args(); a.output.mkdir(parents=True,exist_ok=True)
    if (a.output/'cases.jsonl.gz').exists(): raise RuntimeError('refuse_to_overwrite_results')
    check_freeze(a.freeze); spec=plan(); write(a.output/'plan.json',spec)
    # Serialized protocol is sealed before new case execution.
    write(a.output/'protocol-seal.json',{'plan_sha256':hashlib.sha256((a.output/'plan.json').read_bytes()).hexdigest(),'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'sealed_at':datetime.now(timezone.utc).isoformat()})
    from app.engine.sii_engine import evaluate_sii
    summaries=[]; total=0
    def semantic(out):
        graph=copy.deepcopy(out.get('relationship_graph',{})); graph.pop('runtime_seconds',None)
        return {'graph':graph,'governed':out.get('analysis_result',{}).get('sii_evidence'), 'provenance':out.get('supplied_reference')}
    with tempfile.TemporaryDirectory(prefix='neraium-prize-') as runtime, gzip.open(a.output/'cases.jsonl.gz','wt',encoding='utf8') as raw:
        os.environ['NERAIUM_RUNTIME_DIR']=runtime
        def call(case_id,index,kwargs,repeat=False):
            nonlocal total
            before=copy.deepcopy(kwargs); started=time.perf_counter(); total+=1
            record={'case_id':case_id,'window':index,'repeat':repeat,'input':before,'input_sha256':digest(before)}
            try:
                out=evaluate_sii(**kwargs); record['output']=out
            except Exception as exc:
                out=None; record['exception']={'type':type(exc).__name__,'message':str(exc)}
            record['wall_seconds']=time.perf_counter()-started; record['input_unchanged']=kwargs==before
            raw.write(json.dumps(record,sort_keys=True,default=str)+'\n'); raw.flush()
            return out,record
        for ci,c in enumerate(spec['cases']):
            ref=rows(c['seed'],0,c['base'],noisy=c.get('noisy',False)); state=recurrence=None; observations=[]
            for day,delta in enumerate(c['deltas'],1):
                cur=rows(c['seed'],day,c['base']+delta,noisy=c.get('noisy',False)); signals=PAIR[:]; kind=c.get('transform')
                if kind=='missing': cur[10][PAIR[0]]=None
                if kind=='nonfinite': cur[10][PAIR[0]]='NaN'
                if kind=='duplicate_time': cur[10]['timestamp']=cur[9]['timestamp']
                if kind=='reversed_time': cur.reverse()
                if kind=='too_short': cur=cur[:15]
                if kind=='irregular':
                    start=datetime.fromisoformat(cur[0]['timestamp'])
                    for i,r in enumerate(cur): r['timestamp']=(start+timedelta(minutes=5*i+i*i)).isoformat()
                if kind=='flatline':
                    for r in cur:r[PAIR[0]]=100.
                if kind=='outlier':cur[48][PAIR[1]]+=1000
                if kind=='level_compensation':
                    cur=rows(c['seed'],day,c['base'])
                    for r in cur:r[PAIR[0]]+=20 # pressure distribution held; drive/output offset only
                if kind=='response_change':
                    cur=rows(c['seed'],day,.2) # output marginal variance held, relationship changed
                if kind=='new_context':
                    ref=[{**r,'equipment_stage':1.} for r in ref];cur=[{**r,'equipment_stage':2.} for r in cur];signals+=['equipment_stage']
                kw=args_for(ref,cur,signals);kw.update(relationship_persistence_state=state,relationship_recurrence_state=recurrence)
                out,record=call(c['id'],day,kw)
                if out:
                    graph=out.get('relationship_graph',{}); edges=graph.get('edges',[])
                    obs={'window':day,'temporal':any(e.get('temporal_persistence_supported',False) for e in edges),
                         'promoted':any(e.get('promoted_changed_edge',False) for e in edges),
                         'governed_persistent':any(e.get('persistent_relationship_change',False) for e in out.get('analysis_result',{}).get('sii_evidence',{}).get('relationship_changes',[])),
                         'edge_count':len(edges),'failed_modules':out.get('processing_trace',{}).get('modules_failed'),
                         'limited_modules':out.get('processing_trace',{}).get('modules_limited'),
                         'wall_seconds':record['wall_seconds'],'input_unchanged':record['input_unchanged'],
                         'edge_changes':[{k:e.get(k) for k in ['columns','baseline_correlation','current_correlation','recent_correlation','change_type','temporal_persistence_status','temporal_persistence_supporting_observations']} for e in edges]}
                    state=graph.get('relationship_persistence_state');recurrence=graph.get('relationship_recurrence_state')
                else:obs={'window':day,'exception':record['exception'],'input_unchanged':record['input_unchanged']}
                observations.append(obs)
            repeated,_=call(c['id'],len(c['deltas']),kw,repeat=True)
            summaries.append({'case':c,'observations':observations,'repeat_equal':semantic(out)==semantic(repeated) if out and repeated else out==repeated})
            if ci%20==0:print(f'completed {ci+1}/{len(spec["cases"])} sequences',flush=True)
        if a.historical:
            source=a.historical.read_bytes(); (a.output/'historical-input.csv.gz').write_bytes(gzip.compress(source,mtime=0))
            records=list(csv.DictReader(source.decode().splitlines())); signals=list(records[0])[1:]
            state=recurrence=None; hist=[]
            for index,start in enumerate(range(576,len(records),288)):
                cur=records[start:start+288]
                if len(cur)!=288:raise RuntimeError('partial_historical_window')
                kw=args_for(records[:576],cur,signals);kw.update(relationship_persistence_state=state,relationship_recurrence_state=recurrence)
                out,record=call('archived_synthetic_chw',index,kw)
                graph=out.get('relationship_graph',{}) if out else {}
                hist.append({'window':index,'exception':record.get('exception'),'failed_modules':out.get('processing_trace',{}).get('modules_failed') if out else None,'limited_modules':out.get('processing_trace',{}).get('modules_limited') if out else None,'temporal_edges':[e.get('columns') for e in graph.get('edges',[]) if e.get('temporal_persistence_supported')],'recurrence_edges':[e.get('columns') for e in graph.get('edges',[]) if e.get('recurrence_evidence',{}).get('recurrence_supported')],'wall_seconds':record['wall_seconds']})
                state=graph.get('relationship_persistence_state',state);recurrence=graph.get('relationship_recurrence_state',recurrence)
            write(a.output/'historical.json',{'source_sha256':hashlib.sha256(source).hexdigest(),'source_class':'preexisting controlled synthetic CHW','rows':len(records),'signals':signals,'observations':hist})
        write(a.output/'summary.json',{'engine_calls':total,'sequences':summaries,'freeze_verification':check_freeze(a.freeze)})
    print(f'finished {total} engine calls',flush=True)
if __name__=='__main__':main()
