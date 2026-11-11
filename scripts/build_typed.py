#!/usr/bin/env python3
"""Add native 2D/float64 drivers, preserving the existing float32 3D binaries."""
import argparse,hashlib,json,platform,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.parse_args()
 base=ROOT/'build/manifest.json';manifest=json.loads(base.read_text())
 for name,pin in manifest['sources'].items():
  path=ROOT/pin['path']
  commit=subprocess.check_output(['git','-C',str(path),'rev-parse','HEAD'],text=True).strip()
  dirty=subprocess.check_output(['git','-C',str(path),'diff','--name-only','HEAD'],text=True).strip()
  if commit!=pin['commit'] or dirty:raise SystemExit('Source revision/working tree mismatch: '+name)
 out=ROOT/'build/typed';(out/'bin').mkdir(parents=True,exist_ok=True);commands=[]
 common=['g++','-std=c++20','-O3','-march=native','-ffp-contract=off','-Inative_typed']
 specs={
  'PFPL':['native_typed/pfpl.cpp','native_typed/pfpl_encode.cpp','native_typed/pfpl_decode.cpp','-mno-fma','-Wno-unknown-pragmas'],
  'SPERR':['native_typed/sperr.cpp','-Ithird_party/SPERR/include','-Ibuild/SPERR','build/SPERR/src/libSPERR.a'],
  'ZFP':['native_typed/zfp.cpp','-Ithird_party/zfp/include','-Ibuild/ZFP/include','build/ZFP/lib/libzfp.a'],
  'SZ3':['native_typed/sz3.cpp','-Ithird_party/SZ3/include','-Ibuild/SZ3/include','-DSZ3_DEBUG_TIMINGS=0','-DSZ3_USE_SKA_HASH=1','-fopenmp','-lzstd'],
  'Falcons':['native_typed/falcons.cpp','-Ithird_party/Falcons/include','-Ibuild/Falcons/include','-DFalcons_DEBUG_TIMINGS=0','-DFalcons_USE_SKA_HASH=1','-fopenmp','build/Falcons/libFalcons_fse.a','-lzstd'],
 }
 with (out/'build.log').open('w') as log:
  def run(cmd):
   commands.append(cmd);print('BUILD',' '.join(cmd),flush=True);log.write(json.dumps(cmd)+'\n');log.flush()
   if subprocess.run(cmd,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT).returncode:raise SystemExit('Build failed: see build/typed/build.log')
  for dtype in ['f32','f64']:
   flags=common+(['-DLFCB_DOUBLE=1'] if dtype=='f64' else [])
   obj='build/typed/driver_'+dtype+'.o'
   run(flags+['-c','native_typed/driver.cpp','-o',obj])
   for name,extra in specs.items():run(flags+[obj]+extra+['-o','build/typed/bin/bench_'+name.lower()+'_'+dtype])
 result={'base_build_manifest_sha256':sha(base),'sources':manifest['sources'],'commands':commands,
  'compiler':subprocess.check_output(['g++','--version'],text=True),'platform':platform.platform(),
  'native_sha256':{str(f.relative_to(ROOT)):sha(f) for f in sorted((ROOT/'native_typed').glob('*')) if f.is_file()},
  'binaries':{str(f.relative_to(ROOT)):sha(f) for f in sorted((out/'bin').glob('*'))}}
 (out/'manifest.json').write_text(json.dumps(result,indent=2)+'\n')
 print('Typed driver build complete',flush=True)
if __name__=='__main__':main()
