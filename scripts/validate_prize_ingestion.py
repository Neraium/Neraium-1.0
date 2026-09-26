#!/usr/bin/env python3
"""Unmodified upload-path robustness observations; not labeled field performance."""
import csv,gzip,hashlib,io,json,os,sys,tempfile,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from validate_prize import rows, check_freeze, write

def main():
    output=Path(sys.argv[1]);output.mkdir(parents=True,exist_ok=True)
    if (output/'uploads.jsonl.gz').exists():raise RuntimeError('refuse_overwrite')
    check_freeze(Path(sys.argv[2]))
    specs=['stable','noise','missing_1pct','missing_5pct','missing_20pct','missing_50pct','dropout','flatline','duplicate','out_of_order','irregular','outliers','relationship_change','level_compensation']
    write(output/'plan.json',{'cases':specs,'rows':1200,'seed':410,'endpoint':'descriptive upload quality, graph persistence, governed findings; no expected detection for degraded inputs','production_configuration':'unchanged defaults'})
    with tempfile.TemporaryDirectory(prefix='prize-upload-') as tmp:
        os.environ['NERAIUM_RUNTIME_DIR']=tmp
        from app.services.upload_jobs import process_csv_content,configure_runtime_dir
        from app.services.sii_runner import configure_runtime_dir as configure_runner
        configure_runtime_dir(Path(tmp));configure_runner(Path(tmp))
        summaries=[]
        with gzip.open(output/'uploads.jsonl.gz','wt') as raw:
            for name in specs:
                source=rows(410,0,.65,n=1200,noisy=name=='noise')
                if name.startswith('missing_'):
                    period={'missing_1pct':100,'missing_5pct':20,'missing_20pct':5,'missing_50pct':2}[name]
                    for i,r in enumerate(source):
                        if i%period==0:r['flow']=''
                for i,r in enumerate(source):
                    if name=='dropout' and i>=900:r['flow']=''
                    if name=='flatline' and i>=900:r['flow']=100.
                    if name=='duplicate' and i%20==1:r['timestamp']=source[i-1]['timestamp']
                    if name=='outliers' and i%31==0:r['differential_pressure']+=1000
                    if name=='level_compensation' and i>=900:r['flow']+=20
                    if name=='relationship_change' and i>=900:r['differential_pressure']=80-r['differential_pressure']
                if name=='out_of_order':source[600:]=reversed(source[600:])
                if name=='irregular':source=[r for i,r in enumerate(source) if i%7!=0]
                buf=io.StringIO();writer=csv.DictWriter(buf,fieldnames=list(source[0]));writer.writeheader();writer.writerows(source);content=buf.getvalue()
                started=time.perf_counter();record={'case':name,'source_csv':content,'source_sha256':hashlib.sha256(content.encode()).hexdigest(),'rows':len(source)}
                try:
                    result=process_csv_content(content=content.encode(),filename=name+'.csv',job_id='prize-'+name);record['output']=result
                    summary={'case':name,'rows':len(source),'data_quality':result.get('data_quality'),'ingestion_report':result.get('ingestion_report'),'drift_status':result.get('drift_status'),'analysis_result':result.get('analysis_result'),'processing_stats':result.get('processing_stats')}
                except Exception as exc:
                    record['exception']={'type':type(exc).__name__,'message':str(exc)};summary={'case':name,'exception':record['exception']}
                record['wall_seconds']=time.perf_counter()-started;summary['wall_seconds']=record['wall_seconds'];summaries.append(summary)
                raw.write(json.dumps(record,sort_keys=True,default=str)+'\n');raw.flush()
                print(name,summary.get('drift_status',summary.get('exception')),flush=True)
        write(output/'summary.json',{'cases':summaries,'freeze_verification':check_freeze(Path(sys.argv[2]))})
if __name__=='__main__':main()
