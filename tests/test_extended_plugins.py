import json
import subprocess
import sys

import numpy as np
import pytest

from lfcbench import (AbsoluteError, RankingMetric, benchmark, plugin_metadata, rank_entries,
                      register_compressor, register_metric, register_ranking_metric,
                      unregister_compressor, unregister_metric, unregister_ranking_metric)
from lfcbench.compressors import IdentityCompressor
from lfcbench.leaderboard import _MANUAL as RANKING_MANUAL
from lfcbench.metric_registry import _manual as METRICS, _manual_metadata as METRIC_META
from lfcbench.registry import Registry, _manual as COMPRESSORS, _manual_metadata as COMPRESSOR_META


def remove(name, data, metadata):
    data.pop(name,None);metadata.pop(name,None)


def test_compressor_tracks_and_installed_entrypoint(monkeypatch):
    register_compressor('test.multi',IdentityCompressor,tracks=('domain_specific','particle'),
                        data_models=('particles',),domains=('cosmology',))
    try:
        info=Registry().describe('test.multi')
        assert info['tracks']==('domain_specific','particle') and info['domains']==('cosmology',)
        with pytest.raises(ValueError):register_compressor('test.bad',IdentityCompressor,tracks=('invented',))
        assert 'test.bad' not in COMPRESSORS
    finally:remove('test.multi',COMPRESSORS,COMPRESSOR_META)
    @plugin_metadata(tracks=('particle',),data_models=('particles',),domains=('cosmology',))
    class Entry(IdentityCompressor):pass
    class EP:
        name='test.installed';value='example:Entry'
        def load(self):return Entry
    monkeypatch.setattr('lfcbench.registry.entry_points',lambda **kwargs:[EP()])
    assert Registry().describe('test.installed')['data_models']==('particles',)


def test_domain_metric_context_and_existing_array_api():
    @register_metric('test.domain',tracks=('domain_specific',),domains=('cosmology',),needs_context=True)
    def metric(a,b,*,context):
        assert not a.flags.writeable and not b.flags.writeable
        context['nested']['x']=9
        return {'difference':float(np.max(abs(a-b)))}
    try:
        a=np.arange(16,dtype=np.float32).reshape(4,4)
        with pytest.raises(ValueError,match='domain'):
            benchmark(a,compressor='identity',error=AbsoluteError(.1),quality_metrics=[{'name':'test.domain'}])
        context={'domain':'cosmology','nested':{'x':1}}
        result=benchmark(a,compressor='identity',error=AbsoluteError(.1),metric_context=context,
                         quality_metrics=[{'name':'test.domain'}])
        assert result['metrics']['quality']['test.domain']['difference']==0
        assert context['nested']['x']==1
    finally:remove('test.domain',METRICS,METRIC_META)


def test_ranking_same_cohort_ties_missing_and_custom_metric():
    metric=RankingMetric('custom.error','Custom error','lower','%');register_ranking_metric(metric)
    try:
        rows=[{'cohort':'x','codec':'a','status':'verified','metrics':{'custom.error':2}},
              {'cohort':'x','codec':'b','status':'verified','metrics':{'custom.error':1}},
              {'cohort':'x','codec':'c','status':'verified','metrics':{'custom.error':1}},
              {'cohort':'x','codec':'d','status':'pending','metrics':{'custom.error':0}}]
        ranked=rank_entries(rows,metric='custom.error',cohort='x')['entries']
        assert [(x['codec'],x['rank']) for x in ranked]==[('b',1),('c',1),('a',3),('d',None)]
        with pytest.raises(ValueError,match='cohorts'):
            rank_entries(rows+[{'cohort':'different','codec':'e'}],metric='custom.error',cohort='x')
    finally:RANKING_MANUAL.pop('custom.error')


def test_cli_filters_by_track_and_emits_metadata(tmp_path):
    (tmp_path/'custom.py').write_text(
        'from lfcbench import register_compressor\n'
        'from lfcbench.compressors import IdentityCompressor\n'
        "register_compressor('example.domain', IdentityCompressor, tracks=('domain_specific',), domains=('cosmology',))\n")
    proc=subprocess.run([sys.executable,'-m','lfcbench','--plugin','custom','list','--track','domain_specific','--json'],
                        cwd=tmp_path,text=True,capture_output=True,check=True)
    result=json.loads(proc.stdout)
    assert len(result)==1 and result[0]['name']=='example.domain' and result[0]['domains']==['cosmology']


def test_unregister_and_data_model_guard():
    register_compressor('test.future_particle',IdentityCompressor,tracks=('particle',),data_models=('particles',))
    try:
        with pytest.raises(ValueError,match='not registered for grid'):
            benchmark(np.ones((3,3),dtype=np.float32),compressor='test.future_particle',error=AbsoluteError(.1))
    finally:unregister_compressor('test.future_particle')
    with pytest.raises(ValueError,match='no local'):
        unregister_compressor('identity')
    register_metric('test.remove',lambda a,b:{})
    unregister_metric('test.remove')
    with pytest.raises(ValueError,match='no local'):unregister_metric('test.remove')
    register_ranking_metric(RankingMetric('test.remove','Temporary','lower'))
    unregister_ranking_metric('test.remove')


def test_yaml_domain_metadata_reaches_metric(tmp_path):
    from lfcbench.runner import run_config
    @register_metric('test.context_yaml',tracks=('domain_specific',),domains=('cosmology',),needs_context=True)
    def score(a,b,*,context):
        return {'box_size':context['metadata']['box_size'],'name':context['dataset']}
    try:
        np.save(tmp_path/'array.npy',np.arange(25,dtype=np.float32).reshape(5,5))
        config=tmp_path/'run.yaml'
        config.write_text('''
datasets:
  - name: density
    path: array.npy
    domain: cosmology
    metadata: {box_size: 100}
compressors: [{name: identity}]
error_bounds: [{mode: abs, value: 0.01}]
quality_metrics: [{name: test.context_yaml}]
warmups: 0
repetitions: 1
''')
        output=tmp_path/'result.jsonl';assert run_config(config,output,Registry())['ok']==1
        row=json.loads(output.read_text())
        assert row['metrics']['quality']['test.context_yaml']=={'box_size':100,'name':'density'}
        assert row['compressor_registration']['tracks']==['general']
    finally:unregister_metric('test.context_yaml')


def test_example_domain_metric_and_ranking_registration():
    proc=subprocess.run([sys.executable,'-m','lfcbench','--plugin','examples.domain_metric','list-ranking-metrics'],
                        text=True,capture_output=True,check=True)
    assert 'example.climate_bias' in proc.stdout and '"direction": "lower"' in proc.stdout
    proc=subprocess.run([sys.executable,'-m','lfcbench','--plugin','examples.domain_metric','list-metrics'],
                        text=True,capture_output=True,check=True)
    assert 'example.climate_bias' in proc.stdout and 'climate' in proc.stdout
