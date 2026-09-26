#!/usr/bin/env python3
"""Observe existing benchmark paths, including every repetition and guard result."""
import gzip,importlib.util,json,os,sys,tempfile,time
from pathlib import Path
from validate_prize import check_freeze,write
from benchmark_dataset_processing import CASES, generate_rows,numeric_profiles,run_baseline_learning,run_comparison,semantic_fingerprint,_measure
ROOT=Path(__file__).resolve().parents[1]

def main():
    out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=True);check_freeze(Path(sys.argv[2]))
    if (out/'performance.json').exists():raise RuntimeError('refuse_overwrite')
    write(out/'plan.json',{'processing_cases':{k:vars(v) for k,v in CASES.items()},'repetitions':3,'upload_rows':[10000,100000,1000000],'upload_guard_source':'tests/test_upload_robustness_benchmark.py','runtime':'local SQLite, concurrent regression activity may be present; no cloud/network or concurrency throughput claims'})
    results=[]
    with tempfile.TemporaryDirectory(prefix='prize-performance-') as tmp, gzip.open(out/'processing-outputs.jsonl.gz','wt') as raw:
        os.environ['NERAIUM_RUNTIME_DIR']=tmp
        from app.services.upload_jobs import configure_runtime_dir
        from app.services.sii_runner import configure_runtime_dir as configure_runner
        configure_runtime_dir(Path(tmp));configure_runner(Path(tmp))
        for name,case in CASES.items():
            columns,rows=generate_rows(case);profiles=numeric_profiles(columns,rows)
            for repetition in range(3):
                for path,fn in [('baseline',lambda:run_baseline_learning(columns,rows,optimized=True)),('comparison',lambda:run_comparison(columns,rows,profiles,optimized=True))]:
                    measured=_measure(fn);output=measured.pop('output');fp=semantic_fingerprint(output.get('intelligence',output));record={'case':name,'rows':case.rows,'signals':case.signals,'path':path,'repetition':repetition,**measured,'semantic_fingerprint':fp}
                    results.append(record);raw.write(json.dumps({**record,'output':output},default=str)+'\n');raw.flush();print(name,path,repetition,measured['wall_seconds'],flush=True)
        spec=importlib.util.spec_from_file_location('original_benchmark',ROOT/'tests/test_upload_robustness_benchmark.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        uploads=[]
        for n,ceiling in [(10000,20.),(100000,60.),(1000000,300.)]:
            try:
                record=module._run_case(f'prize_{n}',module._rows(n),expected_detected=False,max_seconds=ceiling)
                record['checks']={'runtime_within_existing_reference':record['runtime_seconds']<=ceiling,'wall_within_reference':record['wall_seconds']<=ceiling,'all_source_rows_accounted':record['rows_received']==record['rows_used']==n,'sampling_bounded':record['analysis_sample_rows']<=100000,'one_million_memory_guard':record['memory_delta_kb']<=768*1024 if n==1000000 else None}
            except Exception as exc:record={'rows':n,'exception':{'type':type(exc).__name__,'message':str(exc)}}
            uploads.append(record);write(out/'upload-scales.json',uploads);print('upload',n,record.get('wall_seconds'),flush=True)
        write(out/'performance.json',{'measurements':results,'uploads':uploads,'freeze_verification':check_freeze(Path(sys.argv[2]))})
if __name__=='__main__':main()
