#!/usr/bin/env python3
"""Read live job progress without including archived/interrupted attempts."""
import argparse,collections,datetime,json
from pathlib import Path
def progress(root):
 root=Path(root);cfg=json.loads((root/'config.json').read_text())
 status=json.loads((root/'pipeline_status.json').read_text()) if (root/'pipeline_status.json').exists() else {}
 done=measured=warm=bad=reused=failed=0;latest=None;by_dataset={}
 for dataset in cfg['datasets']:
  records=[];dd=[]
  for f in (root/dataset).glob('*.jsonl'):
   if latest is None or f.stat().st_mtime>latest.stat().st_mtime:latest=f
   for line in f.read_text().splitlines():
    try:records.append(json.loads(line))
    except json.JSONDecodeError:pass
  for f in (root/dataset).glob('*.done.json'):dd.append(json.loads(f.read_text()))
  n=sum(not r['warmup'] for r in records);b=sum(r['status']!='ok' for r in records)
  measured+=n;warm+=sum(r['warmup'] for r in records);bad+=b;done+=len(dd);failed+=sum(d['status']!='ok' for d in dd)
  reused+=sum(not r['warmup'] and r.get('reused',False) for r in records)
  by_dataset[dataset]={'jobs':len(dd),'measured':n,'bad_records':b}
 result={'time':datetime.datetime.now().isoformat(),'stage':status.get('stage'),'jobs_done':done,
  'jobs_expected':len(cfg['fields'])*len(cfg['codecs']),'measured':measured,
  'measured_expected':len(cfg['fields'])*len(cfg['codecs'])*len(cfg['alphas'])*cfg['repetitions'],
  'warmups':warm,'bad_records':bad,'failed_jobs':failed,'reused':reused,
  'current':str(latest.relative_to(root)) if latest else None,'datasets':by_dataset}
 return result
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('run',type=Path);a=p.parse_args();print(json.dumps(progress(a.run)))
