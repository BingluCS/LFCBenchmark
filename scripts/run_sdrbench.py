#!/usr/bin/env python3
"""Sequential single-core suite with explicit shapes/dtypes and NYX result reuse."""
import argparse,datetime,fcntl,hashlib,json,os,platform,random,resource,shutil,subprocess,sys,time
from pathlib import Path
from rounding_sdrbench import normalize_bound,repair_roundoff_job
ROOT=Path(__file__).resolve().parents[1]
CODECS=['ZFP','PFPL','SPERR','SZ3','Falcons']
SHAPES={'Miranda':[256,384,384],'CESM':[1,1800,3600],'JHTDB':[512,512,512],
        'NYX':[512,512,512],'SCALE':[98,1200,1200],'Hurricane':[100,500,500]}
def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  while data:=f.read(8*1024*1024):h.update(data)
 return h.hexdigest()
def dump(path,obj):
 tmp=path.with_name(path.name+'.tmp');tmp.write_text(json.dumps(obj,indent=2,allow_nan=False)+'\n');tmp.replace(path)
def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--output',type=Path,required=True);p.add_argument('--inventory',type=Path,default=ROOT/'results/sdrbench-inventory.json')
 p.add_argument('--datasets',nargs='+',choices=SHAPES,default=list(SHAPES));p.add_argument('--miranda-precision',choices=['float32','float64'],default='float64')
 p.add_argument('--repetitions',type=int,default=5);p.add_argument('--warmups',type=int,default=1)
 p.add_argument('--alphas',type=float,nargs='+',default=[1e-1,1e-2,1e-3,1e-4,1e-5,1e-6])
 p.add_argument('--cpu',type=int,default=2);p.add_argument('--seed',type=int,default=42)
 p.add_argument('--codecs',nargs='+',choices=CODECS,default=CODECS);p.add_argument('--reuse-nyx',action='store_true');p.add_argument('--resume',action='store_true')
 p.add_argument('--reuse-from',type=Path,action='append',default=[],help='reuse matching repetition prefixes from complete jobs in another suite run')
 a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
 sources=[]
 for path in a.reuse_from:
  path=path.resolve()
  if path==out:p.error('--reuse-from must differ from --output')
  origin_meta=json.loads((path/'metadata.json').read_text());origin_cfg=json.loads((path/'config.json').read_text())
  if origin_meta['host']!=platform.node() or origin_cfg['cpu']!=a.cpu or origin_cfg['warmups']!=a.warmups:
   p.error('incompatible reuse host, CPU or warmup policy: '+str(path))
  sources.append((path,origin_cfg['repetitions']))
 lock=(ROOT/'build'/('benchmark-cpu-'+str(a.cpu)+'.lock')).open('a+')
 try:fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError:raise SystemExit('Another native suite is already using CPU '+str(a.cpu))
 if a.repetitions<1 or a.warmups<0 or any(not 0<x<1 for x in a.alphas) or len(set(a.alphas))!=len(a.alphas):p.error('invalid repetitions, warmups, or alphas')
 if len(set(a.datasets))!=len(a.datasets) or len(set(a.codecs))!=len(a.codecs):p.error('duplicate dataset or codec')
 inventory=json.loads(a.inventory.read_text());fields=[];excluded=[]
 for dataset in a.datasets:
  key='Miranda-float' if dataset=='Miranda' and a.miranda_precision=='float32' else dataset
  for source in inventory[key]:
   row={**source,'dataset':dataset,'shape':SHAPES[dataset],'field':Path(source['path']).stem}
   size=(8 if row['dtype']=='float64' else 4)
   elements=1
   for n in row['shape']:elements*=n
   if elements*size!=row['bytes']:raise ValueError('Shape/dtype mismatch: '+row['path'])
   if row['nonfinite']:excluded.append({**row,'reason':'nonfinite input; outside finite error-bounded protocol'})
   elif row['max']==row['min']:excluded.append({**row,'reason':'zero value range; range-relative bound and PSNR undefined'})
   else:fields.append(row)
 manifests={key:ROOT/path for key,path in {'legacy':'build/manifest.json','typed':'build/typed/manifest.json'}.items()}
 builds={key:sha(path) for key,path in manifests.items()}
 for path in manifests.values():
  m=json.loads(path.read_text())
  for file,digest in m['native_sha256'].items():
   if sha(ROOT/file)!=digest:raise ValueError('Native source differs from build: '+file)
 config={'schema_version':2,'datasets':a.datasets,'fields':fields,'excluded':excluded,'codecs':a.codecs,
  'alphas':a.alphas,'repetitions':a.repetitions,'warmups':a.warmups,'cpu':a.cpu,'seed':a.seed,
  'miranda_precision':a.miranda_precision,'builds':builds,'reuse_nyx':a.reuse_nyx}
 cp=out/'config.json'
 if cp.exists():
  if not a.resume:p.error('run exists; choose a new output or use --resume')
  if json.loads(cp.read_text())!=config:p.error('configuration/build/input inventory changed')
 else:dump(cp,config)
 for key,path in manifests.items():shutil.copyfile(path,out/(key+'_build_manifest.json'))
 binaries={}
 for f in fields:
  kind='legacy' if f['dtype']=='float32' and f['shape'][0]>1 else 'typed'
  for codec in a.codecs:
   path=ROOT/('build/bin/bench_'+codec.lower() if kind=='legacy' else 'build/typed/bin/bench_'+codec.lower()+('_f64' if f['dtype']=='float64' else '_f32'))
   binaries[str(path)]={'sha256':sha(path),'kind':kind}
 metadata={'host':platform.node(),'platform':platform.platform(),'python':sys.version,
  'cpuinfo':Path('/proc/cpuinfo').read_text().split('model name')[1].split('\n')[0].strip(':\t '),
  'binaries':binaries,'created':datetime.datetime.now().isoformat(),
  'timing_scope':'native adapter operation including configuration/allocation; excludes input copy, file I/O, process startup, validation and final output destruction',
  'error_mode':'range-relative pointwise absolute error: alpha*(max-min)',
  'SPERR_float32_policy':'reserve one worst-case output float32 ULP when bound > 2 ULP; otherwise half nominal bound',
  'SPERR_float64_policy':'pass nominal bound; no float32 output conversion',
  'SPERR_2D':'official 2D C API; include native 10-byte header; no 3D padding',
  'SPERR_3D_chunks':'min(dimension,256) on each axis',
  'units':'MiB/s = 1048576 bytes/s for aggregate reports','order':'C (z,y,x), x fastest; z=1 denotes true 2D',
  'resource_sampling':'cumulative /proc PID CPU/fault stats at result delivery, plus per-job child rusage; diagnostic only, outside native API clocks',
  'resource_clock_ticks_per_second':os.sysconf('SC_CLK_TCK'),
  'reuse_from':[str(path) for path,_ in sources],
  'refill_policy':'retain the compatible measured prefix and its warmups; measure only missing repeats after fresh warmups; extra warmups are validated and kept in driver logs',
  'excluded_fields':excluded,'project_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()}
 if (out/'metadata.json').exists():
  prior=json.loads((out/'metadata.json').read_text());metadata['created']=prior['created']
  metadata['project_commit_initial']=prior.get('project_commit_initial',prior['project_commit'])
  metadata['resumes']=prior.get('resumes',[])+[{'at':datetime.datetime.now().isoformat(),'project_commit':metadata['project_commit']}]
 dump(out/'metadata.json',metadata)
 env=os.environ.copy();env.update({k:'1' for k in ['OMP_NUM_THREADS','OMP_THREAD_LIMIT','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']});env['OMP_DYNAMIC']='FALSE'
 jobs=[(f,c) for f in fields for c in a.codecs];random.Random(a.seed).shuffle(jobs)
 hashes={};failures=[];completed=0;reused=0
 def reused_rows(f,c,digest):
  stem=f['field']+'__'+c;kind='legacy' if f['dtype']=='float32' and f['shape'][0]>1 else 'typed'
  best=None
  for source,source_repetitions in sources:
   prefix=min(a.repetitions,source_repetitions)
   if prefix<1 or (best and prefix<=best[3]):continue
   folder=source/f['dataset'];done=folder/(stem+'.done.json');raw=folder/(stem+'.jsonl')
   if not done.is_file() or not raw.is_file():continue
   old=json.loads(done.read_text())
   if old['status']!='ok' or old['returncode'] or old['input_sha256']!=digest or old['max_observed_threads']>1:continue
   candidates=list(map(json.loads,raw.read_text().splitlines()));picked=[]
   for alpha in a.alphas:
    rows=[r for r in candidates if r['alpha']==alpha and ((r['warmup'] and 1-a.warmups<=r['repeat']<=0) or (not r['warmup'] and 1<=r['repeat']<=prefix))]
    if len(rows)!=a.warmups+prefix or len({(r['warmup'],r['repeat']) for r in rows})!=len(rows):break
    if any(r['build_manifest_sha256']!=builds[kind] or r['input_sha256']!=digest or r['status']!='ok' or r['cpu']!=a.cpu or r['shape']!=f['shape'] or r['dtype']!=f['dtype'] or r['dataset']!=f['dataset'] or r['field']!=f['field'] or r['codec']!=c for r in rows):break
    picked.extend({**r,'reused':True,'measurement_origin':r.get('measurement_origin',str(raw)),'reuse_source':str(raw)} for r in rows)
   else:
    best=(picked,[str(raw)],old['max_observed_threads'],prefix)
    if prefix==a.repetitions:return best
  if not a.reuse_nyx or f['dataset']!='NYX':return best
  rows=[];origins=[];threads=0
  for alpha in a.alphas:
   folder=ROOT/'results'/('nyx-alpha-1e-1' if alpha==.1 else 'nyx-single-thread')
   stem=f['field']+'__'+c;done=folder/(stem+'.done.json');raw=folder/(stem+'.jsonl')
   if not done.exists():return best
   old=json.loads(done.read_text())
   if old['status']!='ok' or old['input_sha256']!=digest:return best
   selected=[r for r in map(json.loads,raw.read_text().splitlines()) if r['alpha']==alpha and
    ((r['warmup'] and 1-a.warmups<=r['repeat']<=0) or (not r['warmup'] and 1<=r['repeat']<=a.repetitions))]
   if len(selected)!=a.warmups+a.repetitions:return best
   if any(r['build_manifest_sha256']!=builds['legacy'] or r['status']!='ok' or r['cpu']!=a.cpu for r in selected):return best
   rows.extend({**r,'dtype':'float32','measurement_origin':str(raw),'reused':True,'build_kind':'legacy'} for r in selected)
   origins.append(str(raw));threads=max(threads,old['max_observed_threads'])
  return rows,origins,threads,a.repetitions
 for f,codec in jobs:
  folder=out/f['dataset'];folder.mkdir(exist_ok=True);stem=f['field']+'__'+codec
  done=folder/(stem+'.done.json');raw=folder/(stem+'.jsonl');path=Path(f['path'])
  if str(path) not in hashes:hashes[str(path)]=sha(path)
  digest=hashes[str(path)]
  if a.resume and raw.exists() and done.exists() and json.loads(done.read_text())['status']=='ok':
   if json.loads(done.read_text())['input_sha256']!=digest:raise ValueError('Input changed since previous run: '+str(path))
   completed+=1;print('RESUME_SKIP',f['dataset'],stem,flush=True);continue
  if a.resume and raw.exists() and done.exists() and repair_roundoff_job(ROOT,folder,stem,f,codec,digest,config,env):
   completed+=1;print('ROUNDING_REPAIRED',f['dataset'],stem,flush=True);continue
  if a.resume and any((folder/(stem+ext)).exists() for ext in ('.jsonl','.log','.done.json')):
   previous=folder/'attempts'/stem/datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f');previous.mkdir(parents=True)
   for ext in ('.jsonl','.log','.done.json'):
    old=folder/(stem+ext)
    if old.exists():shutil.move(old,previous/old.name)
  print('START',completed+1,'/',len(jobs),f['dataset'],stem,datetime.datetime.now().isoformat(),flush=True)
  imported=reused_rows(f,codec,digest);bad=extra_warmups=0;rc=0;job_resources=None
  rows,origins,threads,prefix=imported if imported else ([],[],0,0)
  count=sum(not r['warmup'] for r in rows);reused+=count
  prefix_stream=''.join(json.dumps(r,allow_nan=False)+'\n' for r in rows)
  import_log='Imported existing C++ API measurements from:\n'+'\n'.join(origins)+'\n' if origins else ''
  if prefix==a.repetitions:
   cmd=origins;raw.write_text(prefix_stream);(folder/(stem+'.log')).write_text(import_log)
  else:
   kind='legacy' if f['dtype']=='float32' and f['shape'][0]>1 else 'typed'
   binary=ROOT/('build/bin/bench_'+codec.lower() if kind=='legacy' else 'build/typed/bin/bench_'+codec.lower()+('_f64' if f['dtype']=='float64' else '_f32'))
   aliases={}
   for alpha in a.alphas:
    actual={r.get('native_alpha',alpha) for r in rows if r['alpha']==alpha} or {alpha}
    if len(actual)!=1:raise ValueError('Inconsistent effective tolerance in imported repeats: '+stem)
    native_alpha=actual.pop()
    if native_alpha in aliases:raise ValueError('Aliased native tolerances: '+stem)
    aliases[native_alpha]=alpha
   cmd=['taskset','-c',str(a.cpu),str(binary),str(path),*map(str,f['shape']),str(a.repetitions-prefix),str(a.warmups),*map(str,aliases)]
   usage0=resource.getrusage(resource.RUSAGE_CHILDREN);wall0=time.perf_counter()
   with (folder/(stem+'.log')).open('w') as log,raw.open('w') as stream:
    log.write(import_log);stream.write(prefix_stream);stream.flush()
    proc=subprocess.Popen(cmd,cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1)
    for line in proc.stdout:
     log.write(line);log.flush()
     try:threads=max(threads,len(list(Path(f'/proc/{proc.pid}/task').iterdir())))
     except FileNotFoundError:pass
     if line.startswith('LFCB_RESULT '):
      r=json.loads(line[len('LFCB_RESULT '):]);r.update({'dataset':f['dataset'],'field':f['field'],'dtype':f['dtype'],'shape':f['shape'],'input_sha256':digest,'build_manifest_sha256':builds[kind],'build_kind':kind,'reused':False})
      r=normalize_bound(r,aliases[r['alpha']])
      try:
       stat=Path(f'/proc/{proc.pid}/stat').read_text().rsplit(')',1)[1].split()
       r['observed_child_cpu_seconds_total']=(int(stat[11])+int(stat[12]))/os.sysconf('SC_CLK_TCK')
       r['observed_child_minor_faults_total']=int(stat[7]);r['observed_child_major_faults_total']=int(stat[9])
       r['observed_job_wall_seconds_total']=time.perf_counter()-wall0
      except FileNotFoundError:pass
      if r['cpu']!=a.cpu or r['min']!=f['min'] or r['max']!=f['max']:r['status']='provenance_mismatch'
      bad+=r['status']!='ok'
      if prefix and r['warmup']:
       extra_warmups+=1
       print('ADDITIONAL_WARMUP',f['dataset'],stem,'alpha',r['alpha'],'status',r['status'],flush=True)
       continue
      if prefix:
       r['native_repeat']=r['repeat'];r['execution_repeat_offset']=prefix;r['repeat']+=prefix
      stream.write(json.dumps(r,allow_nan=False)+'\n');stream.flush();count+=not r['warmup']
      print('POINT',f['dataset'],stem,'alpha',r['alpha'],'repeat',r['repeat'],'warmup',r['warmup'],'status',r['status'],flush=True)
    rc=proc.wait()
   usage1=resource.getrusage(resource.RUSAGE_CHILDREN)
   job_resources={'job_elapsed_wall_seconds':time.perf_counter()-wall0,'child_user_cpu_seconds':usage1.ru_utime-usage0.ru_utime,
    'child_system_cpu_seconds':usage1.ru_stime-usage0.ru_stime,'child_major_faults':usage1.ru_majflt-usage0.ru_majflt,
    'child_minor_faults':usage1.ru_minflt-usage0.ru_minflt,'child_involuntary_context_switches':usage1.ru_nivcsw-usage0.ru_nivcsw}
  expected_extra=len(a.alphas)*a.warmups if 0<prefix<a.repetitions else 0
  status='ok' if rc==0 and count==len(a.alphas)*a.repetitions and bad==0 and threads<=1 and extra_warmups==expected_extra else 'failed'
  result={'status':status,'returncode':rc,'measured_records':count,'bad_records':bad,'max_observed_threads':threads,
   'command_or_import_origins':cmd,'input_sha256':digest,'reused':prefix==a.repetitions,'job_resources':job_resources,
   'import_origins':origins,'imported_repetitions_per_bound':prefix,'native_repetitions_per_bound':a.repetitions-prefix,
   'additional_warmups_logged':extra_warmups}
  dump(done,result);completed+=1
  if status!='ok':failures.append(f['dataset']+'/'+stem)
  progress={'completed_jobs':completed,'expected_jobs':len(jobs),'failed_jobs':failures,'reused_measured_records_this_process':reused,'last_job':f['dataset']+'/'+stem,'updated':datetime.datetime.now().isoformat()}
  dump(out/'progress.json',progress);print('DONE',f['dataset'],stem,result,flush=True)
 dump(out/'progress.json',{'completed_jobs':completed,'expected_jobs':len(jobs),'failed_jobs':failures,'reused_measured_records_this_process':reused,'last_job':f['dataset']+'/'+stem if jobs else None,'updated':datetime.datetime.now().isoformat()})
 summary={'status':'ok' if not failures else 'failed','jobs':len(jobs),'failures':failures,'expected_measured_records':len(jobs)*len(a.alphas)*a.repetitions,'excluded':excluded}
 dump(out/'suite_complete.json',summary);print('SUITE_COMPLETE',summary,flush=True)
 return bool(failures)
if __name__=='__main__':raise SystemExit(main())
