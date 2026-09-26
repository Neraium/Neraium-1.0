#!/usr/bin/env python3
"""Blind chronological validation orchestration; uses unchanged historical wrapper."""
import csv,hashlib,json,os,sys,tempfile,time
from pathlib import Path
from datetime import datetime,timedelta,timezone
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/validation/wastewater-real-2026'; RAW=OUT/'raw'
WRAPPER=Path('/home/ubuntu/Neraium-Historical-Analysis')
sys.path.insert(0,str(WRAPPER/'src'))
def h(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,indent=2,default=str)+'\n')
def main():
 if (RAW/'protocol.json').exists():raise RuntimeError('Refuse to overwrite run; reproduce in a fresh package directory')
 freeze=json.loads((RAW/'freeze.json').read_text());source=Path(freeze['source_path'])
 assert h(source)==freeze['source_sha256']
 assert all(h(ROOT/p)==v for p,v in freeze['files_sha256'].items())
 normalized=RAW/'normalized.csv'
 with source.open(newline='') as f,normalized.open('w',newline='') as g:
  reader=csv.DictReader(f);columns=reader.fieldnames;writer=csv.DictWriter(g,fieldnames=columns);writer.writeheader()
  first=last=None
  for row in reader:
   t=datetime.strptime(row['Time'],'%m/%d/%Y %I:%M:%S %p');first=first or t;last=t
   row['Time']=t.strftime('%Y-%m-%d %H:%M:%S');writer.writerow(row)
 refend=first+timedelta(days=7);end=refend
 while end<=last:end+=timedelta(days=1)
 config={'reference_rows':2016,'comparison_rows':288,'step_rows':288,'signal_units':{c:None for c in columns[1:]}}
 write(RAW/'config.json',config)
 protocol={'sealed_at':datetime.now(timezone.utc).isoformat(),'source_sha256':h(source),'normalized_sha256':h(normalized),'runner_sha256':h(__file__),'wrapper_files':{str(p.relative_to(WRAPPER)):h(p) for p in (WRAPPER/'src').rglob('*.py')},'reference_start':first.isoformat(),'reference_end_exclusive':refend.isoformat(),'end_exclusive':end.isoformat(),'policy':'First seven source-clock days fixed reference; every subsequent one-day half-open interval, including final partial interval. All seven signals; no adaptive selection. Existing QualitySource complete-case validity exclusion. No units inferred, imputation, resampling, clipping, sorting, baseline resets or analytical overrides.','transformation':'Timestamp format only: %m/%d/%Y %I:%M:%S %p to %Y-%m-%d %H:%M:%S; source clock retained, no timezone asserted. CSV rewritten with same header order and verbatim numeric cell strings.','endpoints':'Graph temporal and recurrence support, promoted edges, governed persistent relationship flags and insights reported separately; consecutive support runs are descriptive bookkeeping, not new qualification.'}
 write(RAW/'protocol.json',protocol)
 from neraium_historical.config import load_config
 from neraium_historical.engine_adapter import EngineAdapter
 from neraium_historical.quality_source import QualitySource
 from neraium_historical.daily_replay import DailyReplay
 with tempfile.TemporaryDirectory(prefix='neraium-wastewater-') as tmp:
  os.environ['NERAIUM_RUNTIME_DIR']=tmp
  engine=EngineAdapter.load(str(ROOT));src=QualitySource(normalized,Path(tmp)/'index.sqlite',columns[1:],'Time')
  write(RAW/'quality-view.json',src.audit)
  replay=DailyReplay(src,engine,load_config(RAW/'config.json'),first,refend,end,RAW/'checkpoints')
  write(RAW/'reference-provenance.json',replay.reference_provenance)
  started=time.perf_counter()
  for i in range(replay.total):replay.get(i)
  write(RAW/'execution.json',{'wall_seconds':time.perf_counter()-started,'steps':replay.total,'finished_at':datetime.now(timezone.utc).isoformat()})
  src.close()
 assert h(source)==freeze['source_sha256']
 assert all(h(ROOT/p)==v for p,v in freeze['files_sha256'].items())
 write(RAW/'analytical-output-freeze.json',{'frozen_at':datetime.now(timezone.utc).isoformat(),'external_documentation_examined':False,'source_unchanged':True,'production_source_unchanged':True,'files':{str(p.relative_to(OUT)):h(p) for p in RAW.rglob('*') if p.is_file()}})
if __name__=='__main__':main()
