"""Anonymous historical evaluation; never reads sealed/ or source labels."""
import csv,copy,gzip,hashlib,json,math,os,pathlib,sys,tempfile,time,traceback,datetime,concurrent.futures
R=pathlib.Path(__file__).resolve().parent
INPUT=R.parents[1]/"lbnl-blind-2026"/"raw"
ROOT=R.parents[3]
sys.path.insert(0,str(R))
from engine_adapter import EngineAdapter
from checkpoint_codec import read as read_checkpoint, write as write_checkpoint

def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def dump(p,x):
 p.parent.mkdir(parents=True,exist_ok=True)
 if p.suffix=='.gz':
  with gzip.open(p,'wt') as f:json.dump(x,f,separators=(',',':'),allow_nan=False)
 else:p.write_text(json.dumps(x,indent=2,allow_nan=False)+'\n')
def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def check_source():
 f=json.loads((R/'freeze.json').read_text());assert all(sha(ROOT/p)==v for p,v in f['tracked_file_sha256'].items())
 assert sha(R/'protocol.json')==json.loads((R/'protocol-seal.json').read_text())['sha256']
def read_hourly(name):
 output=INPUT/'hourly'/f'{name}.csv'
 assert output.is_file()
 with output.open(newline='') as f:
  reader=csv.DictReader(f);columns=reader.fieldnames[1:];rows=list(reader)
 return columns,rows

def run_case(case,mode='primary'):
 check_source();starttime=time.perf_counter();out=R/mode/case
 if (out/'complete.json').exists():
  print(mode,case,'reusing complete preserved sequence',flush=True);return case
 cols,rows=read_hourly(case);rcols,ref=read_hourly('REFERENCE');assert cols==rcols
 prot=json.loads((R/'protocol.json').read_text());units=json.loads((R/'units.json').read_text())
 ref=[r for r in ref if '2018-01-01 00:00:00'<=r['Datetime']<prot['comparison_start']]
 groups=[cols[1:][i:i+32] for i in range(0,len(cols)-1,32)]
 summary=[]
 with tempfile.TemporaryDirectory(prefix='neraium-lbnl-') as runtime:
  os.environ['NERAIUM_RUNTIME_DIR']=runtime;engine=EngineAdapter.load(str(ROOT))
  for groupno,signals in enumerate(groups,1):
   selected=['Datetime']+signals;state=rec=None;previous=None
   def qualify(rr):
    valid=[];positions=[];excluded=[]
    for row in rr:
     bad=[]
     for c in signals:
      try:ok=bool(row[c].strip()) and math.isfinite(float(row[c]))
      except (ValueError,OverflowError):ok=False
      if not ok:bad.append(c)
     if bad:excluded.append({'source_row':int(row['source_row']),'columns':bad})
     else:valid.append({c:row[c] for c in selected});positions.append(int(row['source_row']))
    return valid,positions,excluded
   reference,rpos,rex=qualify(ref)
   start=datetime.datetime.fromisoformat(prot['comparison_start']);end=datetime.datetime.fromisoformat(prot['comparison_end_exclusive']);index=0
   while start<end:
    stop=min(start+datetime.timedelta(days=prot['step_days']),end);a=str(start);b=str(stop)
    comp,cpos,cex=qualify([r for r in rows if a<=r['Datetime']<b]);assert not reference or not comp or reference[-1]['Datetime']<comp[0]['Datetime']
    incoming=digest([state,rec])
    existing=list(out.glob(f'B{groupno}_{index:03d}.*.gz'))
    if existing:
     assert len(existing)==1
     cp=read_checkpoint(existing[0]);assert cp['incoming_state_sha256']==incoming and cp['previous_checkpoint_sha256']==previous
     assert cp['reference_source_rows']==rpos and cp['comparison_source_rows']==cpos and cp['start']==a and cp['end_exclusive']==b
     if cp['result'] is not None:
      graph=cp['result']['relationship_graph'];state=copy.deepcopy(graph['relationship_persistence_state']);rec=copy.deepcopy(graph['relationship_recurrence_state'])
     assert cp['outgoing_state_sha256']==digest([state,rec]);previous=sha(existing[0]);summary.append({'block':groupno,'index':index,'error':cp['error'] and cp['error']['message'],'seconds':cp['elapsed_seconds'],'reused_frozen_prefix':True})
     start=stop;index+=1;continue
    result=None;error=None;beg=time.perf_counter()
    try:
     result=engine.evaluate_pair(columns=selected,reference_rows=copy.deepcopy(reference),comparison_rows=comp,numeric_profiles=[{'column':c,'numeric_ratio':1.0,'missing_count':0,'non_numeric_count':0} for c in signals],timestamp_column='Datetime',signal_units={c:units[c] for c in signals},relationship_persistence_state=copy.deepcopy(state),relationship_recurrence_state=copy.deepcopy(rec))
     graph=result['relationship_graph'];state=copy.deepcopy(graph['relationship_persistence_state']);rec=copy.deepcopy(graph['relationship_recurrence_state'])
    except Exception as e:error={'type':type(e).__name__,'message':str(e),'traceback':traceback.format_exc()}
    record={'case_id':case,'block':groupno,'index':index,'start':a,'end_exclusive':b,'reference_source_rows':rpos,'comparison_source_rows':cpos,'reference_excluded':rex,'comparison_excluded':cex,'incoming_state_sha256':incoming,'outgoing_state_sha256':digest([state,rec]),'previous_checkpoint_sha256':previous,'result':result,'error':error,'elapsed_seconds':time.perf_counter()-beg}
    path=out/f'B{groupno}_{index:03d}.pkl.gz';write_checkpoint(path,record);previous=sha(path)
    summary.append({'block':groupno,'index':index,'error':error and error['message'],'seconds':record['elapsed_seconds']})
    if index%10==0:print(mode,case,groupno,index,'error' if error else 'returned',round(time.perf_counter()-starttime,1),flush=True)
    start=stop;index+=1
 dump(out/'complete.json',{'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'wall_seconds':time.perf_counter()-starttime,'calls':summary,'engine':engine.provenance,'hourly_sha256':sha(INPUT/'hourly'/f'{case}.csv')});check_source()
 return case

def main():
 mode=sys.argv[1] if len(sys.argv)>1 else 'primary';check_source()

 if mode=='primary':
  assert not (R/'analytical-output-freeze.json').exists()
  cases=['CASE_001','CASE_022']
 else:
  assert (R/'analytical-output-freeze.json').exists();cases=['CASE_001','CASE_022']
 read_hourly('REFERENCE')
 dump(R/f'{mode}-execution-start.json',{'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'runner_sha256':sha(pathlib.Path(__file__)),'adapter_sha256':sha(R/'engine_adapter.py'),'codec_sha256':sha(R/'checkpoint_codec.py'),'protocol_sha256':sha(R/'protocol.json'),'units_sha256':sha(R/'units.json'),'runtime_env':{k:v for k,v in os.environ.items() if k.startswith(('OMP_','OPENBLAS_','MKL_','NUMEXPR_','PYTHONHASHSEED'))},'cases':cases})
 with concurrent.futures.ProcessPoolExecutor(max_workers=2) as pool:
  futures=[pool.submit(run_case,c,mode) for c in cases]
  for f in futures:print('FINISHED',f.result(),flush=True)
 check_source();dump(R/('analytical-output-freeze.json' if mode=='primary' else 'repeat-output-freeze.json'),{'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'ground_truth_labels_used':False,'tracked_sources_unchanged':True,'files':{str(p.relative_to(R)):sha(p) for p in sorted((R/mode).rglob('*')) if p.is_file()}})
if __name__=='__main__':main()
