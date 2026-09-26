"""Lossless standard-library checkpoint codec and optional full JSON export.

Only load checkpoints produced by this trusted local benchmark. Pickle is not
an interchange parser for untrusted input. JSON exports preserve dictionary order.
"""
import gzip,json,pickle,pathlib,sys

def read(path):
 path=pathlib.Path(path)
 if path.name.endswith('.pkl.gz'):
  with gzip.open(path,'rb') as f:return pickle.load(f)
 with gzip.open(path,'rt') as f:return json.load(f)

def write(path,value):
 path=pathlib.Path(path);path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix(path.suffix+'.writing')
 with gzip.open(tmp,'wb',compresslevel=3) as f:pickle.dump(value,f,protocol=5)
 tmp.replace(path)

if __name__=='__main__':
 value=read(sys.argv[1])
 with gzip.open(sys.argv[2],'wt') as f:f.write(json.dumps(value,separators=(',',':'),allow_nan=False))
