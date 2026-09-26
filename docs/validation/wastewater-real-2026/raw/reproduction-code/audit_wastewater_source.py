#!/usr/bin/env python3
import csv,json,math
from datetime import datetime
from pathlib import Path
rows=list(csv.DictReader(open('/home/ubuntu/Data.csv')));ts=[datetime.strptime(r['Time'],'%m/%d/%Y %I:%M:%S %p') for r in rows];g=[]
for i,(a,b) in enumerate(zip(ts,ts[1:]),1):
 if (b-a).total_seconds()!=300:g.append({'before_source_row':i,'after_source_row':i+1,'before':str(a),'after':str(b),'seconds':(b-a).total_seconds(),'absent_five_minute_slots':int((b-a).total_seconds()/300)-1})
flat={}
for c in list(rows[0])[1:]:
 runs=[];start=0
 for i in range(1,len(rows)+1):
  if i==len(rows) or rows[i][c]!=rows[start][c]:
   if i-start>=12:runs.append({'start_row':start+1,'end_row':i,'rows':i-start,'value':rows[start][c],'start_time':str(ts[start]),'end_time':str(ts[i-1])})
   start=i
 flat[c]={'runs_at_least_12_rows':len(runs),'longest':max(runs,key=lambda x:x['rows']) if runs else None}
negative=[]
for i,r in enumerate(rows,1):
 try:
  if float(r['Influent flowrate'])<0:negative.append(i)
 except ValueError:pass
q={'gaps':g,'absent_five_minute_slots':sum(x['absent_five_minute_slots'] for x in g),'source_span_days':(ts[-1]-ts[0]).total_seconds()/86400,'negative_flow_rows':negative,'constant_string_run_audit':flat,'note':'Descriptive source-quality audit, not an added exclusion or analytical threshold; constant values may be physical, rounded, censored or sensor-related.','audit_development_failure':'Initial supplementary negative-flow audit raised ValueError on source ??? cell; corrected audit handles that nonnumeric value without changing source, inclusion policy or engine execution.'}
Path('docs/validation/wastewater-real-2026/raw/quality-details.json').write_text(json.dumps(q,indent=2)+'\n');print(json.dumps(q,indent=2))
