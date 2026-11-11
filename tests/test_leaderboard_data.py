"""Check published ranking cohorts against audited source measurements."""
import csv
import hashlib
import json
import math
import statistics
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'docs/data'


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def test_leaderboard_matches_per_field_data_and_protocol():
    board=json.loads((DATA/'leaderboard.json').read_text())
    assert board['title']=='SDRBench'
    assert board['metrics']['compress_MiB_s']['unit']=='MiB/s'
    assert board['metrics']['decompress_MiB_s']['unit']=='MiB/s'
    audit=json.loads((DATA/'quality/audit.json').read_text())
    assert audit['complete'] and audit['actual_points']==audit['expected_points']
    with (DATA/'sdrbench/summary_by_field.csv').open(newline='') as f:perf=list(csv.DictReader(f))
    with (DATA/'quality/points.csv').open(newline='') as f:quality=list(csv.DictReader(f))
    key=lambda r:(r['dataset'],r['field'],r['codec'],float(r['alpha']))
    q={key(r):r for r in quality};assert len(q)==len(quality)==len(perf)==audit['actual_points']
    assert {g['protocol']['track'] for g in board['groups']}=={'general'}
    assert len(board['provenance']['excluded_fields'])==13
    for group in board['groups']:
        p=group['protocol'];assert group['id']=='sha256:'+digest(p)
        assert p['threads']==1 and p['error_mode']=='range_relative'
        assert group['entries']
        for entry in group['entries']:
            assert entry['cohort']==group['id'] and entry['status']=='verified'
            selected=[r for r in perf if r['dataset']==p['dataset'] and r['codec']==entry['codec'] and float(r['alpha'])==p['alpha']
                      and q[key(r)]['suspected_fill_value']!='True' and not q[key(r)]['duplicate_of']]
            assert len(selected)==entry['field_count']==group['field_count']
            fields=sorted([{'field':r['field'],'sha256':q[key(r)]['input_sha256']} for r in selected],key=lambda x:x['field'])
            assert p['fields_sha256']==digest(fields)
            raw=sum(int(r['original_bytes']) for r in selected)
            compressed=sum(float(r['mean_compressed_bytes']) for r in selected)
            elements=sum(int(r['elements']) for r in selected)
            m=entry['metrics']
            assert m['ratio']==pytest.approx(raw/compressed)
            assert m['bits_per_value']==pytest.approx(8*compressed/elements)
            for phase in ('compress','decompress'):
                assert m[phase+'_MiB_s']==pytest.approx(raw/(1024**2)/sum(float(r['mean_'+phase+'_seconds']) for r in selected))
            nrmse=math.sqrt(sum(int(r['elements'])*float(r['nrmse'])**2 for r in selected)/elements)
            assert m['psnr_db']==pytest.approx(-20*math.log10(nrmse))
            assert m['ssim']==pytest.approx(statistics.median(float(q[key(r)]['ssim']) for r in selected))
    assert all(g['field_count']==64 for g in board['groups'] if g['protocol']['dataset']=='CESM')
