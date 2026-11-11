#!/usr/bin/env python3
"""Inventory all local fields without guessing dtype or dimensions from byte size."""
import argparse,json,math
from pathlib import Path
import numpy as np
from run_sdrbench import SHAPES,dump
def main():
 p=argparse.ArgumentParser();p.add_argument('--data-root',type=Path,default=Path('/data0/lb/sdrbench'));p.add_argument('--output',type=Path,required=True)
 p.add_argument('--datasets',nargs='+',choices=[*SHAPES,'Miranda-float'],help='inventory only these datasets; default scans the full suite')
 a=p.parse_args()
 if a.output.exists():raise SystemExit('Inventory already exists; preserve it for resume or select another output')
 result={}
 names=a.datasets if a.datasets is not None else [*SHAPES,'Miranda-float']
 if len(set(names))!=len(names):p.error('duplicate dataset')
 for name in names:
  if name=='Miranda-float' and a.datasets is None and not (a.data_root/name).is_dir():continue
  dtype='float64' if name=='Miranda' else 'float32';shape=SHAPES['Miranda' if name=='Miranda-float' else name]
  rows=[];pattern='*.d64' if dtype=='float64' else '*.f32'
  for file in sorted((a.data_root/name).glob(pattern)):
   expected=math.prod(shape)*(8 if dtype=='float64' else 4)
   if file.stat().st_size!=expected:raise ValueError('Shape/dtype byte mismatch: '+str(file))
   data=np.memmap(file,dtype='<f8' if dtype=='float64' else '<f4',mode='r')
   row={'path':str(file.resolve()),'bytes':file.stat().st_size,'elements':len(data),'dtype':dtype,
        'min':float(data.min()),'max':float(data.max()),'nonfinite':int(np.count_nonzero(~np.isfinite(data)))}
   rows.append(row)
  if not rows:raise ValueError('No files found for '+name)
  result[name]=rows;print(name,'fields',len(rows),'bytes',sum(r['bytes'] for r in rows),flush=True)
 a.output.parent.mkdir(parents=True,exist_ok=True);dump(a.output,result)
if __name__=='__main__':main()
