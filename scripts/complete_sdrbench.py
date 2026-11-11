#!/usr/bin/env python3
"""Run, plot, audit, and archive a suite; safe to run under nohup."""
import argparse,datetime,json,shutil,subprocess,sys,tarfile
from pathlib import Path
from run_sdrbench import ROOT,dump,sha
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
 p.add_argument('--resume',action='store_true');p.add_argument('--per-field',action='store_true');a,forward=p.parse_known_args()
 out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
 def state(name,**extra):
  report={'stage':name,'updated':datetime.datetime.now().isoformat(),**extra};dump(out/'pipeline_status.json',report);print(json.dumps(report),flush=True)
 cmds=[('benchmark',[sys.executable,'-u',str(ROOT/'scripts/run_sdrbench.py'),'--output',str(out),*forward,*(['--resume'] if a.resume else [])]),
       ('plot',[sys.executable,str(ROOT/'scripts/plot_sdrbench.py'),str(out),*(['--per-field'] if a.per_field else [])]),
       ('audit',[sys.executable,str(ROOT/'scripts/audit_sdrbench.py'),str(out),'--check-inputs'])]
 for stage,cmd in cmds:
  with (out/(stage+'.log')).open('a' if a.resume else 'w') as log:
   proc=subprocess.Popen(cmd,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
   state(stage,child_pid=proc.pid,command=cmd);rc=proc.wait()
  if rc:
   state('failed',failed_stage=stage,returncode=rc,log=str(out/(stage+'.log')));return rc
 state('archive')
 for name in ['README.md','sources.lock.json','reference.lock.json']:shutil.copyfile(ROOT/name,out/name)
 archive=out.parent/(out.name+'-delivery.tar.gz')
 try:
  subprocess.run(['git','bundle','create','--quiet',str(out/'lfcbenchmark-source.bundle'),'--all'],cwd=ROOT,check=True)
  with tarfile.open(archive,'w:gz') as t:
   t.add(out,arcname=out.name,filter=lambda m:None if m.name.endswith('/pipeline_status.json') else m)
  digest=sha(archive);(archive.parent/(archive.name+'.sha256')).write_text(digest+'  '+archive.name+'\n')
 except Exception as exc:
  state('failed',failed_stage='archive',error=str(exc));raise
 state('complete',archive=str(archive),archive_sha256=digest,audit=json.loads((out/'audit.json').read_text()))
 print('ARCHIVE',str(archive),digest,flush=True)
 return 0
if __name__=='__main__':raise SystemExit(main())
