#!/usr/bin/env python3
"""Build pinned upstream libraries and in-memory API benchmark drivers."""
import argparse, hashlib, json, os, platform, subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SOURCES={'PFPL':'https://github.com/burtscher/PFPL.git','SPERR':'https://github.com/NCAR/SPERR.git','SZ3':'https://github.com/szcompressor/SZ3.git','ZFP':'https://github.com/LLNL/zfp.git','Falcons':'https://github.com/opensdc-org/Falcons.git'}
DIRS={'ZFP':'zfp'}
def capture(cmd):return subprocess.check_output(cmd,cwd=ROOT,text=True).strip()
def main():
 p=argparse.ArgumentParser();p.add_argument('--jobs',type=int,default=4);a=p.parse_args()
 (ROOT/'build/bin').mkdir(parents=True,exist_ok=True)
 pins={}
 for name,url in SOURCES.items():
  path='third_party/'+DIRS.get(name,name)
  pins[name]={'url':url,'path':path,'commit':capture(['git','-C',path,'rev-parse','HEAD'])}
 lock=ROOT/'sources.lock.json'
 if lock.exists():
  if json.loads(lock.read_text())!=pins:raise SystemExit('Source pins differ from sources.lock.json; refusing to build')
 else:lock.write_text(json.dumps(pins,indent=2)+'\n')
 commands=[]
 with (ROOT/'build/build.log').open('w') as log:
  def run(cmd):
   cmd=list(map(str,cmd));commands.append(cmd);print('BUILD', ' '.join(cmd),flush=True)
   log.write('\nCOMMAND '+json.dumps(cmd)+'\n');log.flush()
   rc=subprocess.run(cmd,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT).returncode
   if rc:raise SystemExit(f'command failed ({rc}), see build/build.log')
  flags='-O3 -march=native -ffp-contract=off'
  def cmake(name,options=(),targets=()):
   source='third_party/'+DIRS.get(name,name);build='build/'+name
   run(['cmake','-S',source,'-B',build,'-DCMAKE_BUILD_TYPE=Release','-DBUILD_SHARED_LIBS=OFF','-DCMAKE_CXX_FLAGS='+flags,'-DCMAKE_C_FLAGS='+flags,*options])
   run(['cmake','--build',build,'--parallel',a.jobs,*(['--target',*targets] if targets else [])])
  cmake('SPERR',['-DUSE_OMP=OFF','-DBUILD_UNIT_TESTS=OFF','-DBUILD_CLI_UTILITIES=OFF','-DENABLE_AVX2=ON'])
  cmake('ZFP',['-DZFP_WITH_OPENMP=OFF','-DBUILD_TESTING=OFF','-DBUILD_UTILITIES=OFF','-DBUILD_ZFPY=OFF'])
  cmake('SZ3',['-DBUILD_TESTING=OFF','-DBUILD_SZ3_BINARY=OFF'])
  cmake('Falcons',['-DBUILD_TESTING=OFF','-DBUILD_Falcons_BINARY=OFF','-DENABLE_AVX2=ON'],['Falcons_fse'])
  common=['g++','-std=c++20','-O3','-march=native','-ffp-contract=off','-Inative']
  run([*common,'-c','native/driver.cpp','-o','build/driver.o'])
  specs={
   'PFPL':['native/pfpl.cpp','native/pfpl_encode.cpp','native/pfpl_decode.cpp','-mno-fma','-Wno-unknown-pragmas'],
   'SPERR':['native/sperr.cpp','-Ithird_party/SPERR/include','-Ibuild/SPERR','build/SPERR/src/libSPERR.a'],
   'ZFP':['native/zfp.cpp','-Ithird_party/zfp/include','-Ibuild/ZFP/include','build/ZFP/lib/libzfp.a'],
   'SZ3':['native/sz3.cpp','-Ithird_party/SZ3/include','-Ibuild/SZ3/include','-DSZ3_DEBUG_TIMINGS=0','-DSZ3_USE_SKA_HASH=1','-fopenmp','-lzstd'],
   'Falcons':['native/falcons.cpp','-Ithird_party/Falcons/include','-Ibuild/Falcons/include','-DFalcons_DEBUG_TIMINGS=0','-DFalcons_USE_SKA_HASH=1','-fopenmp','build/Falcons/libFalcons_fse.a','-lzstd'],
  }
  for name,extra in specs.items():run([*common,'build/driver.o',*extra,'-o','build/bin/bench_'+name.lower()])
 manifest={'sources':pins,'compiler':capture(['g++','--version']),'cmake':capture(['cmake','--version']),'commands':commands,'platform':platform.platform(),'native_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT/'native').glob('*')) if p.is_file()}}
 (ROOT/'build/manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
 print('Build complete; manifest: build/manifest.json',flush=True)
if __name__=='__main__':main()
