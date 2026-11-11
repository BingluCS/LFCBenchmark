#!/usr/bin/env python3
"""Validate complete results, aggregate using byte/time totals, and plot."""
import argparse, collections, csv, json, math, statistics
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from audit_run import audit

ORDER=['ZFP','PFPL','SPERR','SZ3','Falcons']
COLORS={'ZFP':'#e69f00','PFPL':'#56b4e9','SPERR':'#009e73','SZ3':'#7a5195','Falcons':'#d62728'}
def write_csv(path,rows):
 with path.open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def main():
 p=argparse.ArgumentParser();p.add_argument('run',type=Path);a=p.parse_args();root=a.run.resolve()
 audit(root)
 cfg=json.loads((root/'config.json').read_text());expected=set(cfg['codecs'])
 fields=sorted(Path(f).stem for f in cfg['files']);alphas=cfg['alphas'];reps=cfg['repetitions']
 records=[]
 for field in fields:
  for codec in expected:
   name=field+'__'+codec
   done=root/(name+'.done.json')
   if not done.exists() or json.loads(done.read_text())['status']!='ok':raise SystemExit('incomplete/failed job: '+name)
   rows=[json.loads(x) for x in (root/(name+'.jsonl')).read_text().splitlines()]
   if any(x['status']!='ok' for x in rows):raise SystemExit('error bound or decode failure: '+name)
   records.extend(r for r in rows if not r['warmup'])
 grouped=collections.defaultdict(list)
 for r in records:grouped[r['field'],r['codec'],r['alpha']].append(r)
 summaries=[]
 for field in fields:
  for codec in ORDER:
   if codec not in expected:continue
   for alpha in alphas:
    values=grouped[field,codec,alpha]
    if len(values)!=reps or {r['repeat'] for r in values}!=set(range(1,reps+1)):raise SystemExit(f'missing/duplicate repeat {field} {codec} {alpha}')
    mean=lambda k:statistics.fmean(r[k] for r in values)
    raw=values[0]['original_bytes'];compressed=mean('compressed_bytes');c=mean('compress_seconds');d=mean('decompress_seconds')
    nrmse=math.sqrt(statistics.fmean(r['nrmse']**2 for r in values))
    summaries.append({'field':field,'codec':codec,'alpha':alpha,'repetitions':reps,'original_bytes':raw,'mean_compressed_bytes':compressed,'ratio':raw/compressed,'bits_per_value':compressed*8/values[0]['elements'],'mean_compress_seconds':c,'mean_decompress_seconds':d,'compress_MiB_s':raw/1048576/c,'decompress_MiB_s':raw/1048576/d,'compress_time_std_seconds':statistics.stdev(r['compress_seconds'] for r in values) if reps>1 else 0,'decompress_time_std_seconds':statistics.stdev(r['decompress_seconds'] for r in values) if reps>1 else 0,'nrmse':nrmse,'psnr_db':-20*math.log10(nrmse) if nrmse else None,'max_abs_error':max(r['max_abs_error'] for r in values),'absolute_bound':values[0]['absolute_bound']})
 write_csv(root/'summary_by_field.csv',summaries)
 aggregate=[]
 for codec in ORDER:
  if codec not in expected:continue
  for alpha in alphas:
   rows=[r for r in summaries if r['codec']==codec and r['alpha']==alpha]
   raw=sum(r['original_bytes'] for r in rows);comp=sum(r['mean_compressed_bytes'] for r in rows);c=sum(r['mean_compress_seconds'] for r in rows);d=sum(r['mean_decompress_seconds'] for r in rows)
   nr=math.sqrt(statistics.fmean(r['nrmse']**2 for r in rows))
   aggregate.append({'codec':codec,'alpha':alpha,'fields':len(rows),'ratio':raw/comp,'bits_per_value':32*comp/raw,'compress_MiB_s':raw/1048576/c,'decompress_MiB_s':raw/1048576/d,'psnr_db':-20*math.log10(nr) if nr else None,'rms_field_nrmse':nr})
 write_csv(root/'summary_aggregate.csv',aggregate)
 figdir=root/'figures';figdir.mkdir(exist_ok=True)
 plt.rcParams.update({'font.size':11,'axes.spines.top':False,'axes.spines.right':False,'pdf.fonttype':42,'ps.fonttype':42})
 def save(fig,name):
  fig.savefig(figdir/(name+'.png'),dpi=180,bbox_inches='tight');fig.savefig(figdir/(name+'.pdf'),bbox_inches='tight');plt.close(fig)
 def rd(ax,rows,title):
  for codec in ORDER:
   rr=sorted([r for r in rows if r['codec']==codec and r['psnr_db'] is not None],key=lambda r:r['bits_per_value'])
   if rr:ax.plot([r['bits_per_value'] for r in rr],[r['psnr_db'] for r in rr],'-o',color=COLORS[codec],label=codec,ms=4)
  ax.set(xlabel='Bit rate (bits/value)',ylabel='PSNR (dB)',title=title);ax.grid(alpha=.2)
 def ratios(ax,rows,title):
  for codec in ORDER:
   rr=sorted([r for r in rows if r['codec']==codec],key=lambda r:r['alpha'])
   if rr:ax.plot([r['alpha'] for r in rr],[r['ratio'] for r in rr],'-o',color=COLORS[codec],label=codec,ms=4)
  ax.set(xscale='log',yscale='log',xlabel='Value-range relative error bound',ylabel='Compression ratio',title=title);ax.grid(alpha=.2)
 def th(ax,rows,title,metric):
  canonical=[x for x in [1e-2,1e-3,1e-4] if x in alphas]
  if not canonical:canonical=sorted(alphas,reverse=True)
  x=np.arange(len(canonical));codecs=[c for c in ORDER if c in expected];width=.8/len(codecs)
  for i,codec in enumerate(codecs):
   yy=[next(r[metric] for r in rows if r['codec']==codec and r['alpha']==alpha) for alpha in canonical]
   ax.bar(x+(i-(len(codecs)-1)/2)*width,yy,width=width,color=COLORS[codec],label=codec)
  ax.set_xticks(x,[f'{v:.0e}' for v in canonical]);ax.set(xlabel='Value-range relative error bound',ylabel='Throughput (MiB/s)',title=title);ax.grid(axis='y',alpha=.2)
 fig,ax=plt.subplots(figsize=(7.8,5.2),constrained_layout=True);rd(ax,aggregate,'NYX: single-thread RD curves (six fields)');ax.legend();save(fig,'nyx_rd_aggregate')
 fig,axs=plt.subplots(2,3,figsize=(15,8),constrained_layout=True)
 for ax,field in zip(axs.flat,fields):rd(ax,[r for r in summaries if r['field']==field],field)
 axs.flat[0].legend(fontsize=9);save(fig,'nyx_rd_by_field')
 fig,ax=plt.subplots(figsize=(7.8,5.2),constrained_layout=True);ratios(ax,aggregate,'NYX: single-thread compression ratio');ax.legend();save(fig,'nyx_ratio_aggregate')
 fig,axs=plt.subplots(2,3,figsize=(15,8),constrained_layout=True)
 for ax,field in zip(axs.flat,fields):ratios(ax,[r for r in summaries if r['field']==field],field)
 axs.flat[0].legend(fontsize=9);save(fig,'nyx_ratio_by_field')
 fig,axs=plt.subplots(1,2,figsize=(13,5),constrained_layout=True)
 for ax,metric,title in zip(axs,['compress_MiB_s','decompress_MiB_s'],['NYX compression','NYX decompression']):th(ax,aggregate,title,metric)
 axs[1].legend(fontsize=9);save(fig,'nyx_throughput_aggregate')
 for metric,stem in [('compress_MiB_s','compression'),('decompress_MiB_s','decompression')]:
  fig,axs=plt.subplots(2,3,figsize=(15,8),constrained_layout=True)
  for ax,field in zip(axs.flat,fields):th(ax,[r for r in summaries if r['field']==field],field,metric)
  handles,labels=axs.flat[0].get_legend_handles_labels()
  fig.legend(handles,labels,loc='lower center',bbox_to_anchor=(.5,1.0),ncol=len(handles),frameon=False)
  save(fig,'nyx_'+stem+'_by_field')
 print('Complete:',len(records),'measured records;',len(summaries),'field/config summaries;',len(aggregate),'aggregate points')
 for row in aggregate:
  if row['alpha'] in [1e-2,1e-3,1e-4]:print(row)
if __name__=='__main__':main()
