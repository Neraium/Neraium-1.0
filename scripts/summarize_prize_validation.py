#!/usr/bin/env python3
"""Read-only scorer; never calls or changes the engine. All denominators explicit."""
import gzip,json,sys,collections,statistics,hashlib,math,xml.etree.ElementTree as ET
from pathlib import Path
from validate_prize import write

def main():
    root=Path(sys.argv[1]);summary=json.loads((root/'battery/summary.json').read_text()); groups=collections.defaultdict(list)
    for s in summary['sequences']:groups[s['case']['family']].append(s)
    aggregate={'engine_calls':summary['engine_calls'],'sequence_count':len(summary['sequences']),'primary_generated_windows':sum(len(s['observations']) for s in summary['sequences']), 'families':{},'sensitivity':[], 'stress':[], 'repeated_equal':sum(s['repeat_equal'] for s in summary['sequences'])}
    for family,items in groups.items():
        obs=[o for s in items for o in s['observations']]
        aggregate['families'][family]={'sequences':len(items),'windows':len(obs),'sequences_with_temporal_support':sum(any(o.get('temporal') for o in s['observations']) for s in items),'temporal_windows':sum(bool(o.get('temporal')) for o in obs),'promoted_windows':sum(bool(o.get('promoted')) for o in obs),'governed_persistent_windows':sum(bool(o.get('governed_persistent')) for o in obs),'exceptions':sum('exception' in o for o in obs)}
    for mag in [0,.05,.1,.15,.2,.25,.3]:
        selected=[s for s in groups['sensitivity'] if s['case']['magnitude']==mag]
        aggregate['sensitivity'].append({'magnitude':mag,'sequences':len(selected),'temporal_final':sum(bool(s['observations'][-1].get('temporal')) for s in selected),'promoted_final':sum(bool(s['observations'][-1].get('promoted')) for s in selected),'first_supported_windows':[next((o['window'] for o in s['observations'] if o.get('temporal')),None) for s in selected]})
    for s in groups['stress']:
        aggregate['stress'].append({'case':s['case']['id'],'windows':len(s['observations']),'exceptions':[o.get('exception') for o in s['observations'] if 'exception' in o],'temporal_windows':[o['window'] for o in s['observations'] if o.get('temporal')],'promoted_windows':[o['window'] for o in s['observations'] if o.get('promoted')]})
    aggregate['recovery_post_return_temporal_windows']=sum(bool(o.get('temporal')) for s in groups['recovery'] for o in s['observations'][8:])
    truth=json.loads((root/'prior-evidence/ground-truth.json').read_text())['scenarios'];targets={tuple(sorted(v['pair'])):k for k,v in truth.items()}
    historical={k:{'kind':v['kind'],'pair':v['pair'],'temporal_windows':[],'recurrence_windows':[],'promoted_windows':[],'governed_persistent_windows':[]} for k,v in truth.items()}
    failed=collections.Counter();limited=collections.Counter();errors=collections.Counter();statuses=collections.Counter();mutations=[];historical_extra=[];stress_details={};calls=0;prim=0;nonfinite=[];hash_mismatches=[]
    repeat_counts=collections.Counter(); previous=None
    def invalid_numbers(value):
        if isinstance(value,float):return not math.isfinite(value)
        if isinstance(value,dict):return any(invalid_numbers(v) for v in value.values())
        if isinstance(value,list):return any(invalid_numbers(v) for v in value)
        return False
    with gzip.open(root/'battery/cases.jsonl.gz','rt') as raw:
        for line in raw:
            r=json.loads(line);calls+=1
            if not r.get('input_unchanged'):mutations.append([r['case_id'],r['window']])
            expected=hashlib.sha256(json.dumps(r['input'],sort_keys=True,separators=(',',':'),default=str).encode()).hexdigest()
            if expected!=r['input_sha256']:hash_mismatches.append([r['case_id'],r['window']])
            if r.get('repeat'):
                if 'exception' in r:
                    repeat_counts['rejected_repeats']+=1
                    repeat_counts['identical_rejection']+=int(r['exception']==previous.get('exception'))
                else:repeat_counts['successful_repeats']+=1
                continue
            previous=r
            if invalid_numbers(r.get('output')):nonfinite.append([r['case_id'],r['window']])
            prim+=1
            if 'exception' in r:errors[r['exception']['message']]+=1;continue
            out=r['output'];statuses[str(out.get('status'))]+=1;trace=out.get('processing_trace',{})
            for x in trace.get('modules_failed',[]):failed[str(x)]+=1
            for x in trace.get('modules_limited',[]):limited[str(x)]+=1
            if r['case_id'] in [s['case']['id'] for s in groups['stress']]:
                stress_details[r['case_id']]={'operating_modes':out.get('operating_modes'),'graph_status':out.get('relationship_graph',{}).get('status'),'analysis_classification':out.get('analysis_result',{}).get('finding_classification'),'signal_drift':out.get('signal_drift'),'uncertainty':out.get('uncertainty')}
            if r['case_id']!='archived_synthetic_chw':continue
            for e in out.get('relationship_graph',{}).get('edges',[]):
                pair=tuple(sorted(e['columns']));key=targets.get(pair)
                flags={'temporal_windows':e.get('temporal_persistence_supported'),'recurrence_windows':e.get('recurrence_evidence',{}).get('supported'),'promoted_windows':e.get('promoted_changed_edge')}
                if key:
                    for endpoint,flag in flags.items():
                        if flag:historical[key][endpoint].append(r['window'])
                elif any(flags.values()):historical_extra.append({'window':r['window'],'pair':list(pair),'flags':flags})
            for e in out.get('analysis_result',{}).get('sii_evidence',{}).get('relationship_changes',[]):
                key=targets.get(tuple(sorted(e.get('columns',[]))))
                if key and e.get('persistent_relationship_change'):historical[key]['governed_persistent_windows'].append(r['window'])
    aggregate.update(repeat_counts=dict(repeat_counts),nonfinite_output_records=nonfinite,raw_calls_verified=calls,primary_calls=prim,input_mutations=mutations,input_hash_mismatches=hash_mismatches,primary_exception_counts=dict(errors),primary_module_failures=dict(failed),primary_module_limitations=dict(limited),primary_statuses=dict(statuses),historical_scenarios=historical,historical_other_promotions=historical_extra)
    write(root/'stress-details.json',stress_details)
    # Historical summary in runner used a nonexistent recurrence_supported key.
    # The full raw engine field 'supported' is authoritative and is scored above.
    aggregate['reporting_note']='Runner historical.json recurrence_edges uses an incorrect field name; do not use it. This scorer reads raw recurrence_evidence.supported; original outputs and runner retained unchanged.'
    if (root/'ingestion/summary.json').exists():
        ingestion=json.loads((root/'ingestion/summary.json').read_text())['cases']
        aggregate['ingestion']=[{'case':r['case'],'rows':r.get('rows'),'drift_status':r.get('drift_status'),'exception':r.get('exception'),'quality_rating':r.get('data_quality',{}).get('reliability_rating'),'data_confidence':r.get('data_quality',{}).get('data_confidence',{}).get('rating'),'gate':r.get('data_quality',{}).get('analysis_gate_state'),'finding_classes':[x.get('finding_class',x.get('classification',{}).get('type')) for x in r.get('analysis_result',{}).get('insights',[])],'insights':len(r.get('analysis_result',{}).get('insights',[])),'conditions':len(r.get('analysis_result',{}).get('conditions',[])),'wall_seconds':r['wall_seconds']} for r in ingestion]
    if (root/'performance/performance.json').exists():
        perf=json.loads((root/'performance/performance.json').read_text());g=collections.defaultdict(list)
        for r in perf['measurements']:g[(r['case'],r['path'])].append(r)
        aggregate['performance']=[{'case':k[0],'path':k[1],'repetitions':len(v),'wall_median_seconds':statistics.median(x['wall_seconds'] for x in v),'wall_min_seconds':min(x['wall_seconds'] for x in v),'wall_max_seconds':max(x['wall_seconds'] for x in v),'cpu_median_seconds':statistics.median(x['cpu_seconds'] for x in v),'semantic_hash_count':len({x['semantic_fingerprint'] for x in v}),'peak_rss_bytes':max(x['peak_process_rss_bytes'] for x in v)} for k,v in g.items()]
    if (root/'regression.xml').exists():
        tree=ET.parse(root/'regression.xml');suites=list(tree.getroot().iter('testsuite'));aggregate['regression']={'suites':[s.attrib for s in suites],'failures':[{'name':t.attrib,'failure':f.text} for t in tree.iter('testcase') for f in t if f.tag in ['failure','error']],'skips':[{'name':t.attrib,'reason':s.attrib} for t in tree.iter('testcase') for s in t if s.tag=='skipped']}
    write(root/'assessment.json',aggregate)
    print(json.dumps({k:v for k,v in aggregate.items() if k not in ['regression','stress','historical_other_promotions']},indent=2))
if __name__=='__main__':main()
