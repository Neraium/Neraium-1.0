"""Freeze prospective v2 protocol and production before the first LBNL call."""
import datetime,hashlib,json,pathlib,platform,subprocess,sys,shutil
R=pathlib.Path(__file__).resolve().parent;ROOT=R.parents[3]
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def dump(p,x):p.write_text(json.dumps(x,indent=2)+'\n')
assert not (R/'freeze.json').exists(), 'Never replace a freeze'
files=sorted(p for p in (ROOT/'backend/app').rglob('*') if p.is_file() and p.suffix=='.py')
tracked=subprocess.check_output(['git','ls-files'],cwd=ROOT,text=True).splitlines()
files+= [ROOT/p for p in tracked if (p.startswith('packages/') or p.startswith('tests/') or p in ['requirements.txt','pyproject.toml','scripts/benchmark_dataset_processing.py']) and (ROOT/p).is_file()]
files.append(ROOT/'backend/app/services/output_semantics.py')
files=sorted(set(files))
for p in files:
 target=R/'source-snapshot'/p.relative_to(ROOT)
 target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target)
# Dedicated new regression file is untracked until user elects to commit.
p=ROOT/'tests/test_governed_output_determinism.py'
shutil.copyfile(p,R/'source-snapshot/tests'/p.name)
files.append(p)
diff=subprocess.check_output(['git','diff','--binary'],cwd=ROOT)
(R/'remediation.patch').write_bytes(diff)
dump(R/'freeze.json',{'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
 'commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
 'branch':subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip(),
 'tracked_file_sha256':{str(p.relative_to(ROOT)):sha(p) for p in files},
 'protocol_sha256':sha(R/'protocol.json'),
 'tools':{p.name:sha(p) for p in sorted(R.glob('*.py'))},
 'environment':{'python':sys.version,'platform':platform.platform(),'analytical_config_overrides':None,
 'threads':{'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1','NUMEXPR_NUM_THREADS':'1'},
 'hash_seeds':{'primary':'17','repeat':'991'}},
 'inputs':{name:sha(ROOT/'docs/validation/lbnl-blind-2026/raw/hourly'/f'{name}.csv') for name in ['CASE_001','CASE_022','REFERENCE']}})
dump(R/'protocol-seal.json',{'sha256':sha(R/'protocol.json')})
(R/'environment-packages.txt').write_bytes(subprocess.check_output([sys.executable,'-m','pip','freeze']))
shutil.copyfile('/tmp/neraium-phase1-benchmark-integrity.json',R/'baseline-v1-before-sha256.json')
print('frozen',len(files),'source/test files')
