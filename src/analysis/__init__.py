"""
Statistical processing, pairwise format comparison, break-even analysis,
and decision framework models.

Stage 8: statistics, comparison, breakeven, decision_model
"""

from src.analysis.statistics import (
    FormatStats,
    compute_stats,
    compute_stats_for_records,
    summary_table,
)
from src.analysis.comparison import (
    FormatComparison,
    compare_formats,
    compare_two_formats,
    comparison_table,
)
from src.analysis.breakeven import (
    BreakEvenResult,
    compute_breakeven,
    compute_breakeven_json_vs_mp,
    compute_breakeven_json_vs_gzip,
    compute_breakeven_gzip_vs_mp,
    compute_all_breakevens,
)
from src.analysis.decision_model import (
    Zone,
    Regime,
    DecisionResult,
    classify_zone,
    classify_regime,
    make_decision,
    run_decision_framework,
    decision_table,
)

from src.analysis.plots import PlotGenerator, generate_all_plots
from src.analysis.tables import TableGenerator, generate_all_tables

__all__ = [
    # Statistics
    "FormatStats",
    "compute_stats",
    "compute_stats_for_records",
    "summary_table",
    # Comparison
    "FormatComparison",
    "compare_formats",
    "compare_two_formats",
    "comparison_table",
    # Break-even
    "BreakEvenResult",
    "compute_breakeven",
    "compute_breakeven_json_vs_mp",
    "compute_breakeven_json_vs_gzip",
    "compute_breakeven_gzip_vs_mp",
    "compute_all_breakevens",
    # Decision model
    "Zone",
    "Regime",
    "DecisionResult",
    "classify_zone",
    "classify_regime",
    "make_decision",
    "run_decision_framework",
    "decision_table",
    # Stage 9 Plots & Tables
    "PlotGenerator",
    "generate_all_plots",
    "TableGenerator",
    "generate_all_tables",
]
