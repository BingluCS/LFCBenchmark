"""Example domain-tagged metric; this is not a validated climate application."""
import numpy as np
from lfcbench import RankingMetric, register_metric, register_ranking_metric


@register_metric("example.climate_bias", tracks=("domain_specific",),
                 data_models=("grid",), domains=("climate",), needs_context=True,
                 description="Illustrative mean reconstruction bias")
def climate_bias(original, reconstructed, *, context):
    delta = reconstructed.astype(np.float64) - original.astype(np.float64)
    bias = float(np.mean(delta))
    return {"mean_bias":bias,"absolute_mean_bias":abs(bias),
            "units":context.get("metadata",{}).get("units","unspecified")}


register_ranking_metric(RankingMetric("example.climate_bias", "Absolute mean bias", "lower"))
