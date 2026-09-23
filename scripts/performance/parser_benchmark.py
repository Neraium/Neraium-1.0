"""Side-by-side final parser microbenchmark against the frozen test reference."""
import json
import statistics
import sys
import time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT / 'tests')]
from app.services.data_quality import parse_numeric_value
from test_performance_equivalence import reference_parse_numeric_value

cases = {
    'canonical': ['123.45678901', '-0.01', '1e-12'] * 1000,
    'units': ['123.45 kPa', '12 %', '1,234.5'] * 1000,
    'mixed': ['123.456', '12 kPa', None, 'nan', 'bad', '1,234%'] * 500,
}
output = {}
for case, values in cases.items():
    output[case] = {}
    for name, fn in [('reference', reference_parse_numeric_value), ('optimized', parse_numeric_value)]:
        for value in values:
            fn(value)
        runs = []
        for _ in range(5):
            started = time.perf_counter()
            for repeat in range(20):
                for value in values:
                    fn(value)
            runs.append(time.perf_counter() - started)
        output[case][name] = {'calls_per_sample': 60000, 'samples': runs, 'median': statistics.median(runs)}
path = ROOT / 'docs/performance/2026-optimization/raw/final-parser-microbenchmark.json'
path.write_text(json.dumps(output, indent=2) + '\n')
print(json.dumps(output, indent=2))
