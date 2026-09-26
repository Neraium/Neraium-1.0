#!/usr/bin/env python3
"""Integrity checks and fixed first/middle/last fresh-process evidence repeats."""
import json,csv,hashlib,gzip,copy,sys,os,tempfile,time
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1];RAW=ROOT/'docs/validation/wastewater-real-2026/raw';sys.path.insert(0,str(ROOT/'backend'))
def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def semantic(r):
 g=copy.deepcopy(r['relationship_graph']);g.pop('runtime_seconds',None)
 return {'graph':g,'governed':r['analysis_result']['sii_evidence'],'supplied_reference':r['supplied_reference']}
def main():
 assert (RAW/'analytical-output-freeze.json').exists()
 if (RAW/'repeatability.json').exists():raise RuntimeError('No overwrite')
 rows=list(csv.DictReader((RAW/'normalized.csv').open()));original=list(csv.DictReader(open('/home/ubuntu/Data.csv')));assert len(rows)==len(original)
 for a,b in zip(original,rows):
  assert all(a[k]==b[k] for k in a if k!='Time')
  assert datetime.strptime(a['Time'],'%m/%d/%Y %I:%M:%S %p')==datetime.strptime(b['Time'],'%Y-%m-%d %H:%M:%S')
 config=json.loads((RAW/'config.json').read_text());columns=list(rows[0]);refprov=json.loads((RAW/'reference-provenance.json').read_text());ref=[rows[i-1] for i in refprov['source_row_numbers']];states=None;rec=None;results=[];checked=0
 from app.engine.sii_engine import evaluate_sii
 with tempfile.TemporaryDirectory(prefix='neraium-ww-repeat-') as tmp,gzip.open(RAW/'repeat-outputs.jsonl.gz','wt') as output:
  os.environ['NERAIUM_RUNTIME_DIR']=tmp
  for p in sorted((RAW/'checkpoints').glob('[0-9][0-9][0-9].json')):
   cp=json.loads(p.read_text());r=cp['result'];a=cp['attempt'];i=a['index']
   if r is None:continue
   cur=[rows[i-1] for i in a['input_provenance']['source_row_numbers']]
   for role,data in [('reference',ref),('comparison',cur)]:assert digest({'columns':columns,'units':config['signal_units'],'rows':data})==r['supplied_reference'][role]['input_hash']
   checked+=1
   if i in [0,126,252]:
    kwargs={'columns':columns,'reference_rows':ref,'comparison_rows':cur,'numeric_profiles':[{'column':c,'numeric_ratio':1.0,'missing_count':0,'non_numeric_count':0} for c in columns[1:]],'timestamp_column':'Time','signal_units':config['signal_units'],'relationship_persistence_state':states,'relationship_recurrence_state':rec}
    before=copy.deepcopy(kwargs);t=time.perf_counter();repeated=evaluate_sii(**kwargs)
    results.append({'window':i,'equal':semantic(r)==semantic(repeated),'original_hash':digest(semantic(r)),'repeat_hash':digest(semantic(repeated)),'input_unchanged':kwargs==before,'seconds':time.perf_counter()-t})
    output.write(json.dumps({'window':i,'input':before,'output':repeated})+'\n')
   states=r['relationship_graph']['relationship_persistence_state'];rec=r['relationship_graph']['relationship_recurrence_state']
 freeze=json.loads((RAW/'freeze.json').read_text());unchanged=all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in freeze['files_sha256'].items());assert unchanged
 record={'checked_input_hash_windows':checked,'numeric_cells_and_source_order_preserved':True,'timestamp_transformation_verified':True,'source_unchanged':hashlib.sha256(Path(freeze['source_path']).read_bytes()).hexdigest()==freeze['source_sha256'],'production_source_unchanged':unchanged,'repeat_scope':'Full relationship graph excluding runtime_seconds, governed sii_evidence, supplied_reference; ordered input dictionaries retained. Fresh process from original run; each selected window uses its original incoming states.','repeats':results,'finished_at':datetime.now(timezone.utc).isoformat()}
 (RAW/'repeatability.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record,indent=2))
if __name__=='__main__':main()
