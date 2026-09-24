"""Production measurement only. No production monkeypatches or comparator exclusions."""
import os,sys,pathlib,json,time,math,csv,hashlib,gzip,resource,shutil,subprocess,statistics,platform,importlib.metadata,signal,copy
from datetime import datetime,timedelta,timezone
ROOT=pathlib.Path(__file__).resolve().parents[4]
OUT=ROOT/'docs/performance/production-processing-2026';RAW=OUT/'raw';RT=RAW/'runtime'
sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'tests')]
SIZES=[10000,100000,250000,500000,1000000,2500000,5000000]
THREADS={k:'1' for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']}
CONFIG={'warmups':1,'measured_runs':5,'sample_timeout_seconds':180,'peak_rss_limit_bytes':5*1024**3,'minimum_available_memory_bytes':1024**3,'minimum_free_disk_bytes':2*1024**3,'maximum_estimated_five_run_seconds':900,'window_count':100,'window_size':64,'threads':THREADS,'observation_definition':'one timestamped multivariate row; three numeric signal values per batch row; signal points = rows * 3','source_clock':'2026-01-01 UTC plus one minute per batch row','analytical_configuration':'production defaults; ingestion row cap fixed at 5000000 for every size; existing internal production module limits unchanged','comparator':'app.services.output_semantics.semantic_content/canonical_json only; no extra field exclusions; source ownership fixed; execution clocks not patched'}
def dump(p,v):p.write_text(json.dumps(v,indent=2,default=str)+'\n')
def mem():
 return {a.rstrip(':'):int(b)*1024 for a,b,*_ in (l.split() for l in pathlib.Path('/proc/meminfo').read_text().splitlines())}
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def verify():
 m=json.loads((ROOT/'docs/validation/current-product-integration/CANDIDATE_MANIFEST.json').read_text());bad=[f['path'] for f in m['production_files'] if sha(ROOT/f['path'])!=f['sha256']]
 assert not bad,bad
 return {'branch':subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip(),'base_commit':m['base_commit'],'candidate_tree':m['verified_current_candidate_tree'],'production_subtree':m['production_subtree'],'source_files_verified':len(m['production_files']),'manifest_sha256':sha(ROOT/'docs/validation/current-product-integration/CANDIDATE_MANIFEST.json')}
def rows(n):
 start=datetime(2026,1,1,tzinfo=timezone.utc)
 for i in range(n):
  load=50+12*math.sin(i/37)+3*math.cos(i/13);flow=80+load*1.7+math.sin(i/11);pressure=12+flow*.08+.1*math.cos(i/7)
  if i>=n*.7:pressure+=8+3*math.sin(i/5)
  yield {'timestamp':(start+timedelta(minutes=i)).isoformat(),'load_pct':f'{load:.8f}','flow_gpm':f'{flow:.8f}','pressure_psi':f'{pressure:.8f}'}
def save_output(path,v):
 from app.services.output_semantics import canonical_json
 with gzip.open(path,'wt') as f:f.write(canonical_json(v))
def walk(v):
 if isinstance(v,dict):
  yield v
  for x in v.values():yield from walk(x)
 elif isinstance(v,(list,tuple)):
  for x in v:yield from walk(x)
def counts(v,n):
 engine=v.get('sii_result',v) if isinstance(v,dict) else {};graph=engine.get('relationship_graph',{}) if isinstance(engine,dict) else {}
 governed=v.get('analysis_result',{}) if isinstance(v,dict) else {}
 if isinstance(v,dict) and v.get('output_semantics'):governed=v
 consequence=[x['measurable_consequence'] for x in walk(governed) if isinstance(x.get('measurable_consequence'),dict)]
 edges=graph.get('edges',graph.get('relationships',[]))
 return {'telemetry_observations':n,'signals':3,'signal_points':3*n,'timestamps':n,'relationship_edges_returned':len(edges) if isinstance(edges,(list,dict)) else None,'relationships_evaluated':graph.get('evaluated_relationship_count',graph.get('relationship_count')),'comparison_windows':1,'governed_outputs':len(governed.get('conditions',[]))+len(governed.get('insights',[])),'consequence_statuses':[x.get('status') for x in consequence],'consequence_reasons':[x.get('reason') for x in consequence],'modules_failed':engine.get('processing_trace',{}).get('modules_failed',[]),'module_statuses':engine.get('processing_trace',{}).get('module_statuses',{}),'graph_keys':list(graph),'result_keys':list(v) if isinstance(v,dict) else None}
def worker(kind,n,label):
 os.environ.update(THREADS);os.environ['NERAIUM_RUNTIME_DIR']=str(RT);os.environ['NERAIUM_PROCESS_ROLE']='all';os.environ['NERAIUM_MAX_INGESTION_ANALYSIS_ROWS']='5000000'
 # Each fresh process receives a freshly initialized, identically located local runtime.
 if RT.exists():shutil.rmtree(RT)
 RT.mkdir()
 from app.services import runtime_db,upload_jobs,sii_runner
 from app.services.dataset_scope import set_current_dataset_scope,build_dataset_scope
 from app.services.output_semantics import semantic_digest,semantic_content,canonical_json
 runtime_db.configure_runtime_dir(RT);upload_jobs.configure_runtime_dir(RT);sii_runner.configure_runtime_dir(RT)
 set_current_dataset_scope(build_dataset_scope(user_id='production-benchmark'));runtime_db.init_runtime_db()
 source=RT/'telemetry.csv';data=None; extra={};sample=f'{kind}-{n}-{label}'
 if kind in ['end_to_end','ingestion','baseline','core','persistence_context']:
  data=list(rows(n));columns=list(data[0]);numeric=columns[1:];profiles=[{'column':x,'constant_or_stuck':False,'missing_count':0,'non_numeric_count':0} for x in numeric]
  with source.open('w') as f:
   w=csv.DictWriter(f,fieldnames=columns);w.writeheader();w.writerows(data)
  extra['input_sha256']=sha(source)
 if kind=='end_to_end':
  from app.services.baseline_contracts import WORKFLOW_LEGACY_ANALYSIS
  upload_jobs.write_job('production-benchmark',{'job_id':'production-benchmark','dataset_id':'production-benchmark','workflow':WORKFLOW_LEGACY_ANALYSIS,'filename':'telemetry.csv'})
  def run():
   result=upload_jobs.process_csv_file(source,job_id='production-benchmark')
   status=upload_jobs.read_upload_status('production-benchmark')
   assert result.get('analysis_result'), 'missing governed analysis_result'
   assert result.get('evidence_persistence',{}).get('persisted'), 'missing persisted evidence'
   assert result.get('report_finalization',{}).get('state')=='complete',result.get('report_finalization')
   extra['terminal_status']=status;extra['finalization']=result.get('report_finalization');return result
 elif kind=='ingestion':
  from app.services.historical_ingestion import build_historical_ingestion
  run=lambda:build_historical_ingestion(source,dataset_id='production-benchmark',filename='telemetry.csv',max_analysis_rows=5000000)
 elif kind=='baseline':
  from app.services.behavioral_baseline import build_behavioral_baseline
  run=lambda:build_behavioral_baseline(job_id='production-benchmark',filename='telemetry.csv',columns=columns,rows=data,numeric_columns=numeric,timestamp_column='timestamp',row_count_total=n,numeric_profiles=profiles)
 elif kind in ['core','persistence_context']:
  from app.engine.sii_engine import evaluate_sii
  def evaluate(selected,ps=None,rs=None):return evaluate_sii(columns=columns,rows=selected,numeric_profiles=profiles,timestamp_column='timestamp',relationship_persistence_state=ps,relationship_recurrence_state=rs,config={'numeric_columns':numeric,'source_run_id':'production-benchmark'})
  if kind=='core':run=lambda:evaluate(data)
  else:
   # Establish predecessor outside timing; current window carries its returned states.
   predecessor=[dict(row,timestamp=(datetime.fromisoformat(row['timestamp'])-timedelta(minutes=n)).isoformat()) for row in data]
   prior=evaluate(predecessor);g=prior['relationship_graph'];ps=g['relationship_persistence_state'];rs=g['relationship_recurrence_state']
   extra['incoming_state_hash']=semantic_digest({'persistence':ps,'recurrence':rs});extra['incoming_state_bytes']=len(canonical_json({'persistence':ps,'recurrence':rs}).encode());run=lambda:evaluate(data,ps,rs)
 elif kind=='governance':
  from app.services.analysis_result_contract import build_analysis_result
  # Reuse the unchanged real 10k-row production source already captured by the end-to-end path.
  with gzip.open(RAW/'end_to_end-10000-warmup.output.json.gz','rt') as f:src=json.load(f)
  run=lambda:build_analysis_result(src)
  extra.update({'upstream_source':'end_to_end-10000-warmup.output.json.gz','upstream_source_sha256':sha(RAW/'end_to_end-10000-warmup.output.json.gz'),'scope':'actual contract/governance/consequence attachment from captured real production analysis; upstream processing excluded'})
 elif kind.startswith('consequence_'):
  from test_consequence_certification import source_result,START
  from app.services.analysis_result_contract import build_analysis_result
  case=kind.split('_',1)[1];src,window=source_result('synthetic-system',case,1)
  src['timestamp_profile']={'first_timestamp':START.isoformat(),'last_timestamp':(START+timedelta(hours=6)).isoformat()}
  run=lambda:build_analysis_result(src)
  extra.update({'fixture':'tests/test_consequence_certification.py::source_result','fixture_case':case,'fixture_rows':7,'fixture_signal_points':14,'synthetic_finding_from_existing_fixture':True,'scope':'contract and real consequence attachment; excludes telemetry ingestion and SII detection'})
 elif kind=='incremental':
  from test_sii_supplied_reference import source_clock_contract
  from app.engine.sii_engine import evaluate_sii
  args=source_clock_contract(64);prior=evaluate_sii(**args);graph=prior['relationship_graph'];ps0=graph['relationship_persistence_state'];rs0=graph['relationship_recurrence_state']
  windows=[]
  for i in range(100):
   a=source_clock_contract(64)
   for row in a['comparison_rows']:row['timestamp']=(datetime.fromisoformat(row['timestamp'])+timedelta(days=i+1)).strftime('%Y-%m-%d %H:%M:%S')
   windows.append(a)
  def run():
   ps,rs=ps0,rs0;outputs=[];samples=[]
   for i,a in enumerate(windows):
    incoming=semantic_digest({'persistence':ps,'recurrence':rs});t=time.perf_counter();c=time.process_time();result=evaluate_sii(**a,relationship_persistence_state=ps,relationship_recurrence_state=rs);elapsed=time.perf_counter()-t;cpu=time.process_time()-c
    graph=result['relationship_graph'];ps=graph['relationship_persistence_state'];rs=graph['relationship_recurrence_state'];state={'persistence':ps,'recurrence':rs}
    samples.append({'window':i,'observations':64,'reference_rows':64,'wall_seconds':elapsed,'cpu_seconds':cpu,'peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,'state_bytes':len(canonical_json(state).encode()),'incoming_state_hash':incoming,'outgoing_state_hash':semantic_digest(state),'counts':counts(result,64)})
    outputs.append(result)
   extra['windows']=samples;extra['bootstrap_excluded']=True;extra['state_continuity']=all(samples[i]['incoming_state_hash']==samples[i-1]['outgoing_state_hash'] for i in range(1,len(samples)));return outputs
 else:raise ValueError(kind)
 before=mem();started=time.perf_counter();cpu=time.process_time();output=run();wall=time.perf_counter()-started;cpu=time.process_time()-cpu;rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024
 semantic=semantic_content(output);digest=semantic_digest(output)
 result={'kind':kind,'workload_rows':n,'run':label,'wall_seconds':wall,'cpu_seconds':cpu,'peak_rss_bytes':rss,'memory_before':before,'observations_per_second':None if kind=='governance' else n/wall,'counts':counts(output,n),'semantic_digest':digest,**extra}
 if kind.startswith('consequence_'):result['counts'].update(telemetry_observations=7,signals=2,signal_points=14,timestamps=7)
 save_output(RAW/(sample+'.output.json.gz'),output);save_output(RAW/(sample+'.semantic.json.gz'),semantic)
 dump(RAW/(sample+'.json'),result)
def differences(a,b,path='',out=None):
 if out is None:out=[]
 if len(out)>=30:return out
 if type(a)!=type(b):out.append({'path':path,'before':str(a)[:180],'after':str(b)[:180]})
 elif isinstance(a,dict):
  for k in sorted(set(a)|set(b)):
   if k not in a or k not in b:out.append({'path':path+'/'+k,'missing_in':'before' if k not in a else 'after'})
   else:differences(a[k],b[k],path+'/'+k,out)
   if len(out)>=30:break
 elif isinstance(a,list):
  if len(a)!=len(b):out.append({'path':path,'before_length':len(a),'after_length':len(b)})
  for i,(x,y) in enumerate(zip(a,b)):
   differences(x,y,path+'/'+str(i),out)
   if len(out)>=30:break
 elif a!=b:out.append({'path':path,'before':a,'after':b})
 return out

def controller(supplement=False):
 candidate=verify(); env={**os.environ,**THREADS,'PYTHONHASHSEED':'0','PYTHONDONTWRITEBYTECODE':'1'}
 environment={'candidate':candidate,'cpu_model':next(l.split(':',1)[1].strip() for l in pathlib.Path('/proc/cpuinfo').read_text().splitlines() if l.startswith('model name')),'vcpus':os.cpu_count(),'cpu_affinity':sorted(os.sched_getaffinity(0)),'memory':mem(),'os':platform.platform(),'python':sys.version,'dependencies':{d.metadata['Name']:d.version for d in importlib.metadata.distributions()},'threads':THREADS,'storage':subprocess.check_output(['df','-T',str(ROOT)],text=True),'storage_device_details':subprocess.check_output(['lsblk','-o','NAME,TYPE,ROTA,SIZE,MODEL'],text=True),'configuration':CONFIG}
 dump(RAW/'supplement-environment.json' if supplement else OUT/'ENVIRONMENT.json',environment);dump(RAW/'configuration.json',CONFIG)
 results=json.loads((OUT/'RESULTS.json').read_text()) if supplement else {'candidate':candidate,'configuration':CONFIG,'classes':[]}
 tasks=[('end_to_end',SIZES),('ingestion',SIZES),('baseline',SIZES),('core',SIZES),('persistence_context',SIZES),('consequence_A',[7]),('consequence_B',[7]),('consequence_C',[7]),('incremental',[6400])]
 if supplement:tasks=[('governance',[10000])]
 for kind,sizes in tasks:
  stopped=None
  for n in sizes:
   rec={'kind':kind,'workload_rows':n,'runs':[],'status':'pending'};results['classes'].append(rec)
   if stopped:rec.update(status='not_run',reason=stopped);continue
   if mem()['MemAvailable']<CONFIG['minimum_available_memory_bytes'] or shutil.disk_usage(ROOT).free<CONFIG['minimum_free_disk_bytes']:
    stopped='preflight resource reserve';rec.update(status='resource_limit',reason=stopped);continue
   for label in ['warmup','1','2','3','4','5']:
    key=f'{kind}-{n}-{label}';print('START',key,flush=True);t=time.monotonic()
    with (RAW/(key+'.log')).open('w') as log:
     proc=subprocess.Popen([sys.executable,__file__,'worker',kind,str(n),label],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
     limit=None;observed=0
     while proc.poll() is None:
      time.sleep(.25)
      try:
       st=pathlib.Path(f'/proc/{proc.pid}/status').read_text();rss=int(next(l.split()[1] for l in st.splitlines() if l.startswith('VmRSS:')))*1024;observed=max(observed,rss)
      except (FileNotFoundError,StopIteration):pass
      if time.monotonic()-t>CONFIG['sample_timeout_seconds']:limit='180-second subprocess wall limit'
      if observed>CONFIG['peak_rss_limit_bytes']:limit='5 GiB RSS limit'
      if mem()['MemAvailable']<CONFIG['minimum_available_memory_bytes']:limit='1 GiB available memory reserve'
      if shutil.disk_usage(ROOT).free<CONFIG['minimum_free_disk_bytes']:limit='2 GiB disk reserve'
      if limit:
       os.killpg(proc.pid,signal.SIGTERM)
       try:proc.wait(timeout=5)
       except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
       break
    if proc.returncode or limit:
     rec.update(status='resource_limit' if limit else 'execution_failed',reason=limit or f'worker exit {proc.returncode}',failed_run=label,observed_process_seconds=time.monotonic()-t,observed_peak_rss_bytes=observed);stopped=rec['reason'];break
    sample=json.loads((RAW/(key+'.json')).read_text())
    if label=='warmup':
     rec['warmup']=sample
     if sample['wall_seconds']*5>CONFIG['maximum_estimated_five_run_seconds']:
      stopped='five-run cost exceeds 900 seconds';rec.update(status='cost_limit',reason=stopped,estimated_five_run_seconds=sample['wall_seconds']*5);break
    else:rec['runs'].append(sample)
    # Warm-up is also identical input and must agree. No mismatch is normalized away.
    if sample['semantic_digest']!=rec['warmup']['semantic_digest']:
     with gzip.open(RAW/f'{kind}-{n}-warmup.semantic.json.gz','rt') as f:a=json.load(f)
     with gzip.open(RAW/(key+'.semantic.json.gz'),'rt') as f:b=json.load(f)
     rec.update(status='semantic_mismatch',differences=differences(a,b),mismatch_run=label);stopped='semantic mismatch: class stopped';break
    rec['status']='running';dump(OUT/'RESULTS.json',results);print('DONE',key,round(sample['wall_seconds'],4),flush=True)
   if len(rec['runs'])==5 and rec['status']=='running':
    rec['status']='complete';rec['summary']={k:{'median':statistics.median(x[k] for x in rec['runs']),'minimum':min(x[k] for x in rec['runs']),'maximum':max(x[k] for x in rec['runs'])} for k in ['wall_seconds','cpu_seconds','peak_rss_bytes','observations_per_second'] if all(x.get(k) is not None for x in rec['runs'])}
   dump(OUT/'RESULTS.json',results);print('CLASS',kind,n,rec['status'],flush=True)
 verify();dump(OUT/'RESULTS.json',results)
if __name__=='__main__':
 if len(sys.argv)>1 and sys.argv[1]=='worker':worker(sys.argv[2],int(sys.argv[3]),sys.argv[4])
 else:controller(supplement=len(sys.argv)>1 and sys.argv[1]=='supplement')
