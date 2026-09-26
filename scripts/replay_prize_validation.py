#!/usr/bin/env python3
"""Verify recorded chronological state and replay fixed cases in a fresh process."""
import copy,gzip,json,os,sys,tempfile
from pathlib import Path
from validate_prize import check_freeze,digest,write

def semantic(out):
    graph=copy.deepcopy(out.get('relationship_graph',{}));graph.pop('runtime_seconds',None)
    return {'graph':graph,'governed':out.get('analysis_result',{}).get('sii_evidence'),'provenance':out.get('supplied_reference')}

def main():
    root=Path(sys.argv[1]);check_freeze(root/'freeze.json')
    selected={('grid_0.65_1_0.2_0',8),('stationary_noise_0',8),('new_context',8),('archived_synthetic_chw',49)}
    records=[];states={};issues=[];count=0
    for line in gzip.open(root/'battery/cases.jsonl.gz','rt'):
        r=json.loads(line)
        if r.get('repeat'):continue
        key=r['case_id'];kw=r['input'];incoming=[kw.get('relationship_persistence_state'),kw.get('relationship_recurrence_state')]
        if incoming!=states.get(key,[None,None]):issues.append({'case':key,'window':r['window'],'issue':'state_chain_mismatch'})
        if digest(kw)!=r['input_sha256']:issues.append({'case':key,'window':r['window'],'issue':'input_hash_mismatch'})
        if 'output' in r:
            graph=r['output'].get('relationship_graph',{});states[key]=[graph.get('relationship_persistence_state'),graph.get('relationship_recurrence_state')]
        if (key,r['window']) in selected:records.append(r)
        count+=1
    results=[]
    with tempfile.TemporaryDirectory(prefix='prize-replay-') as tmp:
        os.environ['NERAIUM_RUNTIME_DIR']=tmp
        from app.engine.sii_engine import evaluate_sii
        for r in records:
            try:
                out=evaluate_sii(**r['input']);result={'case':r['case_id'],'window':r['window'],'expected_sha256':digest(semantic(r['output'])),'actual_sha256':digest(semantic(out)),'equal':semantic(out)==semantic(r['output'])}
            except Exception as exc:result={'case':r['case_id'],'window':r['window'],'exception':str(exc),'equal':False}
            results.append(result)
    write(root/'replay-verification.json',{'primary_records_checked':count,'chain_and_hash_issues':issues,'selected_cases_requested':len(selected),'selected_cases_found':len(records),'fresh_process_replays':results,'scope':'exact graph minus runtime_seconds, governed sii_evidence and supplied_reference; complete outputs retained in original raw stream; no general full-output byte equality claim','freeze_verification':check_freeze(root/'freeze.json')})
    if issues or len(records)!=len(selected) or not all(r['equal'] for r in results):raise SystemExit(1)
if __name__=='__main__':main()
