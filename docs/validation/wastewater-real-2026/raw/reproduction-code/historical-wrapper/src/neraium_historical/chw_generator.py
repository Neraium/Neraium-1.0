"""Reproducible controlled CHW fixture; never imported by analysis or production.

Replacement provenance: the original 3-month CSV's generating source was not
available locally. This is an explicit replacement, not a recovered original.
Weather uses bounded, interpolated daily innovations instead of an unbounded
random walk. The bounds describe this fixture, not all possible desert weather.
"""
from datetime import datetime, timedelta
from pathlib import Path
import argparse
import csv
import hashlib
import json
import numpy as np

OA_BOUNDS_F = (65.0, 118.0)
SEED = 20260913
DAYS = 60
START = datetime(2026, 6, 14)
COLUMNS = ['OA_Temp_F', 'OA_RH_Pct', 'Building_Cooling_Load_Tons',
           'Chiller_Power_kW', 'Plant_CHW_Flow_GPM', 'Primary_Pump_Speed_Pct',
           'AHU3_CHW_Valve_Cmd_Pct', 'AHU3_CHW_Flow_GPM',
           'CoolingTower_Fan_Speed_Pct', 'Condenser_Water_Supply_Temp_F',
           'Plant_CHW_Supply_Temp_F', 'AHU3_Zone_Temp_F']
UNITS = dict(zip(COLUMNS, ['degF', '%', 'ton', 'kW', 'gpm', '%', '%', 'gpm', '%', 'degF', 'degF', 'degF']))


def weather(days=DAYS, cadence=15, seed=SEED):
    if not isinstance(days, int) or days < 1 or cadence < 1 or 86400 % cadence:
        raise ValueError('Use positive whole days and a cadence dividing one day')
    rng = np.random.default_rng(seed)
    t = np.arange(days * (86400 // cadence)) * cadence / 86400
    # Convex interpolation of bounded daily weather prevents accumulated drift.
    synoptic = np.interp(t, np.arange(days + 1), rng.uniform(-4, 4, days + 1))
    seasonal = 94 + 3 * np.sin(2 * np.pi * (t - 5) / 120)
    diurnal = 12 * np.cos(2 * np.pi * (t - 16 / 24))
    jitter = rng.uniform(-.35, .35, len(t))
    raw = seasonal + synoptic + diurnal + jitter
    # Analytic raw envelope: 74.65..113.35 F. Final physical safety bound.
    oa = np.clip(raw, *OA_BOUNDS_F)
    return t, oa, raw


def envelope(t, start, stop, ramp=.25):
    up = np.clip((t-start)/ramp, 0, 1)
    down = np.clip((stop-t)/ramp, 0, 1)
    v = np.minimum(up, down)
    return v*v*(3-2*v)  # smooth derivative at both ends


def generate(days=DAYS, cadence=15, seed=SEED, controlled=True):
    t, oa, raw = weather(days, cadence, seed)
    rng = np.random.default_rng(seed + 1)
    phase = 2*np.pi*t
    data = {'OA_Temp_F': oa, 'OA_RH_Pct': 22-.45*(oa-94)+rng.uniform(-1,1,len(t))}
    # Independent bounded oscillations preserve comparable marginal distributions
    # while rotating the response's shared vs independent load contribution.
    schedules = [envelope(t,9,26,2), sum(envelope(t,a,a+3) for a in (30,39,48)),
                 envelope(t,5.25,5.5,.05),
                 envelope(t,28,31)-envelope(t,37,40)+envelope(t,46,49), np.zeros(len(t))]
    specs = [(COLUMNS[2:4],2,3,220,60,145,30),
             (COLUMNS[4:6],5,7,600,100,67,12),
             (COLUMNS[6:8],11,13,55,18,24,7),
             (COLUMNS[8:10],17,19,55,15,82,3),
             (COLUMNS[10:12],23,29,44,1.2,73,.7)]
    for i,(names,f,g,mx,sx,my,sy) in enumerate(specs):
        x = np.sin(f*phase+.12*i)
        z = np.cos(g*phase+.21*i)
        rho = (.8 if i==4 else .68) + (.21*schedules[i] if controlled else 0)
        y = rho*x + np.sqrt(1-rho*rho)*z
        # Small bounded sensor noise; fixed seed, independent of episode schedule.
        data[names[0]] = mx+sx*x+rng.uniform(-.002*sx,.002*sx,len(t))
        data[names[1]] = my+sy*y+rng.uniform(-.002*sy,.002*sy,len(t))
    # Weather feeds hydraulic demand without unrealistic full-day clipping.
    # Daily mean affects operating level, not the within-day test covariance.
    n = 86400//cadence
    day_oa = np.repeat(oa.reshape(days,n).mean(axis=1)-94,n)
    data['Plant_CHW_Flow_GPM'] += 2*day_oa
    data['Primary_Pump_Speed_Pct'] = np.clip(data['Primary_Pump_Speed_Pct']+.15*day_oa, 20,100)
    return t, data, {'oa_raw_min':float(raw.min()), 'oa_raw_max':float(raw.max()),
                     'oa_safety_bound_hits':int(np.count_nonzero(raw != oa))}


def truth():
    def at(day): return (START+timedelta(days=day)).isoformat(sep=' ')
    def ep(a,b,ramp):
        return {'onset':at(a), 'full_strength_start':at(a+ramp),
                'recovery_start':at(b-ramp), 'end_exclusive':at(b)}
    return {'A': {'kind':'continuous', 'pair':COLUMNS[2:4], 'episodes':[ep(9,26,2)], 'direction':1},
            'B': {'kind':'recurring', 'pair':COLUMNS[4:6], 'episodes':[ep(a,a+3,.25) for a in (30,39,48)], 'direction':1},
            'C': {'kind':'transient', 'pair':COLUMNS[6:8], 'episodes':[ep(5.25,5.5,.05)], 'direction':1},
            'D': {'kind':'stable', 'pair':COLUMNS[10:12], 'episodes':[], 'direction':0},
            'E': {'kind':'alternating', 'pair':COLUMNS[8:10], 'episodes':[{**ep(a,a+3,.25),'direction':d} for a,d in ((28,1),(37,-1),(46,1))]}}


def write_dataset(directory, cadence=300, seed=SEED):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory/'telemetry.csv'
    if path.exists(): raise FileExistsError(path)
    t, data, audit = generate(cadence=cadence, seed=seed)
    with path.open('x', newline='') as f:
        w = csv.writer(f); w.writerow(['timestamp',*COLUMNS])
        for i in range(len(t)):
            w.writerow([(START+timedelta(seconds=i*cadence)).isoformat(sep=' '),
                        *[f'{data[c][i]:.5f}' for c in COLUMNS]])
    h = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = {'seed':seed,'start':str(START),'days':DAYS,'cadence_seconds':cadence,
                'telemetry_sha256':h, 'scenarios':truth(), 'baseline_correlation':.68,
                'active_correlation':.89,'stable_control_correlation':.8}
    private = directory/'private'; private.mkdir(exist_ok=True)
    private.chmod(0o700)
    (private/'ground-truth.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (private/'ground-truth.json').chmod(0o600)
    config = {'reference_rows':2*86400//cadence, 'comparison_rows':86400//cadence,
              'step_rows':86400//cadence, 'signal_units':UNITS}
    (directory/'replay-config.json').write_text(json.dumps(config,indent=2)+'\n')
    public = {'telemetry_sha256':h,'seed':seed,'rows':len(t), 'cadence_seconds':cadence,
              'reference_start':str(START),'reference_end':str(START+timedelta(days=2)),
              'end_exclusive':str(START+timedelta(days=DAYS)), 'oa_bounds_f':OA_BOUNDS_F,
              'generator_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), **audit}
    (directory/'generation.json').write_text(json.dumps(public,indent=2)+'\n')
    return public


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path); parser.add_argument('--cadence',type=int,default=300)
    parser.add_argument('--seed',type=int,default=SEED)
    args=parser.parse_args(); print(json.dumps(write_dataset(args.directory,args.cadence,args.seed),indent=2))
