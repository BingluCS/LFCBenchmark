"""Explicit score registration and comparable-cohort ranking."""
from __future__ import annotations
from dataclasses import asdict, dataclass
from importlib.metadata import entry_points
import math
import re

_MANUAL = {}


@dataclass(frozen=True)
class RankingMetric:
    name: str
    label: str
    direction: str
    unit: str = ""

    def __post_init__(self):
        if not isinstance(self.name,str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]*",self.name):
            raise ValueError("invalid ranking metric name")
        if not isinstance(self.label,str) or not self.label:raise ValueError("metric label is required")
        if self.direction not in ("higher","lower"):raise ValueError("direction must be higher or lower")
        if not isinstance(self.unit,str):raise TypeError("unit must be a string")


BUILTIN_METRICS = {
    x.name:x for x in [
        RankingMetric('ratio','Compression ratio','higher','×'),
        RankingMetric('bits_per_value','Bits per value','lower','bits/value'),
        RankingMetric('compress_MiB_s','Compression throughput','higher','MiB/s'),
        RankingMetric('decompress_MiB_s','Decompression throughput','higher','MiB/s'),
        # Keep the decimal-unit names for records produced before MiB/s.
        RankingMetric('compress_MB_s','Compression throughput','higher','MB/s'),
        RankingMetric('decompress_MB_s','Decompression throughput','higher','MB/s'),
        RankingMetric('psnr_db','PSNR','higher','dB'),
        RankingMetric('ssim','Median SSIM','higher'),
        RankingMetric('pcc','Median PCC','higher'),
        RankingMetric('spectral_l1','Median spectral power L1 error','lower'),
        RankingMetric('field_acf_delta','Median field autocorrelation difference','lower'),
    ]
}


def register_ranking_metric(metric):
    """Register a score definition; use entry point group lfcbenchmark.ranking_metrics to distribute."""
    if not isinstance(metric,RankingMetric):raise TypeError("metric must be RankingMetric")
    if metric.name in _MANUAL or metric.name in BUILTIN_METRICS:raise ValueError(f"duplicate ranking metric: {metric.name}")
    _MANUAL[metric.name]=metric
    return metric


def unregister_ranking_metric(name):
    """Remove a local ranking metric; built-ins and entry points remain."""
    if name not in _MANUAL:raise ValueError(f"no local ranking metric: {name}")
    del _MANUAL[name]


class RankingMetricRegistry:
    def __init__(self):
        self.items={name:[('built-in',lambda m=metric:m)] for name,metric in BUILTIN_METRICS.items()}
        for name,metric in _MANUAL.items():self.items.setdefault(name,[]).append(('local',lambda m=metric:m))
        for ep in entry_points(group='lfcbenchmark.ranking_metrics'):
            self.items.setdefault(ep.name,[]).append((f'entry point: {ep.value}',ep.load))

    def names(self):return sorted(self.items)

    def get(self,name):
        items=self.items.get(name,())
        if not items:raise ValueError(f"unknown ranking metric: {name}")
        if len(items)!=1:raise ValueError(f"duplicate ranking metric: {name}")
        metric=items[0][1]()
        if not isinstance(metric,RankingMetric) or metric.name!=name:raise TypeError("entry point must expose a matching RankingMetric")
        return metric


def rank_entries(entries, *, metric, cohort):
    """Rank verified records from exactly one cohort; missing values stay unranked.

    Each record has ``cohort``, ``codec``, ``status`` and ``metrics``. Cohort is
    an immutable protocol identifier covering dataset, input set, bound, machine,
    thread count, preprocessing and metric settings. The producer is responsible
    for auditing those properties; a JSON status alone is not independent proof.
    """
    if not isinstance(cohort,str) or not cohort:raise ValueError("cohort identifier required")
    spec=RankingMetricRegistry().get(metric);seen=set();eligible=[];unranked=[]
    for item in entries:
        if not isinstance(item,dict) or item.get('cohort')!=cohort:raise ValueError("mixed or invalid comparison cohorts")
        name=item.get('codec')
        if not isinstance(name,str) or not name or name in seen:raise ValueError("duplicate or invalid codec")
        seen.add(name);value=item.get('metrics',{}).get(metric)
        valid=isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value)
        if item.get('status')=='verified' and valid:eligible.append((item,float(value)))
        else:unranked.append({**item,'rank':None})
    eligible.sort(key=lambda pair:((-pair[1] if spec.direction=='higher' else pair[1]),pair[0]['codec']))
    output=[];previous=None;rank=0
    for index,(item,value) in enumerate(eligible,1):
        if previous is None or value!=previous:rank=index
        output.append({**item,'rank':rank});previous=value
    return {'cohort':cohort,'metric':asdict(spec),'entries':output+unranked}
