#!/usr/bin/env python3
"""Repeat only observed timeout failures and the 100k guard after other workloads end."""
import json,os,shutil,subprocess,sys,tempfile,time
from pathlib import Path
from validate_prize import check_freeze,write

def main():
    raw=Path(sys.argv[1]);check_freeze(raw/'freeze.json')
    if (raw/'isolated-exit.json').exists():raise RuntimeError('refuse_overwrite')
    while not (raw/'focused-exit.json').exists():time.sleep(1)
    cases=['tests/test_behavioral_baseline_workflow.py::test_completed_comparison_uses_distinct_dataset_and_analysis_ids_and_scopes_findings','tests/test_data_upload.py::test_upload_status_propagation_progresses_from_queued_to_complete','tests/test_upload_robustness_benchmark.py::test_100k_upload_performance_guard']
    with tempfile.TemporaryDirectory(prefix='prize-isolated-pytest-') as tmp:
        command=[sys.executable,'-m','pytest',*cases,'--junitxml='+str(raw/'isolated-regression.xml'),'--basetemp='+tmp]
        with (raw/'isolated-regression.log').open('w') as log:
            result=subprocess.run(command,env={**os.environ,'PYTHONPATH':'backend','OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1','PYTHONHASHSEED':'0'},stdout=log,stderr=subprocess.STDOUT)
        for p in Path(tmp).rglob('100k_benchmark_report.json'):shutil.copyfile(p,raw/'isolated-100k.json')
        write(raw/'isolated-exit.json',{'command':command,'exit_code':result.returncode,'earlier_failures_retained':True,'other_validation_workloads_finished':True,'freeze_verification':check_freeze(raw/'freeze.json')})
    raise SystemExit(result.returncode)
if __name__=='__main__':main()
