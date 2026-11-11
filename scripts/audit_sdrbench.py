#!/usr/bin/env python3
"""Validate the complete six-dataset suite without dropping failed cases."""
import argparse,hashlib,json,math
from pathlib import Path
from run_sdrbench import sha,dump
def audit(root,check_inputs=False,*,write_report=True):
 root=Path(root).resolve();cfg=json.loads((root/'config.json').read_text());meta=json.loads((root/'metadata.json').read_text())
 for kind,digest in cfg['builds'].items():
  if sha(root/(kind+'_build_manifest.json'))!=digest:raise ValueError('Archived build manifest changed: '+kind)
 count=warmups=reused=jobs=refill_warmups=0;max_threads=0;deterministic=True;digests={};adjustments=[]
 for field in cfg['fields']:
  dataset=field['dataset'];path=Path(field['path']);shape=field['shape'];size=8 if field['dtype']=='float64' else 4
  for codec in cfg['codecs']:
   stem=field['field']+'__'+codec;folder=root/dataset
   done=json.loads((folder/(stem+'.done.json')).read_text())
   if done['status']!='ok' or done['returncode'] or done['max_observed_threads']>1:raise ValueError('Failed/nonserial job: '+dataset+'/'+stem)
   max_threads=max(max_threads,done['max_observed_threads'])
   prefix=done.get('imported_repetitions_per_bound',0);extra=done.get('additional_warmups_logged',0)
   if extra!=(len(cfg['alphas'])*cfg['warmups'] if 0<prefix<cfg['repetitions'] else 0):raise ValueError('Refill warmup coverage: '+stem)
   refill_warmups+=extra
   if check_inputs:
    if path not in digests:digests[path]=sha(path)
    if digests[path]!=done['input_sha256']:raise ValueError('Input changed: '+str(path))
   rows=[json.loads(l) for l in (folder/(stem+'.jsonl')).read_text().splitlines()]
   if len(rows)!=len(cfg['alphas'])*(cfg['repetitions']+cfg['warmups']):raise ValueError('Wrong record count: '+stem)
   for alpha in cfg['alphas']:
    rr=[r for r in rows if r['alpha']==alpha]
    if any('native_alpha' in r for r in rr):
     bounds={(r.get('native_alpha',alpha),r['effective_bound']) for r in rr}
     if len(bounds)!=1 or not all('native_alpha' in r for r in rr):raise ValueError('Inconsistent retry policy: '+stem)
     actual,effective=next(iter(bounds))
     adjustments.append({'dataset':dataset,'field':field['field'],'codec':codec,'alpha':alpha,
                         'nominal_bound':rr[0]['absolute_bound'],'effective_bound':effective,'native_alpha':actual})
    for warm,numbers in [(False,set(range(1,cfg['repetitions']+1))),(True,set(range(1-cfg['warmups'],1)))]:
     selected=[r for r in rr if r['warmup']==warm]
     if len(selected)!=len(numbers) or {r['repeat'] for r in selected}!=numbers:raise ValueError('Coverage failure: '+stem)
    deterministic &= len({(r['compressed_bytes'],r['rmse'],r['max_abs_error']) for r in rr})==1
   for r in rows:
    valid=(r['dataset']==dataset and r['field']==field['field'] and r['codec']==codec and r['shape']==shape
     and r['dtype']==field['dtype'] and r['elements']==math.prod(shape) and r['original_bytes']==size*math.prod(shape)
     and r['input_sha256']==done['input_sha256'] and r['cpu']==cfg['cpu']
     and r['build_manifest_sha256']==cfg['builds'][r['build_kind']]
     and r['status']=='ok' and r['violations']==0 and r['nonfinite']==0
     and r['max_abs_error']<=r['absolute_bound'] and 0<r['effective_bound']<=r['absolute_bound']
     and r['min']==field['min'] and r['max']==field['max']
     and r['absolute_bound']==r['alpha']*(r['max']-r['min']) and r['compressed_bytes']>0)
    valid &= all(math.isfinite(r[k]) and r[k]>0 for k in ('compress_seconds','decompress_seconds'))
    if not valid:raise ValueError('Invalid record: '+dataset+'/'+stem+' '+str(r))
   count+=sum(not r['warmup'] for r in rows);warmups+=sum(r['warmup'] for r in rows)
   reused+=sum(not r['warmup'] and r.get('reused',False) for r in rows);jobs+=1
 report={'status':'ok','datasets':cfg['datasets'],'tested_fields':len(cfg['fields']),'excluded_fields':cfg['excluded'],
  'jobs':jobs,'measured_records':count,'warmup_records':warmups,'additional_refill_warmups_logged':refill_warmups,'reused_measured_records':reused,
  'strict_bound_violations':0,'max_observed_threads':max_threads,'cpu':cfg['cpu'],'inputs_rehashed':check_inputs,
  'rounding_adjusted_configurations':adjustments,
  'repeat_size_and_error_metrics_identical':bool(deterministic),'project_commit':meta['project_commit']}
 if write_report:dump(root/'audit.json',report)
 return report
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('run',type=Path);p.add_argument('--check-inputs',action='store_true');a=p.parse_args()
 print(json.dumps(audit(a.run,a.check_inputs),indent=2))
