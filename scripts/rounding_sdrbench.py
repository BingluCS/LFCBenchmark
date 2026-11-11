"""Targeted, provenance-preserving retries for SZ3 float32 rounding edges."""
import datetime,json,math,shutil,struct,subprocess
from pathlib import Path

POLICY='SZ3 float32: one binary32 step below the downward-rounded nominal tolerance'

def f32(x):return struct.unpack('<f',struct.pack('<f',x))[0]

def normalize_bound(row,nominal_alpha):
    """Use the driver's independent max-error scan to verify the nominal bound."""
    if row['alpha']==nominal_alpha:return row
    if row['codec']!='SZ3' or row['dtype']!='float32' or not 0<row['alpha']<nominal_alpha:
        raise ValueError('Unexpected adjusted native tolerance')
    nominal=nominal_alpha*(row['max']-row['min'])
    if not 0<row['effective_bound']<nominal:raise ValueError('Retry tolerance did not tighten the nominal bound')
    row.update(native_alpha=row['alpha'],native_validation_bound=row['absolute_bound'],
               native_violations=row['violations'],native_status=row['status'],
               alpha=nominal_alpha,absolute_bound=nominal,tolerance_policy=POLICY)
    if row['status'] in ('ok','violation') and row['nonfinite']==0 and math.isfinite(row['max_abs_error']) and row['max_abs_error']<=nominal:
        row.update(violations=0,status='ok')
    else:row['status']='violation'
    return row

def repair_roundoff_job(root,folder,stem,field,codec,digest,cfg,env):
    """Repair only completed, finite, binary32-sized violations; keep failed attempts."""
    if codec!='SZ3' or field['dtype']!='float32':return False
    raw=folder/(stem+'.jsonl');done=folder/(stem+'.done.json');driver_log=folder/(stem+'.log')
    old=json.loads(done.read_text())
    if old['returncode'] or old['input_sha256']!=digest or old['max_observed_threads']>1:return False
    rows=[json.loads(line) for line in raw.read_text().splitlines()]
    expected={(alpha,warm,i) for alpha in cfg['alphas'] for warm,rr in (
        (True,range(1-cfg['warmups'],1)),(False,range(1,cfg['repetitions']+1))) for i in rr}
    if len(rows)!=len(expected) or {(r['alpha'],r['warmup'],r['repeat']) for r in rows}!=expected:return False
    kind='legacy' if field['shape'][0]>1 else 'typed'
    if any(r['status'] not in ('ok','violation') or r['input_sha256']!=digest or r['cpu']!=cfg['cpu'] or r['build_manifest_sha256']!=cfg['builds'][kind] for r in rows):return False
    bad=[r for r in rows if r['status']!='ok']
    if not bad or any(r['nonfinite'] or r.get('native_alpha') or not r['absolute_bound']<r['max_abs_error'] or f32(r['max_abs_error'])>r['absolute_bound'] for r in bad):return False
    alphas=sorted({r['alpha'] for r in bad},reverse=True);aliases={};details=[]
    data_range=field['max']-field['min']
    for alpha in alphas:
        nominal=alpha*data_range;nearest=f32(nominal)
        bits=struct.unpack('<I',struct.pack('<f',nearest))[0]-int(nearest>nominal)-1
        if bits<=0:return False
        tighter=struct.unpack('<f',struct.pack('<I',bits))[0];native_alpha=tighter/data_range
        if not 0<native_alpha<alpha:return False
        aliases[native_alpha]=alpha
        details.append({'alpha':alpha,'nominal_bound':nominal,'native_alpha':native_alpha,
                        'effective_bound':native_alpha*data_range,
                        'original_max_abs_error':max(r['max_abs_error'] for r in bad if r['alpha']==alpha),
                        'original_formal_violating_points':[r['violations'] for r in bad if r['alpha']==alpha and not r['warmup']]})
    if len(aliases)!=len(alphas):raise ValueError('Retry tolerances alias one another')
    attempt=folder/'attempts'/stem/datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f-rounding');attempt.mkdir(parents=True)
    for file in (raw,done,driver_log):
        if file.is_file():shutil.copyfile(file,attempt/file.name)
    binary=root/('build/bin/bench_sz3' if kind=='legacy' else 'build/typed/bin/bench_sz3_f32')
    cmd=['taskset','-c',str(cfg['cpu']),str(binary),field['path'],*map(str,field['shape']),str(cfg['repetitions']),str(cfg['warmups']),*map(str,aliases)]
    print('ROUNDING_RETRY',field['dataset'],stem,details,flush=True)
    replacement={};threads=old['max_observed_threads'];new_log=attempt/'retry.log'
    with new_log.open('w') as log:
        log.write('COMMAND '+json.dumps(cmd)+'\n')
        with subprocess.Popen(cmd,cwd=root,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,bufsize=1) as proc:
            for line in proc.stdout:
                log.write(line);log.flush()
                try:threads=max(threads,len(list(Path(f'/proc/{proc.pid}/task').iterdir())))
                except FileNotFoundError:pass
                if line.startswith('LFCB_RESULT '):
                    r=json.loads(line[len('LFCB_RESULT '):]);r.update(dataset=field['dataset'],field=field['field'],dtype='float32',shape=field['shape'],input_sha256=digest,build_manifest_sha256=cfg['builds'][kind],build_kind=kind,reused=False)
                    r=normalize_bound(r,aliases[r['alpha']]);r['measurement_origin']=str(new_log)
                    if r['cpu']!=cfg['cpu'] or r['min']!=field['min'] or r['max']!=field['max'] or r['status']!='ok':
                        raise ValueError('Adjusted SZ3 retry failed validation; retained '+str(new_log))
                    key=(r['alpha'],r['warmup'],r['repeat'])
                    if key in replacement:raise ValueError('Duplicate retry record')
                    replacement[key]=r
            rc=proc.wait()
    if rc or threads>1 or set(replacement)!={key for key in expected if key[0] in alphas}:
        raise ValueError('Incomplete SZ3 retry; retained '+str(new_log))
    rows=[replacement.get((r['alpha'],r['warmup'],r['repeat']),r) for r in rows]
    tmp=raw.with_suffix('.jsonl.tmp');tmp.write_text(''.join(json.dumps(r,allow_nan=False)+'\n' for r in rows));tmp.replace(raw)
    old.update(status='ok',bad_records=0,max_observed_threads=threads,tolerance_retries=details,
               original_attempt=str(attempt),repair_command=cmd,repair_log=str(new_log),
               job_resources_scope='initial driver execution; targeted retry logged separately')
    tmp=done.with_suffix('.json.tmp');tmp.write_text(json.dumps(old,indent=2)+'\n');tmp.replace(done)
    return True
