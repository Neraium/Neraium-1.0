"""Complete pre-change normalized telemetry bytes, provenance and mutable aliases."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import gzip,json
from pathlib import Path

import pytest
from app.services import analysis_result_contract as contract
from app.services.analysis_provenance import build_analysis_provenance
from app.services.output_semantics_legacy_source import canonical_json,semantic_digest,SEMANTICS_VERSION

FIXTURE=Path(__file__).parent/'fixtures/normalized_telemetry_metadata/before.json.gz'

def arguments(count=256):
    start=datetime(2026,6,1,tzinfo=timezone.utc)
    return {'rows':[{'timestamp':(start+timedelta(minutes=i)).isoformat(),'flow_gpm':80+i%11,'pressure_psi':40+2*(i%11),'temp_c':20+i%3/10,'__source_row_number':100+i} for i in range(count)],
            'columns':['timestamp','flow_gpm','pressure_psi','temp_c'],'numeric_columns':['flow_gpm','pressure_psi','temp_c'],
            'timestamp_column':'timestamp','timestamp_profile':{'estimated_sample_interval':60},'data_quality':{},'ingestion_report':{'sample_interval_seconds':60},'source_file':'source.csv'}

def catalog():
    return {c:{'source_column':c,'original_header':c.upper(),'normalized_name':c,'display_name':'Label '+c,'source_column_index':i+1,'engineering_units':unit,'canonical_role':role,'telemetry_classification':{'category':'equipment_process','analysis_role':'primary','structural_class':'continuous','reasons':['catalog']}} for i,(c,unit,role) in enumerate([('flow_gpm','gpm','flow'),('pressure_psi','psi','pressure'),('temp_c',None,'temperature')])}

def cases():
    out={}
    def add(name,args):out[name]=args
    add('realistic',arguments())
    a=arguments();a['telemetry_signal_catalog']=catalog();add('realistic_catalog',a)
    a=arguments(1);a['numeric_columns']=['flow_gpm'];add('single',a)
    add('empty',arguments(0))
    a=arguments(0);a['telemetry_signal_catalog']={'flow_gpm':{'telemetry_classification':{}}};add('empty_incomplete_catalog',a)
    a=arguments(8);a['numeric_columns']=[];add('no_columns',a)
    a=arguments(8);a['numeric_columns']=['pressure_psi','missing_column','flow_gpm','pressure_psi'];add('duplicate_and_excluded_columns',a)
    a=arguments(8);a['rows'].reverse();a['numeric_columns'].reverse();add('reordered',a)
    a=arguments(20)
    for i,value in enumerate([None,'',' ','nan','NaN','null','none','n/a','na','-',float('nan'),float('inf'),-float('inf'),'bad','1,234','25%','-999',0,True,'2.5']):
        for c in a['numeric_columns']:a['rows'][i][c]=value
    a['data_quality']={'integrity_flags':{'flow_gpm':'degraded','pressure_psi':'missing'},'fill_methods':{'flow_gpm':'linear','pressure_psi':'forward'}};add('values_quality_fill',a)
    a=arguments(4);a['rows'][0]['__source_timestamp']=' 2026-07-01T12:00:00+05:30 ';a['rows'][1]['timestamp']=None;a['rows'][2].pop('timestamp');a['rows'][3]['timestamp']='invalid clock';a['source_file']=' source_µ.csv ';add('source_and_timestamp',a)
    a=arguments(4);a['timestamp_column']=None;a['source_file']='different.csv';add('fallback_clock_and_identity',a)
    for limit in [-1,0,1,4,500,1000]:
        a=arguments();a['record_limit']=limit;add('limit_'+str(limit),a)
    a=arguments(8);a['telemetry_signal_catalog']=list(catalog().values());add('catalog_list',a)
    a=arguments(8);a['telemetry_signal_catalog']=[*catalog().values(),{'source_column':'flow_gpm','display_name':'last catalog entry','engineering_units':'L/s'}];add('duplicate_catalog_entries',a)
    a=arguments(8);a['telemetry_signal_catalog']=catalog();a['telemetry_signal_catalog']['pressure_psi']['telemetry_classification']=a['telemetry_signal_catalog']['flow_gpm']['telemetry_classification'];add('shared_classification',a)
    a=arguments(8);a['telemetry_signal_catalog']=catalog()
    for metadata in a['telemetry_signal_catalog'].values():metadata['display_name']='Same';metadata['engineering_units']='';metadata['canonical_role']='equivalent'
    add('equivalent_metadata_unit_fallback',a)
    a=arguments(8);a['timestamp_profile']=None;a['ingestion_report']=None;a['data_quality']=None;add('absent_optional_metadata',a)
    return out

CASES=cases()

def aliases(value):
    groups={}
    def walk(v,path):
        if isinstance(v,(dict,list)):
            groups.setdefault(id(v),[]).append(path)
            for k,x in (v.items() if isinstance(v,dict) else enumerate(v)):walk(x,path+'/'+str(k))
    walk(value,'')
    return sorted(sorted(paths) for paths in groups.values() if len(paths)>1)

def capture(args):
    args=deepcopy(args);before=json.dumps(args,allow_nan=True)
    first=contract.build_normalized_telemetry(**args);second=contract.build_normalized_telemetry(**args)
    assert json.dumps(args,allow_nan=True)==before
    assert canonical_json(first)==canonical_json(second)
    packet={'job_id':'fixture-job','dataset_id':'fixture-dataset','input_hash':'fixture-source-hash','analysis_result':{'output_semantics':SEMANTICS_VERSION,'normalized_telemetry':first}}
    return {'ordered_json':json.dumps(first,ensure_ascii=False,separators=(',',':'),allow_nan=True),
            'canonical_json':canonical_json(first),'semantic_digest':semantic_digest(first),
            'provenance':build_analysis_provenance(packet),'mutable_aliases':aliases({'input':args,'first':first,'second':second})}

@pytest.mark.parametrize('name',CASES)
def test_complete_normalized_telemetry_matches_prechange(name):
    with gzip.open(FIXTURE,'rt') as f:expected=json.load(f)
    actual = capture(CASES[name])
    from app.services.engine_identity import git_commit
    assert expected[name]['provenance']['build_commit'] == '97d267d3'
    assert actual['provenance']['build_commit'] == git_commit()
    # Repository build provenance changes on promotion; no telemetry or digest
    # fields are excluded or updated in the retained fixture.
    expected[name]['provenance']['build_commit'] = git_commit()
    assert actual == expected[name]
