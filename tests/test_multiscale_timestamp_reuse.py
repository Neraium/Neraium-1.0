"""Frozen exact temporal selections and complete multiscale results."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import gzip
import inspect
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace

import pytest
from app.engine.sii import common
from app.engine.sii import multiscale_analysis as module

FIXTURE=Path(__file__).parent/'fixtures/multiscale_timestamp_reuse/before.json.gz'

def population(count=480, aware=False):
    start=datetime(2026,3,8,0,0,tzinfo=timezone.utc if aware else None)
    return [{'timestamp':(start+timedelta(minutes=i)).isoformat(), 'flow':80+i%11+(10 if i>=360 else 0),
             'pressure':40+2*(i%11)+(i%3 if i>=420 else 0), '__source_row_number':1000+i} for i in range(count)]

def cases():
    result={}
    def add(name,rows,**kwargs):result[name]={'rows':rows,**kwargs}
    for clock in [False,True]:
        add('realistic_'+str(clock),population(),source_clock=clock)
        data=population(); latest=datetime.fromisoformat(data[-1]['timestamp']); cutoff=latest-timedelta(hours=1)
        data=[r for r in data if r['timestamp']!=cutoff.isoformat()]
        for j,delta in enumerate([-1,0,1]):
            data.append({'timestamp':(cutoff+timedelta(microseconds=delta)).isoformat(),'flow':83+j,'pressure':46+j,'__source_row_number':9000+j})
        data.sort(key=lambda r:r['timestamp'])
        add('cutoff_'+str(clock),data,source_clock=clock)
        add('host_dst_'+str(clock),population(),source_clock=clock,tz='America/New_York')
    add('aware',population(aware=True))
    data=population(aware=True)
    for i,r in enumerate(data):
        d=datetime.fromisoformat(r['timestamp']);r['timestamp']=d.astimezone(timezone(timedelta(hours=5,minutes=30))).isoformat() if i%2 else d.isoformat().replace('+00:00','Z')
    add('equivalent_offsets',data)
    for value,name in [(None,'missing'),('bad','invalid'),('','blank')]:
        data=population();data[50]['timestamp']=value;add(name,data)
    data=population();data[51]['timestamp']=data[50]['timestamp'];add('duplicate',data)
    add('reversed',list(reversed(population())))
    data=population()
    for r in data[:100]:r['timestamp']='invalid'
    add('low_coverage',data)
    add('empty',[]);add('one',population(1));add('small',population(8))
    add('no_timestamp',population(30),timestamp_column=None)
    return result

CASES=cases()

def capture(case,monkeypatch):
    monkeypatch.setattr(module,'time',SimpleNamespace(perf_counter=lambda:100.0))
    monkeypatch.setattr(common,'time',SimpleNamespace(perf_counter=lambda:100.0))
    old_tz=os.environ.get('TZ');os.environ['TZ']=case.get('tz','UTC');time.tzset()
    rows=deepcopy(case['rows']);before=deepcopy(rows)
    column=case.get('timestamp_column','timestamp');clock=case.get('source_clock',False)
    parsed=common.parse_timestamps(rows,column);pairs=[(i,d) for i,d in enumerate(parsed) if d is not None]
    projections=[(pairs[-1][1]-d).total_seconds() if clock else d.timestamp() for _,d in pairs]
    selected=[];progress=[]
    lines,start=inspect.getsourcelines(module.analyze_multiscale)
    selection_line=start+next(i for i,s in enumerate(lines) if 'start_time = parsed[current_indices[0]]' in s)
    def trace(frame,event,arg):
        if frame.f_code is module.analyze_multiscale.__code__ and event=='line' and frame.f_lineno==selection_line:
            local=frame.f_locals
            if 'timestamp_projections' in local:assert local['timestamp_projections']==projections
            recent=list(local['current_indices']);baseline=list(local['baseline_indices'])
            selected.append({'horizon':local['spec'],'baseline_indexes':baseline,'recent_indexes':recent,
                             'baseline_count':len(baseline),'recent_count':len(recent),
                             'baseline_source_ids':[rows[i]['__source_row_number'] for i in baseline],
                             'recent_source_ids':[rows[i]['__source_row_number'] for i in recent]})
        return trace
    old_trace=sys.gettrace()
    try:
        sys.settrace(trace)
        output=module.analyze_multiscale(rows=rows,numeric_columns=['flow','pressure'],timestamp_column=column,
                    source_clock=clock,progress_callback=lambda *a:progress.append(list(a)))
    finally:
        sys.settrace(old_trace)
        if old_tz is None:os.environ.pop('TZ',None)
        else:os.environ['TZ']=old_tz
        time.tzset()
    assert rows==before
    return {'parsed':[d.isoformat() if d else None for d in parsed], 'projected':[[i,v] for (i,_),v in zip(pairs,projections)],
            'selections':selected,'output':output,'progress':progress}

@pytest.mark.parametrize('name',CASES)
def test_complete_temporal_output_matches_prechange(name,monkeypatch):
    with gzip.open(FIXTURE,'rt') as f:expected=json.load(f)
    # No sorted keys: preserve observable ordering as well as complete values.
    assert json.dumps(capture(CASES[name],monkeypatch),allow_nan=False)==json.dumps(expected[name],allow_nan=False)
