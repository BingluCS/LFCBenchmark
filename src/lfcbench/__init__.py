"""Public API for the floating-point compression benchmark."""
__version__ = "0.1.1"

from .api import AbsoluteError, Capabilities, CompressedData, Compressor
from .registry import register_compressor, unregister_compressor
from .benchmark import benchmark
from .metric_registry import register_metric, unregister_metric
from .plugin_metadata import PluginMetadata, plugin_metadata
from .leaderboard import RankingMetric, register_ranking_metric, unregister_ranking_metric, rank_entries

__all__ = ["AbsoluteError", "Capabilities", "CompressedData", "Compressor",
           "PluginMetadata", "plugin_metadata", "register_compressor", "unregister_compressor",
           "register_metric", "unregister_metric", "benchmark", "RankingMetric", "register_ranking_metric",
           "unregister_ranking_metric", "rank_entries"]
