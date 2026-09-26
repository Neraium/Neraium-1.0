#!/usr/bin/env python3
"""Read saved outputs; no detector calls and no new qualification rules."""
import json,csv,hashlib,collections
from pathlib import Path
from datetime import datetime
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'docs/validation/wastewater-real-2026'; RAW=OUT/'raw'
def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def main():
 assert (RAW/'analytical-output-freeze.json').exists(), 'Wait for analytical freeze'
 q=json.loads((RAW/'quality-view.json').read_text()); ref=json.loads((RAW/'reference-provenance.json').read_text())
 counts=collections.Counter();modules=collections.Counter();insights=collections.Counter();consequences=collections.Counter();contexts=collections.Counter();quality=collections.Counter();status=collections.Counter();temporal_status=collections.Counter();change_types=collections.Counter();pairs=collections.defaultdict(list);windows=[];rows=set(ref['source_row_numbers']);prev=None;state=rec=None;checks=[]
 edgefile=(RAW/'edge-results.jsonl').open('w'); insightfile=(RAW/'insights.jsonl').open('w')
 for p in sorted((RAW/'checkpoints').glob('[0-9][0-9][0-9].json')):
  cp=json.loads(p.read_text());a=cp['attempt'];r=cp['result'];i=a['index'];link=cp['handoff']
  assert cp['checkpoint_sha256']==digest({k:v for k,v in cp.items() if k!='checkpoint_sha256'})
  assert link['previous_checkpoint_sha256']==prev and link['incoming_states_sha256']==digest([state,rec]);prev=cp['checkpoint_sha256']
  counts['attempted_windows']+=1;status[a['status']]+=1;w={'index':i,'status':a['status'],'error':a.get('error'),'checkpoint':str(p.relative_to(OUT))}
  if r is None:windows.append(w);continue
  counts['returned_windows']+=1;prov=a['input_provenance'];assert not rows.intersection(prov['source_row_numbers']);rows.update(prov['source_row_numbers']);counts['comparison_rows']+=prov['row_count']
  w.update(start=prov['source_timestamps'][0],end=prov['source_timestamps'][-1],rows=prov['row_count'])
  assert ref['source_timestamps'][-1]<w['start']
  g=r['relationship_graph'];state=g['relationship_persistence_state'];rec=g['relationship_recurrence_state'];assert link['outgoing_states_sha256']==digest([state,rec])
  modules.update(r['processing_trace'].get('modules_limited',[]));counts['module_failures']+=len(r['processing_trace'].get('modules_failed',[]))
  gov=r['analysis_result']['sii_evidence'];gc=[x for x in gov.get('relationship_changes',[]) if x.get('persistent_relationship_change')];counts['governed_persistent_pair_windows']+=len(gc)
  w['governed_persistent']=gc;w['temporal_pairs']=[];w['recurring_pairs']=[]
  for e in g.get('edges',[]):
   pair=' / '.join(sorted(e['columns']));temporal=bool(e.get('temporal_persistence_supported')); recurring=bool(e.get('recurrence_evidence',{}).get('supported'));promoted=bool(e.get('promoted_changed_edge'))
   er={k:e.get(k) for k in ['columns','baseline_correlation','current_correlation','signed_correlation_delta','absolute_correlation_delta','change_type','single_window_change_type','relationship_importance_score','edge_displacement','eligible','edge_confidence','data_quality_factor','sample_sufficiency_factor','temporal_persistence_status','temporal_persistence_supporting_observations','temporal_persistence_supported','promoted_changed_edge','persistent_relationship_change','supporting_windows','first_supported_observation','latest_supported_observation','recurrence_evidence','operating_mode_context','data_confidence','sensor_health_context']};er.update(window=i,start=w['start'],end=w['end'],checkpoint=w['checkpoint'],governed_persistent=any(sorted(x.get('columns',[]))==sorted(e['columns']) for x in gc));edgefile.write(json.dumps(er)+'\n');pairs[pair].append(er)
   counts['evaluated_pair_windows']+=1;counts['eligible_pair_windows']+=bool(e.get('eligible'));counts['temporal_pair_windows']+=temporal;counts['recurrence_pair_windows']+=recurring;counts['promoted_pair_windows']+=promoted
   counts['changed_without_temporal_or_recurrence_pair_windows']+= e.get('change_type') not in (None,'stable','unchanged') and not temporal and not recurring
   temporal_status[e.get('temporal_persistence_status','absent')]+=1;change_types[e.get('change_type','absent')]+=1
   contexts[e.get('operating_mode_context',{}).get('match','absent')]+=1;quality[e.get('data_confidence',{}).get('rating','absent')]+=1
   if temporal:w['temporal_pairs'].append(pair)
   if recurring:w['recurring_pairs'].append(pair)
  counts['windows_with_temporal_support']+=bool(w['temporal_pairs']);counts['windows_with_recurrence_support']+=bool(w['recurring_pairs'])
  for ins in r['analysis_result']['insights']:
   insights[ins.get('classification',{}).get('type','absent')]+=1;consequences[ins.get('measurable_consequence',{}).get('status','absent')]+=1;insightfile.write(json.dumps({'window':i,'end':w['end'],'insight':ins})+'\n')
  windows.append(w)
 edgefile.close();insightfile.close()
 summary=[]
 for pair,ee in sorted(pairs.items()):
  out={'pair':pair,'evaluations':len(ee)}
  for label,key in [('temporal','temporal_persistence_supported'),('recurrence','recurrence_evidence'),('governed','governed_persistent'),('promoted','promoted_changed_edge')]:
   supported=[e for e in ee if (e[key].get('supported') if label=='recurrence' else e[key])];runs=[]
   for e in supported:
    if not runs or runs[-1][-1]['window']+1!=e['window']:runs.append([])
    runs[-1].append(e)
   out[label]={'pair_windows':len(supported),'first_support_time':supported[0]['end'] if supported else None,'runs':[{'first_window':run[0]['window'],'last_window':run[-1]['window'],'windows':len(run),'first_support_time':run[0]['end'],'last_support_time':run[-1]['end'],'support_observation_span_days':(datetime.fromisoformat(run[-1]['end'])-datetime.fromisoformat(run[0]['end'])).total_seconds()/86400,'baseline_correlation':run[0]['baseline_correlation'],'current_correlation_min':min(e['current_correlation'] for e in run),'current_correlation_max':max(e['current_correlation'] for e in run)} for run in runs]}
  summary.append(out)
 counts.update(source_rows=q['original_rows'],valid_complete_case_rows=q['valid_rows'],excluded_rows=q['excluded_rows'],reference_rows=ref['row_count'],unique_rows_analyzed=len(rows),distinct_pairs=len(pairs),distinct_temporal_pairs=sum(bool(p['temporal']['pair_windows']) for p in summary),distinct_recurring_pairs=sum(bool(p['recurrence']['pair_windows']) for p in summary),distinct_governed_persistent_pairs=sum(bool(p['governed']['pair_windows']) for p in summary))
 result={'counts':dict(counts),'window_status':dict(status),'limited_modules':dict(modules),'insight_categories':dict(insights),'consequence_status':dict(consequences),'pair_window_context':dict(contexts),'pair_window_quality':dict(quality),'temporal_status':dict(temporal_status),'change_types':dict(change_types),'pairs':summary,'windows':windows,'verification':{'checkpoint_hashes_and_state_chain':True,'nonoverlapping_rows':True,'no_future_reference':True,'all_valid_rows_analyzed':len(rows)==q['valid_rows']},'count_semantics':'Pair-window counts repeat relationships over time, not independent incidents. Changed/nonpersistent uses engine change_type excluding stable/unchanged and neither temporal nor recurrence; it does not assert a physical transient.'}
 (RAW/'assessment.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ['pairs','windows']},indent=2))
if __name__=='__main__':main()
