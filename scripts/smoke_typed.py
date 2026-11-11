#!/usr/bin/env python3
"""Real-data noncubic/2D checks and a legacy-versus-typed float32 equivalence check."""
import json,os,subprocess
from pathlib import Path
import numpy as np
from run_sdrbench import CODECS,dump
ROOT=Path(__file__).resolve().parents[1]
def main():
 out=ROOT/'results/smoke-typed';out.mkdir(exist_ok=True)
 cases=[('CESM2D','/data0/lb/sdrbench/CESM/TREFHT_1_1800_3600.f32','<f4',(1,1800,3600),(1,64,80)),
        ('Miranda64','/data0/lb/sdrbench/Miranda/velocityx.d64','<f8',(256,384,384),(24,32,40)),
        ('NYX32','/data0/lb/sdrbench/NYX/velocity_x.f32','<f4',(512,512,512),(24,32,40))]
 env=os.environ.copy();env.update({'OMP_NUM_THREADS':'1','OMP_THREAD_LIMIT':'1','OMP_DYNAMIC':'FALSE','OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1'})
 all_rows=[];checks=[]
 for label,source,dtype,shape,crop in cases:
  full=np.memmap(source,dtype=dtype,mode='r',shape=shape);start=[max(0,(n-c)//2) for n,c in zip(shape,crop)]
  data=np.ascontiguousarray(full[tuple(slice(s,s+c) for s,c in zip(start,crop))])
  assert data.max()>data.min(),label
  input_path=out/(label+'.raw');data.tofile(input_path)
  for codec in CODECS:
   suffix='_f64' if dtype=='<f8' else '_f32';binary=ROOT/'build/typed/bin'/('bench_'+codec.lower()+suffix)
   tail=[str(input_path),*map(str,crop),'1','0','0.1','0.01','0.001','0.0001','0.00001','0.000001']
   proc=subprocess.run(['taskset','-c','2',str(binary),*tail],env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
   (out/(label+'__'+codec+'.log')).write_text(proc.stdout)
   rows=[json.loads(l[len('LFCB_RESULT '):]) for l in proc.stdout.splitlines() if l.startswith('LFCB_RESULT ')]
   assert proc.returncode==0 and len(rows)==6,(label,codec,proc.stdout[-2000:])
   assert all(r['status']=='ok' and r['violations']==0 and r['cpu']==2 for r in rows),(label,codec,rows)
   for r in rows:r['smoke_case']=label
   all_rows+=rows
   if label=='NYX32':
    old=subprocess.run(['taskset','-c','2',str(ROOT/'build/bin'/('bench_'+codec.lower())),*tail],env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,check=True)
    previous=[json.loads(l[len('LFCB_RESULT '):]) for l in old.stdout.splitlines() if l.startswith('LFCB_RESULT ')]
    assert len(previous)==6
    for x,y in zip(rows,previous):
     for key in ('compressed_bytes','max_abs_error','rmse','nrmse','violations','effective_bound'):assert x[key]==y[key],(codec,key,x[key],y[key])
   checks.append({'case':label,'codec':codec,'points':len(rows),'status':'ok'})
   print('PASS',label,codec,flush=True)
 (out/'records.jsonl').write_text(''.join(json.dumps(r,allow_nan=False)+'\n' for r in all_rows));dump(out/'checks.json',checks)
 print('SMOKE_COMPLETE',len(all_rows),'strict-bound records; legacy equivalence verified',flush=True)
if __name__=='__main__':main()
