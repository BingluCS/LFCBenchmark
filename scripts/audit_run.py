#!/usr/bin/env python3
"""Check repetition coverage, strict error bounds, affinity, and provenance."""
import argparse, hashlib, json, math, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def audit(run, check_inputs=False):
    run = Path(run).resolve()
    cfg = json.loads((run/'config.json').read_text())
    manifest_path = ROOT/'build/manifest.json'
    manifest = json.loads(manifest_path.read_text())
    digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    if digest != cfg['build_manifest_sha256']:
        raise ValueError('Current build manifest differs from this run')
    for name, expected in manifest['native_sha256'].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest() != expected:
            raise ValueError('Native source changed since build: '+name)
    count = warmups = jobs = 0
    deterministic = True
    for filename in cfg['files']:
        source = Path(filename)
        input_digest = None
        if check_inputs:
            h = hashlib.sha256()
            with source.open('rb') as f:
                while data := f.read(8*1024*1024):
                    h.update(data)
            input_digest = h.hexdigest()
        for codec in cfg['codecs']:
            stem = source.stem+'__'+codec
            done = json.loads((run/(stem+'.done.json')).read_text())
            if done['status'] != 'ok' or done['returncode'] or done['max_observed_threads'] > 1:
                raise ValueError('Failed/nonserial job: '+stem)
            if input_digest and input_digest != done['input_sha256']:
                raise ValueError('Input content changed: '+str(source))
            rows = [json.loads(line) for line in (run/(stem+'.jsonl')).read_text().splitlines()]
            for alpha in cfg['alphas']:
                rr = [r for r in rows if r['alpha'] == alpha]
                measured = [r for r in rr if not r['warmup']]
                warm = [r for r in rr if r['warmup']]
                if len(measured) != cfg['repetitions'] or {r['repeat'] for r in measured} != set(range(1,cfg['repetitions']+1)):
                    raise ValueError('Measured repetition coverage: '+stem)
                if len(warm) != cfg['warmups'] or {r['repeat'] for r in warm} != set(range(1-cfg['warmups'],1)):
                    raise ValueError('Warmup coverage: '+stem)
                deterministic &= len({(r['compressed_bytes'],r['rmse'],r['max_abs_error']) for r in rr}) == 1
            expected = len(cfg['alphas'])*(cfg['warmups']+cfg['repetitions'])
            if len(rows) != expected:
                raise ValueError('Unexpected extra/missing records: '+stem)
            for r in rows:
                valid = (r['codec'] == codec and r['field'] == source.stem
                    and r['shape'] == cfg['shape'] and r['cpu'] == cfg['cpu']
                    and r['build_manifest_sha256'] == digest
                    and r['input_sha256'] == done['input_sha256']
                    and r['status'] == 'ok' and r['violations'] == 0 and r['nonfinite'] == 0
                    and r['max_abs_error'] <= r['absolute_bound']
                    and r['effective_bound'] <= r['absolute_bound']
                    and r['original_bytes'] == 4*math.prod(cfg['shape'])
                    and r['elements'] == math.prod(cfg['shape'])
                    and r['compressed_bytes'] > 0)
                valid &= all(math.isfinite(r[k]) and r[k] > 0 for k in ('compress_seconds','decompress_seconds','absolute_bound','effective_bound'))
                if not valid:
                    raise ValueError('Invalid record: '+stem+' '+str(r))
            count += sum(not r['warmup'] for r in rows)
            warmups += sum(r['warmup'] for r in rows)
            jobs += 1
    try:
        commit = subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    except subprocess.CalledProcessError:
        commit = None
    result = {'status':'ok','jobs':jobs,'measured_records':count,'warmup_records':warmups,
        'strict_bound_violations':0,'cpu':cfg['cpu'],'max_observed_threads':1,
        'inputs_rehashed':check_inputs,'repeat_size_and_error_metrics_identical':bool(deterministic),
        'project_commit_at_audit':commit,'build_manifest_sha256':digest}
    (run/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('run',type=Path);p.add_argument('--check-inputs',action='store_true')
    a=p.parse_args();print(json.dumps(audit(a.run,a.check_inputs),indent=2))
