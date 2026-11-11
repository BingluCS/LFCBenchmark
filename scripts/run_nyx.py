#!/usr/bin/env python3
"""Sequential, CPU-pinned native API benchmark, with resumable job records."""
import argparse, datetime, hashlib, json, os, platform, random, subprocess, sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CODECS=['ZFP','PFPL','SPERR','SZ3','Falcons']
def main():
 p=argparse.ArgumentParser();p.add_argument('--data-dir',type=Path,default=Path('/data0/lb/sdrbench/NYX'))
 p.add_argument('--output',type=Path,required=True);p.add_argument('--repetitions',type=int,default=5);p.add_argument('--warmups',type=int,default=1)
 p.add_argument('--alphas',type=float,nargs='+',default=[1e-2,1e-3,1e-4,1e-5,1e-6]);p.add_argument('--codecs',nargs='+',default=CODECS,choices=CODECS)
 p.add_argument('--fields',nargs='+');p.add_argument('--shape',type=int,nargs=3,default=[512,512,512]);p.add_argument('--cpu',type=int,default=2);p.add_argument('--resume',action='store_true');p.add_argument('--seed',type=int,default=42)
 a=p.parse_args();a.output=a.output.resolve();a.output.mkdir(parents=True,exist_ok=True)
 if a.repetitions<1 or a.warmups<0 or any(x<=0 for x in a.alphas):p.error('invalid repetition count or error bound')
 files=sorted(a.data_dir.glob('*.f32'))
 if a.fields:files=[x for x in files if x.stem in a.fields]
 if not files:p.error('no selected .f32 fields found')
 manifest=json.loads((ROOT/'build/manifest.json').read_text());build_hash=hashlib.sha256((ROOT/'build/manifest.json').read_bytes()).hexdigest()
 config={'shape':a.shape,'alphas':a.alphas,'repetitions':a.repetitions,'warmups':a.warmups,'cpu':a.cpu,'seed':a.seed,'codecs':a.codecs,'files':[str(x.resolve()) for x in files],'build_manifest_sha256':build_hash}
 config_path=a.output/'config.json'
 if config_path.exists():
  if not a.resume:p.error('output already has a run; use a new output or --resume')
  if json.loads(config_path.read_text())!=config:p.error('resume configuration/build mismatch')
 else:config_path.write_text(json.dumps(config,indent=2)+'\n')
 metadata={'host':platform.node(),'platform':platform.platform(),'python':sys.version,'cpuinfo':Path('/proc/cpuinfo').read_text().split('model name')[1].split('\n')[0].strip(':\t '),'sources':manifest['sources'],'timing_scope':'native in-memory adapter operation including setup and allocation; excludes file I/O, process startup, input copy, validation, and output destruction','units':'MiB/s = 1048576 bytes/s for aggregate reports','spatial_order':'C order (z,y,x), x fastest','SPERR_chunks':[min(256,n) for n in a.shape[::-1]],'SPERR_tolerance_policy':'reserve one worst-case float32 output ULP when bound > 2 ULP; otherwise pass half bound; retain nominal and effective bounds','PFPL_mode':'ABS, tolerance rounded downward to float32','aggregation':'arithmetic mean repeat time; sum field bytes divided by sum field mean time'}
 (a.output/'metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
 jobs=[(f,c) for f in files for c in a.codecs];random.Random(a.seed).shuffle(jobs)
 env=os.environ.copy();env.update({'OMP_NUM_THREADS':'1','OMP_THREAD_LIMIT':'1','OMP_DYNAMIC':'FALSE','OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1','NUMEXPR_NUM_THREADS':'1'})
 failures=[];hashes={}
 for file,codec in jobs:
  stem=file.stem+'__'+codec;job_file=a.output/(stem+'.jsonl');done=a.output/(stem+'.done.json')
  expected_bytes=4
  for n in a.shape:expected_bytes*=n
  if file.stat().st_size!=expected_bytes:raise ValueError(f'{file}: byte count does not match shape')
  if file not in hashes:
   digest=hashlib.sha256()
   with file.open('rb') as f:
    while b:=f.read(8*1024*1024):digest.update(b)
   hashes[file]=digest.hexdigest()
  digest_hex=hashes[file]
  if a.resume and done.exists() and json.loads(done.read_text()).get('status')=='ok':
   if json.loads(done.read_text()).get('input_sha256')!=digest_hex:raise ValueError('input changed since previous run: '+str(file))
   print('RESUME_SKIP',stem,flush=True);continue
  cmd=['taskset','-c',str(a.cpu),str(ROOT/'build/bin'/('bench_'+codec.lower())),str(file.resolve()),*map(str,a.shape),str(a.repetitions),str(a.warmups),*map(str,a.alphas)]
  print('START',stem,'alphas',a.alphas,datetime.datetime.now().isoformat(),flush=True)
  count=0;bad=0;max_threads=0
  log=(a.output/(stem+'.log')).open('w')
  stream=job_file.open('w')
  proc=subprocess.Popen(cmd,cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1)
  for line in proc.stdout:
   log.write(line);log.flush()
   try:max_threads=max(max_threads,len(list(Path(f'/proc/{proc.pid}/task').iterdir())))
   except FileNotFoundError:pass
   if line.startswith('LFCB_RESULT '):
    row=json.loads(line[len('LFCB_RESULT '):]);row.update({'dataset':'NYX','field':file.stem,'input_sha256':digest_hex,'shape':a.shape,'build_manifest_sha256':build_hash})
    stream.write(json.dumps(row,allow_nan=False)+'\n');stream.flush()
    if row['status']!='ok':bad+=1
    if not row['warmup']:count+=1
    print('POINT',stem,'alpha',row['alpha'],'repeat',row['repeat'],'warmup',row['warmup'],'status',row['status'],flush=True)
  rc=proc.wait();stream.close();log.close()
  status='ok' if rc==0 and count==len(a.alphas)*a.repetitions and bad==0 and max_threads<=1 else 'failed'
  result={'status':status,'returncode':rc,'measured_records':count,'bad_records':bad,'max_observed_threads':max_threads,'command':cmd,'input_sha256':digest_hex}
  done.write_text(json.dumps(result,indent=2)+'\n')
  print('DONE',stem,result,flush=True)
  if status!='ok':failures.append(stem)
 print('SUITE_COMPLETE','failures=',failures,flush=True)
 return bool(failures)
if __name__=='__main__':raise SystemExit(main())
