#!/usr/bin/env python3
"""Plot complete dataset comparisons and export every field/configuration metric."""
import argparse,collections,csv,json,math,re,statistics
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import NullLocator
from audit_sdrbench import audit
from plot_panels import compact_axis, label_row, panel_row
ORDER=['ZFP','PFPL','SPERR','SZ3','Falcons']
DATASET_ORDER=['NYX','Hurricane','Miranda','SCALE','CESM','JHTDB']
DATASET_LABELS={'Hurricane':'Hurricane Isabel','SCALE':'SCALE-LETKF','CESM':'CESM-ATM'}
LABELS={'SZ3':'SZ3.3'}
COLORS={'ZFP':'#3C4248','PFPL':'#FB9700','SPERR':'#93999F','SZ3':'#1F77B4','Falcons':'#D62728'}
MARKERS={'ZFP':'s','PFPL':'v','SPERR':'o','SZ3':'^','Falcons':'D'}
LINESTYLES={'ZFP':'-.','PFPL':'--','SPERR':':','SZ3':'--','Falcons':'-'}
THROUGHPUT_OMIT={1e-1,1e-6}
RD_MIN_ALPHA=1e-5
PARETO_ALPHA=1e-3
RD_WINDOWS={
 'NYX': ((0,3.5),(50,110),((1.5,2.5),(85,100))),
 'Miranda': ((0,3),(40,120),((.35,.90),(88,103))),
 'Hurricane': ((0,6),(30,110),((2,4),(70,96))),
 'SCALE': ((0,4),(30,120),((.75,1.90),(80,100))),
 'CESM': ((0,4.5),(30,110),((1.5,2.8),(80,96))),
 'JHTDB': ((0,6),(40,115),((1,2.9),(75,97))),
}

def bound_label(alpha):
 mantissa,exponent=f'{alpha:.10E}'.split('E')
 return mantissa.rstrip('0').rstrip('.')+'E'+str(int(exponent))

def hurricane_selection(fields):
 """Match notebook's log10-first grouping, independent of codec and bound."""
 selected={}
 for f in fields:
  if f['dataset']!='Hurricane':continue
  field=f['field'];name=Path(field).name.lower()
  key=re.sub(r'\.(?:bin(?:\.(?:f32|dat))?|f32|dat)$','',re.sub(r'[._]log10','',name))
  priority=(not bool(re.search(r'[._]log10',name)),field)
  if key not in selected or priority<selected[key][0]:selected[key]=(priority,field)
 return {field for _,field in selected.values()}

def nondominated(rows,throughput):
 return {p['codec'] for p in rows if not any(
  q[throughput]>=p[throughput] and q['ratio']>=p['ratio'] and
  (q[throughput]>p[throughput] or q['ratio']>p['ratio']) for q in rows)}

def write_csv(path,rows):
 with path.open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path);p.add_argument('--per-field',action='store_true')
 p.add_argument('--output',type=Path,help='write plot products to a separate directory')
 p.add_argument('--hurricane-log-preferred',action='store_true',help='aggregate one representation per Hurricane field, preferring log10')
 a=p.parse_args();root=a.run.resolve()
 audit(root,write_report=False);cfg=json.loads((root/'config.json').read_text());groups=collections.defaultdict(list)
 out=a.output.resolve() if a.output else (root/'plot_log_preferred' if a.hurricane_log_preferred else root)
 out.mkdir(parents=True,exist_ok=True)
 datasets=sorted(cfg['datasets'],key=lambda d:DATASET_ORDER.index(d) if d in DATASET_ORDER else len(DATASET_ORDER))
 codecs=[c for c in ORDER if c in cfg['codecs']]
 alphas=sorted(cfg['alphas'],reverse=True)
 throughput_alphas=[alpha for alpha in alphas if alpha not in THROUGHPUT_OMIT]
 hurricane_fields=hurricane_selection(cfg['fields'])
 exclude=[f['field'] for f in cfg['fields'] if f['dataset']=='Hurricane' and f['field'] not in hurricane_fields] if a.hurricane_log_preferred else []
 for f in cfg['fields']:
  for codec in cfg['codecs']:
   raw=root/f['dataset']/(f['field']+'__'+codec+'.jsonl')
   for row in map(json.loads,raw.read_text().splitlines()):
    if not row['warmup']:groups[f['dataset'],f['field'],codec,row['alpha']].append(row)
 summary=[]
 for (dataset,field,codec,alpha),rows in sorted(groups.items()):
  mean=lambda k:statistics.fmean(r[k] for r in rows)
  raw=rows[0]['original_bytes'];comp=mean('compressed_bytes');ct=mean('compress_seconds');dt=mean('decompress_seconds');nr=math.sqrt(statistics.fmean(r['nrmse']**2 for r in rows))
  summary.append({'dataset':dataset,'field':field,'dtype':rows[0]['dtype'],'codec':codec,'alpha':alpha,'repetitions':len(rows),
   'original_bytes':raw,'elements':rows[0]['elements'],'mean_compressed_bytes':comp,'ratio':raw/comp,'bits_per_value':8*comp/rows[0]['elements'],
   'mean_compress_seconds':ct,'mean_decompress_seconds':dt,'compress_MiB_s':raw/1048576/ct,'decompress_MiB_s':raw/1048576/dt,
   'compress_time_std_seconds':statistics.stdev(r['compress_seconds'] for r in rows) if len(rows)>1 else None,
   'decompress_time_std_seconds':statistics.stdev(r['decompress_seconds'] for r in rows) if len(rows)>1 else None,
   'nrmse':nr,'psnr_db':-20*math.log10(nr) if nr else None,'max_abs_error':max(r['max_abs_error'] for r in rows),
   'absolute_bound':rows[0]['absolute_bound'],'effective_bound':rows[0]['effective_bound'],'reused':all(r.get('reused',False) for r in rows)})
 variability=[]
 for item in summary:
  rows=groups[item['dataset'],item['field'],item['codec'],item['alpha']]
  for phase in ['compress','decompress']:
   values=[r[phase+'_seconds'] for r in rows];mean=statistics.fmean(values)
   std=statistics.stdev(values) if len(values)>1 else None;cv=std/mean if std is not None else None
   item[phase+'_time_cv']=cv;item[phase+'_time_min_seconds']=min(values)
   item[phase+'_time_max_seconds']=max(values);item[phase+'_time_median_seconds']=statistics.median(values)
   if cv is not None and cv>.3:
    variability.append({k:item[k] for k in ('dataset','field','codec','alpha','repetitions')}|
     {'phase':phase,'mean_seconds':mean,'std_seconds':std,'cv':cv,'min_seconds':min(values),'max_seconds':max(values),'median_seconds':statistics.median(values)})
 write_csv(out/'summary_by_field.csv',summary)
 if variability:write_csv(out/'timing_variability.csv',variability)
 else:(out/'timing_variability.csv').write_text('dataset,field,codec,alpha,repetitions,phase,mean_seconds,std_seconds,cv,min_seconds,max_seconds,median_seconds\n')
 (out/'timing_quality.json').write_text(json.dumps({'cv_threshold':.3,'measured_repetitions':cfg['repetitions'],'spread_estimable':cfg['repetitions']>1,'flagged_field_config_phases':len(variability),
  'primary_estimator':'arithmetic mean of all measured times; no timing outlier discarded',
  'median_estimator':'total bytes divided by sum of per-field median times; supplementary only',
  'flagged':variability},indent=2)+'\n')
 selected=[r for r in summary if not (r['dataset']=='Hurricane' and r['field'] in exclude)]
 (out/'plot_metadata.json').write_text(json.dumps({
  'style_reference':'SZ-analysis.ipynb (serial throughput, ratio, rate-distortion, ratio/throughput)',
  'dataset_order':datasets,'compressor_order':codecs,'error_bounds':alphas,'repetitions':cfg['repetitions'],
  'rd_figure_bounds':[alpha for alpha in alphas if alpha>=RD_MIN_ALPHA],
  'throughput_figure_bounds':throughput_alphas,
  'pareto_figure_bound':PARETO_ALPHA if PARETO_ALPHA in alphas else None,
  'hurricane_aggregation':'prefer supplied log10 representation' if a.hurricane_log_preferred else 'all tested representations',
  'hurricane_excluded_from_aggregates':sorted(exclude),'per_field_csv_contains_all_tested_fields':True,
  'throughput_units':'MiB/s (1 MiB = 1048576 bytes)','throughput_aggregation':'total input bytes / sum of per-field mean times',
  'ratio_aggregation':'total input bytes / total compressed bytes',
  'psnr_aggregation':'-20 log10(element-weighted RMS of normalized field RMSE)',
 },indent=2)+'\n')
 agg=[]
 for dataset in datasets:
  for codec in codecs:
   for alpha in alphas:
    rr=[r for r in selected if r['dataset']==dataset and r['codec']==codec and r['alpha']==alpha]
    raw=sum(r['original_bytes'] for r in rr);comp=sum(r['mean_compressed_bytes'] for r in rr);n=sum(r['elements'] for r in rr)
    nr=math.sqrt(sum(r['elements']*r['nrmse']**2 for r in rr)/n)
    entry={'dataset':dataset,'dtype':rr[0]['dtype'],'codec':codec,'alpha':alpha,'fields':len(rr),'ratio':raw/comp,'bits_per_value':8*comp/n,
     'compress_MiB_s':raw/1048576/sum(r['mean_compress_seconds'] for r in rr),'decompress_MiB_s':raw/1048576/sum(r['mean_decompress_seconds'] for r in rr),
     'psnr_db':-20*math.log10(nr) if nr else None,'rms_field_nrmse':nr}
    for phase in ['compress','decompress']:
     entry[phase+'_max_field_time_cv']=max((r[phase+'_time_cv'] for r in rr if r[phase+'_time_cv'] is not None),default=None)
     entry[phase+'_high_variability_fields']=sum((r[phase+'_time_cv'] or 0)>.3 for r in rr)
     entry[phase+'_MiB_s_from_field_medians']=raw/1048576/sum(r[phase+'_time_median_seconds'] for r in rr)
    agg.append(entry)
 write_csv(out/'summary_by_dataset.csv',agg)
 overall=[]
 metrics=('ratio','compress_MiB_s','decompress_MiB_s')
 for alpha in alphas:
  points=[]
  for codec in codecs:
   rr=[r for r in selected if r['codec']==codec and r['alpha']==alpha]
   raw=sum(r['original_bytes'] for r in rr)
   point={'codec':codec,'alpha':alpha,'fields':len(rr),'original_bytes':raw,
          'ratio':raw/sum(r['mean_compressed_bytes'] for r in rr)}
   for phase in ('compress','decompress'):
    point[phase+'_MiB_s']=raw/1048576/sum(r['mean_'+phase+'_seconds'] for r in rr)
    point[phase+'_high_variability_fields']=sum((r[phase+'_time_cv'] or 0)>.3 for r in rr)
   points.append(point)
  for metric in metrics:
   best=max(r[metric] for r in points)
   for r in points:r[metric+'_pct_of_best']=100*(r[metric]/best)
  overall.extend(points)
 write_csv(out/'summary_overall.csv',overall)
 figdir=out/'figures';figdir.mkdir(exist_ok=True)
 plt.rcParams.update({'font.size':11,'axes.titlesize':13,'axes.spines.top':False,'axes.spines.right':False,'pdf.fonttype':42,'ps.fonttype':42})
 def save(fig,name):
  fig.savefig(figdir/(name+'.png'),dpi=200,bbox_inches='tight')
  fig.savefig(figdir/(name+'.pdf'),bbox_inches='tight')
  plt.close(fig)
 def rd_lines(ax,rows,ms=5,lw=1.9):
  for codec in codecs:
   rr=sorted((r for r in rows if r['codec']==codec),key=lambda r:r['bits_per_value'])
   ax.plot([r['bits_per_value'] for r in rr],[r['psnr_db'] for r in rr],color=COLORS[codec],
    marker=MARKERS[codec],linestyle=LINESTYLES[codec],label=LABELS.get(codec,codec),ms=ms,lw=lw)
 def high_cv(row,phase):
  return (row.get(phase+'_max_field_time_cv',row.get(phase+'_time_cv')) or 0)>.3
 def panel(ax,rows,metric,title,zoom=False,compact=False):
  if metric=='rd':
   shown=[r for r in rows if r['alpha']>=RD_MIN_ALPHA and r['psnr_db'] is not None]
   rd_lines(ax,shown,ms=3.6 if compact else 5,lw=1.35 if compact else 1.9)
   ax.set(xlabel='Bit rate (bits/value)',ylabel='PSNR (dB)')
   window=RD_WINDOWS.get(rows[0]['dataset']) if zoom and rows else None
   if shown:
    xmax=max(r['bits_per_value'] for r in shown)
    psnr=[r['psnr_db'] for r in shown]
    pad=max(1,.02*(max(psnr)-min(psnr)))
    reference_x,reference_y=window[:2] if window else ((0,0),(math.inf,-math.inf))
    # Match the notebook's framing, expanding only for points outside it.
    ax.set(xlim=(0,max(reference_x[1],1.025*xmax)),
           ylim=(min(reference_y[0],min(psnr)-pad),max(reference_y[1],max(psnr)+pad)))
   if window and len({r['alpha'] for r in shown})>=4:
    xzoom,yzoom=window[2]
    ins=ax.inset_axes([.55,.11,.42,.35] if compact else [.56,.11,.39,.31])
    rd_lines(ins,shown,ms=2.4 if compact else 3,lw=.9 if compact else 1.1)
    ins.set(xlim=xzoom,ylim=yzoom)
    if compact:
     ins.set_xticks(xzoom,[f'{value:g}' for value in xzoom])
     ins.set_yticks(yzoom)
     ins.spines[['top','right']].set_visible(True)
     ins.tick_params(axis='both',labelsize=6.5,pad=1,length=2.5)
    else:
     ins.tick_params(axis='both',labelsize=7,pad=1)
    ins.grid(alpha=.25,linewidth=.6)
    ax.indicate_inset_zoom(ins,edgecolor='#606060',alpha=.55,linewidth=.8)
  else:
   points={(r['codec'],r['alpha']):r for r in rows}
   width=.84/len(codecs)
   phase=metric.split('_')[0]
   displayed=alphas if metric=='ratio' else throughput_alphas
   for i,codec in enumerate(codecs):
    xx=[j+(i-(len(codecs)-1)/2)*width for j in range(len(displayed))]
    rr=[points[codec,a] for a in displayed]
    bars=ax.bar(xx,[r[metric] for r in rr],width*.94,color=COLORS[codec],edgecolor='#222222',
                linewidth=.55,label=LABELS.get(codec,codec),zorder=3)
    if metric!='ratio':
     for bar,r in zip(bars,rr):
      if high_cv(r,phase):bar.set(hatch='///',linewidth=.9)
   ax.set_xticks(range(len(displayed)),[bound_label(a) for a in displayed],fontsize=9)
   ax.set_xlabel('Value-range relative error bound')
   if metric=='ratio':ax.set_yscale('log');ax.set_ylabel('Compression ratio')
   else:ax.set_ylabel('Throughput (MiB/s)')
   if metric=='ratio':ax.yaxis.set_minor_locator(NullLocator())
  ax.set_title(title);ax.set_axisbelow(True);ax.grid(axis='both' if metric=='rd' else 'y',alpha=.23)
 def legend(fig,ax,title=None,compact=False):
  handles,labels=ax.get_legend_handles_labels()
  if compact:
   fig.legend(handles,labels,loc='upper center',bbox_to_anchor=(.5,.99),ncol=len(handles),
              frameon=False,fontsize=9,columnspacing=1.35)
   return
  fig.legend(handles,labels,loc='lower center',bbox_to_anchor=(.5,1.005),ncol=len(handles),
             frameon=True,title=title,columnspacing=1.5)
 def notes(fig,rows,metrics=(),*,aggregate=True):
  msg=[]
  if metrics:
   if cfg['repetitions']>1 and any(high_cv(r,phase) for r in rows if r['alpha'] in throughput_alphas for phase in metrics):
    msg.append('Hatched bars: at least one field has timing CV >30%; all repeats retained.')
  if aggregate and a.hurricane_log_preferred and any(r['dataset']=='Hurricane' for r in rows):
   msg.append('Hurricane: one representation per field, preferring supplied log10 data.')
  if msg:fig.text(.5,-.035,'  '.join(msg),ha='center',fontsize=9)
 by_dataset={d:[r for r in agg if r['dataset']==d] for d in datasets}
 def title(dataset):
  label=DATASET_LABELS.get(dataset,dataset);rows=by_dataset[dataset]
  suffix='; log10 preferred' if dataset=='Hurricane' and a.hurricane_log_preferred else ''
  return f"{label} ({rows[0]['dtype']}{suffix})"
 for metric,name in [('rd','rd'),('ratio','ratio'),('compress_MiB_s','compression'),('decompress_MiB_s','decompression')]:
  if metric in metrics[1:] and not throughput_alphas:continue
  if metric=='rd':
   fig,axes=panel_row(len(datasets))
   for ax,dataset in zip(axes,datasets):
    panel(ax,by_dataset[dataset],metric,dataset,zoom=True,compact=True)
    compact_axis(ax,dataset)
   label_row(fig,'Bit rate (bits/value)','PSNR (dB)')
   legend(fig,axes[0],compact=True);notes(fig,agg);save(fig,'datasets_'+name)
   continue
  cols=min(3,len(datasets));nr=math.ceil(len(datasets)/cols)
  fig,axs=plt.subplots(nr,cols,figsize=(5.2*cols,3.8*nr),squeeze=False,constrained_layout=True)
  for ax,dataset in zip(axs.flat,datasets):panel(ax,by_dataset[dataset],metric,title(dataset),zoom=True)
  for ax in list(axs.flat)[len(datasets):]:ax.set_visible(False)
  legend(fig,axs.flat[0])
  notes(fig,agg,(metric.split('_')[0],) if metric in metrics[1:] else ())
  save(fig,'datasets_'+name)
 if throughput_alphas:
  fig,axs=plt.subplots(2,len(datasets),figsize=(4.25*len(datasets),6.6),squeeze=False,constrained_layout=True)
  for i,dataset in enumerate(datasets):
   for j,phase in enumerate(('compress','decompress')):
    ax=axs[j,i];panel(ax,by_dataset[dataset],phase+'_MiB_s',title(dataset) if j==0 else '')
    ax.set_ylabel(('Compression' if j==0 else 'Decompression')+' (MiB/s)' if i==0 else '')
  legend(fig,axs[0,0]);notes(fig,agg,('compress','decompress'));save(fig,'datasets_throughput')
 for dataset,rr in by_dataset.items():
  for metric,name in [('rd','rd'),('ratio','ratio')]:
   fig,ax=plt.subplots(figsize=(7.4,4.7),constrained_layout=True)
   panel(ax,rr,metric,title(dataset),zoom=True);legend(fig,ax);notes(fig,rr);save(fig,dataset+'_'+name)
  if throughput_alphas:
   fig,axs=plt.subplots(1,2,figsize=(12,4.4),constrained_layout=True)
   panel(axs[0],rr,'compress_MiB_s',title(dataset)+' · compression')
   panel(axs[1],rr,'decompress_MiB_s',title(dataset)+' · decompression')
   legend(fig,axs[0]);notes(fig,rr,('compress','decompress'));save(fig,dataset+'_throughput')
 if PARETO_ALPHA in alphas:
  def pareto_rows(dataset,rows):
   rr=[r for r in rows if r['alpha']==PARETO_ALPHA]
   comp=nondominated(rr,'compress_MiB_s');dec=nondominated(rr,'decompress_MiB_s')
   return [{'dataset':dataset,**{k:r[k] for k in ('codec','alpha','fields','ratio','compress_MiB_s','decompress_MiB_s',
    'compress_high_variability_fields','decompress_high_variability_fields')},
    'compress_pareto':r['codec'] in comp,'decompress_pareto':r['codec'] in dec} for r in rr]
  all_pareto=pareto_rows('All datasets',overall)
  dataset_pareto={d:pareto_rows(d,rr) for d,rr in by_dataset.items()}
  write_csv(out/'pareto_1e-3.csv',all_pareto+[r for rr in dataset_pareto.values() for r in rr])
  def pareto_panel(ax,rr,phase,heading,compact=False):
   key=phase+'_MiB_s';flag=phase+'_pareto'
   frontier=sorted({(r[key],r['ratio']) for r in rr if r[flag]})
   if len(frontier)>1:
    ax.plot(*zip(*frontier),color='#262626',ls='--',lw=1.1,zorder=2)
   for r in rr:
    codec=r['codec']
    if r[flag]:ax.scatter(r[key],r['ratio'],s=90 if compact else 177,facecolor='none',edgecolor='#222222',linewidth=1.1,zorder=3)
    ax.scatter(r[key],r['ratio'],s=33 if compact else 68,color=COLORS[codec],marker=MARKERS[codec],edgecolor='white',linewidth=.6,zorder=4)
   label='Compression' if phase=='compress' else 'Decompression'
   ax.set(title=heading,xlabel=label+' throughput (MiB/s)',ylabel='Compression ratio')
   ax.margins(x=.12,y=.15);ax.grid(alpha=.24)
  def pareto_caption(fig,compact=False):
   handles=[Line2D([],[],color=COLORS[c],marker=MARKERS[c],linestyle='none',label=LABELS.get(c,c)) for c in codecs]
   handles.append(Line2D([],[],color='#222222',marker='o',linestyle='--',markerfacecolor='none',label='Pareto frontier'))
   fig.legend(handles=handles,loc='upper center' if compact else 'lower center',
              bbox_to_anchor=(.5,.99 if compact else 1.005),ncol=len(handles),frameon=not compact,
              fontsize=9 if compact else None,title='Range-relative error bound: '+bound_label(PARETO_ALPHA))
   if compact and not exclude:return
   desc='Higher throughput and higher compression ratio are better.'
   if exclude:desc+=' Hurricane uses log10-preferred fields.'
   fig.text(.5,-.035,desc,ha='center',fontsize=9)
  fig,axs=plt.subplots(1,2,figsize=(10.5,4.3),constrained_layout=True,sharey=True)
  for ax,phase in zip(axs,('compress','decompress')):pareto_panel(ax,all_pareto,phase,'All datasets')
  axs[1].set_ylabel('')
  pareto_caption(fig);save(fig,'overall_pareto_1e-3')
  for phase in ('compress','decompress'):
   fig,axes=panel_row(len(datasets))
   for ax,d in zip(axes,datasets):
    pareto_panel(ax,dataset_pareto[d],phase,d,compact=True)
    compact_axis(ax,d)
   label_row(fig,('Compression' if phase=='compress' else 'Decompression')+' throughput (MiB/s)','Compression ratio')
   pareto_caption(fig,compact=True);save(fig,'datasets_pareto_'+phase+'_1e-3')
 if a.per_field:
  for dataset in datasets:
   fields=[f['field'] for f in cfg['fields'] if f['dataset']==dataset]
   for start in range(0,len(fields),6):
    for metric,name in [('rd','rd'),('ratio','ratio'),('compress_MiB_s','compression'),('decompress_MiB_s','decompression')]:
     if metric in metrics[1:] and not throughput_alphas:continue
     fig,axs=plt.subplots(2,3,figsize=(15,8),constrained_layout=True);page=fields[start:start+6]
     for ax,field in zip(axs.flat,page):panel(ax,[r for r in summary if r['dataset']==dataset and r['field']==field],metric,field)
     for ax in list(axs.flat)[len(page):]:ax.set_visible(False)
     legend(fig,axs.flat[0])
     notes(fig,[r for r in summary if r['dataset']==dataset and r['field'] in page],(metric.split('_')[0],) if metric in metrics[1:] else (),aggregate=False)
     save(fig,dataset+'_fields_'+str(start//6+1)+'_'+name)
 print('Complete:',len(summary),'field/config summaries;',len(agg),'dataset/config summaries;',len(list(figdir.glob('*.png'))),'figure pairs')
if __name__=='__main__':main()
