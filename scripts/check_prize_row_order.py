#!/usr/bin/env python3
"""Bound the replay discrepancy by restoring source-column insertion order only."""
import copy,gzip,json,os,sys,tempfile
from pathlib import Path
from validate_prize import check_freeze,digest,write
from replay_prize_validation import semantic

def main():
    root=Path(sys.argv[1]);check_freeze(root/'freeze.json')
    r=json.load(gzip.open(root/'replay-discrepancy-output.json.gz','rt'));kw=copy.deepcopy(r['input'])
    for role in ['reference_rows','comparison_rows']:kw[role]=[{c:row[c] for c in kw['columns']} for row in kw[role]]
    expected=next(x['expected_sha256'] for x in json.loads((root/'replay-verification.json').read_text())['fresh_process_replays'] if x['case']=='archived_synthetic_chw')
    with tempfile.TemporaryDirectory(prefix='prize-row-order-') as tmp:
        os.environ['NERAIUM_RUNTIME_DIR']=tmp
        from app.engine.sii_engine import evaluate_sii
        out=evaluate_sii(**kw)
    with gzip.open(root/'row-order-output.json.gz','wt') as f:json.dump({'input':kw,'output':out},f)
    actual=digest(semantic(out))
    write(root/'row-order-check.json',{'restored_source_column_order_matches_original':actual==expected,'actual_sha256':actual,'expected_sha256':expected,'canonical_input_hash_unchanged':digest(kw)==digest(r['input']),'columns':kw['columns'],'sorted_row_keys':list(r['input']['reference_rows'][0]),'restored_row_keys':list(kw['reference_rows'][0]),'change':'row dictionary insertion order only; no values, columns list, thresholds or configuration changed','primary_replay_failure_retained':True,'freeze_verification':check_freeze(root/'freeze.json')})
    if actual!=expected:raise SystemExit(1)
if __name__=='__main__':main()
