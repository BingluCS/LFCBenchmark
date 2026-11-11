"""Server integration check for wheel installation and third-party entry points."""
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]

def run(cmd,*,cwd=None,env=None):
    result=subprocess.run(list(map(str,cmd)),cwd=cwd,env=env,text=True,capture_output=True)
    if result.returncode:raise RuntimeError(f"command failed: {cmd}\n{result.stdout}\n{result.stderr}")
    return result.stdout

def main():
    with tempfile.TemporaryDirectory(prefix='lfcb-entrypoints-') as tmp:
        temp=Path(tmp);dist=temp/'dist';dist.mkdir()
        run([sys.executable,'-m','build','--wheel','--no-isolation','--outdir',dist,ROOT])
        run([sys.executable,'-m','venv','--system-site-packages',temp/'venv'])
        python=temp/'venv/bin/python';cli=temp/'venv/bin/lfcbench'
        env=os.environ.copy();env.pop('PYTHONPATH',None);env['PYTHONNOUSERSITE']='1'
        run([python,'-m','pip','install','--no-deps',next(dist.glob('lfcbenchmark-*.whl'))],env=env)
        pkg=temp/'plugin';pkg.mkdir()
        (pkg/'pyproject.toml').write_text('''
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"
[project]
name = "lfcb-entrypoint-validation"
version = "1.0.0"
[project.entry-points."lfcbenchmark.compressors"]
"demo.codec" = "demo_plugin:Demo"
[project.entry-points."lfcbenchmark.metrics"]
"demo.quality" = "demo_plugin:quality"
[project.entry-points."lfcbenchmark.ranking_metrics"]
"demo.error" = "demo_plugin:rank_metric"
[tool.setuptools]
py-modules = ["demo_plugin"]
''')
        (pkg/'demo_plugin.py').write_text('''
from lfcbench import plugin_metadata, RankingMetric
from lfcbench.compressors import IdentityCompressor
@plugin_metadata(tracks=("domain_specific",),domains=("cosmology",))
class Demo(IdentityCompressor):
    pass
@plugin_metadata(tracks=("domain_specific",),domains=("cosmology",),needs_context=True)
def quality(original,reconstructed,*,context):
    return {"domain":context["domain"],"error":float(abs(original-reconstructed).max())}
rank_metric=RankingMetric("demo.error","Demo error","lower")
''')
        run([sys.executable,'-m','build','--wheel','--no-isolation','--outdir',dist,pkg])
        run([python,'-m','pip','install','--no-deps',next(dist.glob('lfcb_entrypoint_validation-*.whl'))],env=env)
        listed=json.loads(run([cli,'list','--track','domain_specific','--json'],cwd=temp,env=env))
        assert any(x['name']=='demo.codec' and x['status']=='available' for x in listed)
        assert 'demo.quality' in run([cli,'list-metrics'],cwd=temp,env=env)
        assert 'demo.error' in run([cli,'list-ranking-metrics'],cwd=temp,env=env)
        code='''
import importlib.metadata, numpy as np
from lfcbench import AbsoluteError, benchmark
assert importlib.metadata.version("lfcbenchmark")=="0.1.1"
result=benchmark(np.arange(9,dtype=np.float32).reshape(3,3),compressor="demo.codec",error=AbsoluteError(.1),
    metric_context={"domain":"cosmology"},quality_metrics=[{"name":"demo.quality"}])
assert result["status"]=="ok" and result["metrics"]["quality"]["demo.quality"]["error"]==0
assert result["compressor_registration"]["domains"]==("cosmology",)
'''
        run([python,'-c',code],cwd=temp,env=env)
        print('Installed wheel and compressor/metric/ranking entry points passed on HPDPS-8.')

if __name__=='__main__':main()
