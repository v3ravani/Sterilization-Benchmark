"""
Benchmark experiment definition, runner, and high-precision timer modules.

Stage 6: PrecisionTimer, TimingRecord, time_call
Stage 7: ExperimentConfig, ExperimentMatrix, MatrixCell, BenchmarkRunner,
         ResultWriter, RunSummary
"""

from src.benchmark.timer import PrecisionTimer, TimingRecord, time_call
from src.benchmark.experiment import (
    ExperimentConfig,
    ExperimentMatrix,
    MatrixCell,
    AnalysisThresholds,
    load_experiment_config,
    build_matrix,
    quick_config,
)
from src.benchmark.runner import BenchmarkRunner, RunSummary
from src.benchmark.result_writer import ResultWriter

__all__ = [
    # Stage 6
    "PrecisionTimer",
    "TimingRecord",
    "time_call",
    # Stage 7 — Experiment
    "ExperimentConfig",
    "ExperimentMatrix",
    "MatrixCell",
    "AnalysisThresholds",
    "load_experiment_config",
    "build_matrix",
    "quick_config",
    # Stage 7 — Runner
    "BenchmarkRunner",
    "RunSummary",
    # Stage 7 — Writer
    "ResultWriter",
]
