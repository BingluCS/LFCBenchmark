#!/usr/bin/env python3
"""Build auditable leaderboard cohorts from existing SDRBench/LFCQuality records."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DATASETS=['NYX','Hurricane','Miranda','SCALE','CESM','JHTDB']
METRICS={
    'ratio':{'label':'Compression ratio','direction':'higher','unit':'×'},
    'bits_per_value':{'label':'Bits per value','direction':'lower','unit':'bits/value'},
    'compress_MiB_s':{'label':'Compression throughput','direction':'higher','unit':'MiB/s'},
    'decompress_MiB_s':{'label':'Decompression throughput','direction':'higher','unit':'MiB/s'},
    'psnr_db':{'label':'PSNR','direction':'higher','unit':'dB'},
    'ssim':{'label':'Median SSIM','direction':'higher','unit':''},
    'pcc':{'label':'Median PCC','direction':'higher','unit':''},
    'spectral_l1':{'label':'Median spectral power L1 error','direction':'lower','unit':''},
    'field_acf_delta':{'label':'Median field autocorrelation difference','direction':'lower','unit':''},
}


def read_json(path):return json.loads(path.read_text())
def digest(obj):return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def value(row,key):return float(row[key]) if row.get(key) else None
def median(rows,key):
    values=[value(r,key) for r in rows];values=[v for v in values if v is not None and math.isfinite(v)]
    return statistics.median(values) if len(values)==len(rows) else None


def export(quality, output):
    qconfig=read_json(quality/'config.json');qaudit=read_json(quality/'audit.json')
    paudit=read_json(ROOT/'docs/data/sdrbench/audit.json');manifest=read_json(ROOT/'docs/data/results.json')
    if not qaudit['complete'] or qaudit['error_count'] or not qaudit['expected_points'] or qaudit['actual_points']!=qaudit['expected_points']:
        raise ValueError('quality study must have a complete verified audit')
    if paudit['strict_bound_violations'] or paudit['max_threads']!=1 or not paudit['input_hashes_rechecked']:
        raise ValueError('performance study audit is not eligible')
    if qconfig['compression_threads']!=1 or qconfig['error_mode'].split(';')[0] != 'alpha * (max(original)-min(original))':
        raise ValueError('quality experiment protocol differs')
    with (ROOT/'docs/data/sdrbench/summary_by_field.csv').open(newline='') as stream:p_rows=list(csv.DictReader(stream))
    points=quality/'analysis/points.csv'
    if not points.is_file():points=quality/'points.csv'
    with points.open(newline='') as stream:q_rows=list(csv.DictReader(stream))
    def key(r):return r['dataset'],r['field'],r['codec'],float(r['alpha'])
    perf={key(r):r for r in p_rows};q={key(r):r for r in q_rows}
    if len(perf)!=len(p_rows) or len(q)!=len(q_rows) or set(perf)!=set(q) or len(q)!=qaudit['expected_points']:
        raise ValueError('per-field performance and quality coverage differ')
    source_fields={(f['dataset'],f['field']):f for f in qconfig['fields']}
    if len(source_fields)!=len(qconfig['fields']):raise ValueError('duplicate configured field')
    codecs=qconfig['codecs']
    if not codecs or len(set(codecs))!=len(codecs):raise ValueError('empty or duplicate codec list')
    datasets=[d for d in DATASETS if any(ds==d for ds,_ in source_fields)]
    datasets+=sorted({ds for ds,_ in source_fields}-set(datasets))
    bounds=qconfig['alphas']
    if not bounds or len(set(bounds))!=len(bounds):raise ValueError('empty or duplicate error bounds')
    if any((ds,field) not in source_fields or codec not in codecs or alpha not in bounds
           for ds,field,codec,alpha in q):
        raise ValueError('records contain an unconfigured field, codec or bound')
    excluded=set();hashes={};grouped=defaultdict(list)
    for k,quality_row in q.items():
        dataset,field,codec,alpha=k;performance=perf[k]
        if quality_row['verification']!='ok':raise ValueError('unverified quality point '+repr(k))
        if quality_row['suspected_fill_value']=='True' or quality_row['duplicate_of']:
            excluded.add((dataset,field));continue
        if not math.isclose(float(quality_row['ratio']),float(performance['ratio']),rel_tol=1e-10):
            raise ValueError('compressed-size mismatch '+repr(k))
        if not math.isclose(float(quality_row['nrmse']),float(performance['nrmse']),rel_tol=1e-10,abs_tol=1e-300):
            raise ValueError('normalized error mismatch '+repr(k))
        input_hash=quality_row['input_sha256'];prior=hashes.setdefault((dataset,field),input_hash)
        if prior!=input_hash:raise ValueError('input hash changes across cases '+repr(k))
        grouped[(dataset,alpha,codec)].append((performance,quality_row))
    expected_fields={d:sorted((name for ds,name in source_fields if ds==d and (ds,name) not in excluded)) for d in datasets}
    groups=[];backends=manifest['backends']
    if set(codecs)-set(backends):raise ValueError('missing pinned backend metadata')
    for dataset in datasets:
        for alpha in bounds:
            fields=expected_fields[dataset]
            if not fields or not any((dataset,alpha,codec) in grouped for codec in codecs):continue
            identity={'dataset':dataset,'data_model':'grid','track':'general','cpu':paudit['cpu'],
              'host':'HPDPS-8','threads':1,'error_mode':'range_relative','alpha':alpha,
              'fields_sha256':digest([{'field':f,'sha256':hashes[(dataset,f)]} for f in fields]),
              'field_policy':'exclude suspected CESM fill values and exact CESM duplicate',
              'quality_options':qconfig['metric_options']}
            cohort='sha256:'+digest(identity);entries=[]
            for codec in codecs:
                rr=grouped.get((dataset,alpha,codec),[])
                if not rr:continue
                if sorted(p['field'] for p,_ in rr)!=fields:raise ValueError('incomplete matched cohort '+repr((dataset,alpha,codec)))
                performance=[p for p,_ in rr];quality_rows=[r for _,r in rr]
                raw=sum(int(x['original_bytes']) for x in performance)
                comp=sum(float(x['mean_compressed_bytes']) for x in performance)
                elements=sum(int(x['elements']) for x in performance)
                nr=math.sqrt(sum(int(x['elements'])*float(x['nrmse'])**2 for x in performance)/elements)
                metrics={'ratio':raw/comp,'bits_per_value':8*comp/elements,
                    'compress_MiB_s':raw/1048576/sum(float(x['mean_compress_seconds']) for x in performance),
                    'decompress_MiB_s':raw/1048576/sum(float(x['mean_decompress_seconds']) for x in performance),
                    'psnr_db':-20*math.log10(nr) if nr else None,
                    'ssim':median(quality_rows,'ssim'),'pcc':median(quality_rows,'pcc'),
                    'spectral_l1':median(quality_rows,'power_relative_l1'),
                    'field_acf_delta':median(quality_rows,'field_acf_mean_abs_delta')}
                entries.append({'codec':codec,'display_name':'SZ3.3' if codec=='SZ3' else codec,
                    'cohort':cohort,'status':'verified','field_count':len(fields),'metrics':metrics,
                    'source':backends[codec]})
            groups.append({'id':cohort,'protocol':identity,'field_count':len(fields),'entries':entries})
    output.parent.mkdir(parents=True,exist_ok=True)
    result={'schema_version':1,'title':'SDRBench','tracks':[{'id':'general','label':'General'},
        {'id':'domain_specific','label':'Domain-specific'},{'id':'particle','label':'Particle'}],
        'metrics':METRICS,'datasets':datasets,'bounds':bounds,'groups':groups,
        'provenance':{'performance_audit':'./data/sdrbench/audit.json','quality_audit':'./data/quality/audit.json',
            'excluded_fields':[{'dataset':d,'field':f} for d,f in sorted(excluded)],
            'aggregation':'Ratio: total raw bytes / total compressed bytes. Throughput: total raw bytes / sum of mean field times. PSNR: element-weighted RMS NRMSE. SSIM/PCC/spectral/ACF: per-field median.',
            'quality_scope':'One reconstruction per combination; quality outside codec timers.',
            'warning':'Raw figures remain in the explorer; this leaderboard excludes 12 suspected CESM missing-value fields and one exact duplicate.'}}
    output.write_text(json.dumps(result,separators=(',',':'),allow_nan=False)+'\n')
    print('LEADERBOARD',len(groups),'cohorts',sum(len(g['entries']) for g in groups),'entries; excluded',len(excluded),'fields')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--quality',type=Path,default=ROOT/'docs/data/quality',help='quality config, audit and points (default: published inputs)')
    parser.add_argument('--output',type=Path,default=ROOT/'docs/data/leaderboard.json')
    args=parser.parse_args();export(args.quality.resolve(),args.output.resolve())
