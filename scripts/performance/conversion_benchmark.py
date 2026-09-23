"""Alternating CPU-time comparison for the measured baseline conversion hotspot."""
import json
import statistics
import time
from pathlib import Path
import numpy as np

results = {}
for size in (128, 1000, 100000):
    values = [float(i % 93) * .0123 for i in range(size)]
    samples = {'asarray': [], 'fromiter': []}
    repetitions = max(20, 2000000 // size)
    methods = {
        'asarray': lambda: np.asarray(values, dtype=float),
        'fromiter': lambda: np.fromiter(values, dtype=float, count=len(values)),
    }
    np.testing.assert_array_equal(methods['asarray'](), methods['fromiter']())
    for fn in methods.values():
        fn()
    for trial in range(5):
        for name in (list(methods) if trial % 2 == 0 else list(reversed(methods))):
            start = time.process_time()
            for _ in range(repetitions):
                methods[name]()
            samples[name].append(time.process_time() - start)
    results[str(size)] = {'repetitions_per_sample': repetitions, 'samples_cpu_seconds': samples,
                          'median_cpu_seconds': {name: statistics.median(times) for name, times in samples.items()}}
path = Path(__file__).resolve().parents[2] / 'docs/performance/2026-optimization/raw/conversion-microbenchmark.json'
path.write_text(json.dumps(results, indent=2)+'\n')
print(json.dumps({size: value['median_cpu_seconds'] for size, value in results.items()}, indent=2))
