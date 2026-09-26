#!/usr/bin/env python3
"""Retain and describe the observed fresh-process replay discrepancy, without changing acceptance."""
import gzip,json,os,sys,tempfile
from pathlib import Path
from validate_prize import check_freeze,write,digest
from replay_prize_validation import semantic

def differences(a,b,path=''):
    if type(a)!=type(b):return [{'path':path,'before':a,'after':b}]
    if isinstance(a,dict):return [d for k in sorted(a.keys()|b.keys()) for d in differences(a.get(k),b.get(k),path+'/'+k)]
    if isinstance(a,list):
        if len(a)!=len(b):return [{'path':path+'/length','before':len(a),'after':len(b)}]
        return [d for i,(v,w) in enumerate(zip(a,b)) for d in differences(v,w,path+'/'+str(i))]
    return [] if a==b else [{'path':path,'before':a,'after':b}]

def main():
    root=Path(sys.argv[1]);check_freeze(root/'freeze.json')
    for line in gzip.open(root/'battery/cases.jsonl.gz','rt'):
        r=json.loads(line)
        if r['case_id']=='archived_synthetic_chw' and r['window']==49:break
    else:raise RuntimeError('case_missing')
    with tempfile.TemporaryDirectory(prefix='prize-discrepancy-') as tmp:
        os.environ['NERAIUM_RUNTIME_DIR']=tmp
        from app.engine.sii_engine import evaluate_sii
        out=evaluate_sii(**r['input'])
    with gzip.open(root/'replay-discrepancy-output.json.gz','wt') as f:json.dump({'input':r['input'],'output':out},f,sort_keys=True)
    diff=differences(semantic(r['output']),semantic(out))
    write(root/'replay-discrepancy.json',{'case':r['case_id'],'window':49,'original_sha256':digest(semantic(r['output'])),'diagnostic_sha256':digest(semantic(out)),'differences':diff,'difference_count':len(diff),'acceptance_unchanged':True})
    print(json.dumps(diff,indent=2))
if __name__=='__main__':main()
