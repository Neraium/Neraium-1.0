"""Predefined v2 exact semantic comparison; never opens case labels."""
import json, pathlib, sys, hashlib, datetime
R=pathlib.Path(__file__).resolve().parent
ROOT=R.parents[3]
sys.path[:0]=[str(ROOT/'backend'),str(R)]
from checkpoint_codec import read
from app.services.output_semantics import semantic_content, canonical_json, semantic_digest
from run_analysis import check_source, sha, dump, INPUT
def differences(a,b,path=''):
 if type(a)!=type(b):return [path]
 if isinstance(a,dict):
  out=[]
  for k in sorted(a.keys()|b.keys()):
   out.extend([path+'/'+k] if k not in a or k not in b else differences(a[k],b[k],path+'/'+k))
  return out
 if isinstance(a,list):
  out=[] if len(a)==len(b) else [path+'/length']
  for i,(x,y) in enumerate(zip(a,b)):out.extend(differences(x,y,path+'/'+str(i)))
  return out
 return [] if a==b else [path]
def main():
 check_source()
 for mode,seal in [('primary','analytical-output-freeze.json'),('repeat','repeat-output-freeze.json')]:
  frozen=json.loads((R/seal).read_text())
  assert all(sha(R/p)==h for p,h in frozen['files'].items())
 rows=[]
 for case in ['CASE_001','CASE_022']:
  for a in sorted((R/'primary'/case).glob('B*.pkl.gz')):
   b=R/'repeat'/case/a.name
   left,right=read(a),read(b)
   row={'case_id':case,'checkpoint':a.name,'errors':[left['error'],right['error']]}
   for name,key in [('semantic','analysis_result'),('graph','relationship_graph'),('source','supplied_reference'),('whole_result',None)]:
    x,y=left['result'],right['result']
    if key:x,y=x[key],y[key]
    sx,sy=semantic_content(x),semantic_content(y)
    row[name+'_hashes']=[semantic_digest(x),semantic_digest(y)]
    row[name+'_match']=canonical_json(sx)==canonical_json(sy)
    if not row[name+'_match']:row[name+'_differences']=differences(sx,sy)
   row['state_hashes']=[left['outgoing_state_sha256'],right['outgoing_state_sha256']]
   row['state_match']=row['state_hashes'][0]==row['state_hashes'][1]
   old=list((INPUT/'primary'/case).glob(a.name.replace('.pkl.gz','.*.gz')))
   assert len(old)==1
   v1graph=read(old[0])['result']['relationship_graph']
   v1graph={k:v for k,v in v1graph.items() if k!='runtime_seconds'}
   row['v1_graph_match']=canonical_json(v1graph)==canonical_json(semantic_content(left['result']['relationship_graph']))
   if not row['v1_graph_match']:row['v1_graph_differences']=differences(v1graph,semantic_content(left['result']['relationship_graph']))
   rows.append(row)
   if len(rows)%60==0:print('compared',len(rows),flush=True)
 assert len(rows)==720
 dump(R/'comparisons.json',rows)
 totals={key:sum(bool(row[key]) for row in rows) for key in ['semantic_match','graph_match','state_match','source_match','whole_result_match','v1_graph_match']}
 dump(R/'evaluation.json',{'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'comparisons':len(rows),'matches':totals,'errors':sum(bool(e) for r in rows for e in r['errors']),'runtime_contract_sha256':sha(ROOT/'backend/app/services/output_semantics.py')})
 print(totals,flush=True)
 check_source()
if __name__=='__main__':main()
