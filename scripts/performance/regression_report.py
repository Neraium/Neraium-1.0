"""Compare complete focused regression failures against the pre-edit baseline."""
import json
import re
from pathlib import Path
RAW = Path(__file__).resolve().parents[2] / 'docs/performance/2026-optimization/raw'

def read(name):
    text = (RAW / name).read_text()
    failed = sorted(line[7:].split(' - ', 1)[0].strip() for line in text.splitlines() if line.startswith('FAILED '))
    summary = re.findall(r'(\d+) failed, (\d+) passed.*? in ([\d.]+)s', text)
    if not summary or '[100%]' not in text:
        raise RuntimeError(f'Incomplete regression report: {name}')
    count_failed, count_passed, elapsed = summary[-1]
    assert int(count_failed) == len(failed)
    return {'log': name, 'failed': int(count_failed), 'passed': int(count_passed), 'seconds': float(elapsed), 'failed_test_ids': failed}

before = read('before-focused-regression.log')
after = read('after-focused-regression.log')
output = {'before': before, 'after': after,
          'new_failures': sorted(set(after['failed_test_ids']) - set(before['failed_test_ids'])),
          'resolved_failures': sorted(set(before['failed_test_ids']) - set(after['failed_test_ids']))}
(RAW / 'regression-comparison.json').write_text(json.dumps(output, indent=2)+'\n')
print(json.dumps(output, indent=2))
if output['new_failures']:
    raise SystemExit(1)
