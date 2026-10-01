"""
Experiment configuration and matrix definition for the benchmark runner.

Loads experiment parameters from config/experiment.yaml and pre-computes
the full Cartesian product of (workloads × formats × network_profiles) so
the runner can iterate over a flat, predictable list of MatrixCell objects.

Usage:
    config = load_experiment_config("config/experiment.yaml")
    matrix = build_matrix(config)
    for cell in matrix.cells:
        print(cell)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import yaml

from src.data.workloads import WORKLOADS, Workload, get_workload


# ─────────────────────────────────────────────────────────────────────────────
# Threshold configuration
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class AnalysisThresholds:
    """
    Zone classification thresholds for the 3-zone decision framework.

    Attributes:
        no_switch: Relative gain below this → Stay with JSON (Zone 1).
        switch:    Relative gain at or above this → Switch (Zone 3).
                   Between no_switch and switch → Evaluate (Zone 2).
    """
    no_switch: float = 0.05   # 5%
    switch:    float = 0.20   # 20%


# ─────────────────────────────────────────────────────────────────────────────
# Experiment configuration
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ExperimentConfig:
    """
    Full configuration for one benchmark experiment run.

    Loaded from config/experiment.yaml.  All fields mirror the YAML schema
    so the struct is a 1-to-1 mapping of the config file.

    Attributes:
        name:                  Human-readable experiment name.
        version:               Experiment version string.
        experiment_id:         Auto-generated unique ID for this run.
        repetitions:           Number of measured iterations per cell.
        warmup_runs:           Number of discarded warm-up iterations per cell.
        workload_names:        Names of Workload objects to run (from WORKLOADS catalog).
                               Empty list → use all workloads.
        serializer_names:      Serializer format names to include.
        network_profile_names: Network profile names to include.
        gzip_compression_level: Compression level for GZIP serializer (1–9).
        thresholds:            Zone classification thresholds.
    """
    name:                  str = "benchmark"
    version:               str = "1.0"
    experiment_id:         str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    repetitions:           int = 5
    warmup_runs:           int = 1
    workload_names:        List[str] = field(default_factory=lambda: [w.name for w in WORKLOADS])
    serializer_names:      List[str] = field(default_factory=lambda: ["json", "json_gzip", "messagepack"])
    network_profile_names: List[str] = field(default_factory=lambda: ["FAST", "SLOW"])
    gzip_compression_level: int = 6
    thresholds:            AnalysisThresholds = field(default_factory=AnalysisThresholds)

    def __post_init__(self) -> None:
        if self.repetitions < 1:
            raise ValueError(f"repetitions must be >= 1, got {self.repetitions}")
        if self.warmup_runs < 0:
            raise ValueError(f"warmup_runs must be >= 0, got {self.warmup_runs}")

    @property
    def total_iterations_per_cell(self) -> int:
        """Total iterations run per matrix cell (warmup + measured)."""
        return self.warmup_runs + self.repetitions

    def __repr__(self) -> str:
        return (
            f"ExperimentConfig("
            f"name={self.name!r}, "
            f"reps={self.repetitions}, "
            f"warmup={self.warmup_runs}, "
            f"formats={self.serializer_names}, "
            f"profiles={self.network_profile_names})"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Matrix cell — one (workload, format, profile) combination
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class MatrixCell:
    """
    A single experimental unit: one workload × format × network profile triplet.

    The runner iterates over a list of these, running `config.repetitions`
    measured iterations (plus warmup) for each cell.

    Attributes:
        workload:       Workload definition (structure, size, redundancy, seed).
        format_name:    Serializer identifier ('json', 'json_gzip', 'messagepack').
        profile_name:   Network profile identifier ('FAST', 'SLOW', etc.).
        cell_index:     Zero-based index within the full matrix.
    """
    workload:    Workload
    format_name: str
    profile_name: str
    cell_index:  int = 0

    def __str__(self) -> str:
        return (
            f"MatrixCell[{self.cell_index}]("
            f"workload={self.workload.name!r}, "
            f"format={self.format_name!r}, "
            f"profile={self.profile_name!r})"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Experiment matrix — pre-computed Cartesian product
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ExperimentMatrix:
    """
    Pre-computed Cartesian product of (workloads × formats × network_profiles).

    Attributes:
        cells:          Ordered list of MatrixCell objects.
        config:         The ExperimentConfig that produced this matrix.
        total_runs:     Total measured iterations across all cells.
    """
    cells:  List[MatrixCell]
    config: ExperimentConfig

    @property
    def total_runs(self) -> int:
        """Total measured runs = cells × repetitions (warmups excluded)."""
        return len(self.cells) * self.config.repetitions

    @property
    def total_iterations(self) -> int:
        """Total iterations including warmups = cells × (warmup + reps)."""
        return len(self.cells) * self.config.total_iterations_per_cell

    def __repr__(self) -> str:
        return (
            f"ExperimentMatrix("
            f"cells={len(self.cells)}, "
            f"reps={self.config.repetitions}, "
            f"total_runs={self.total_runs})"
        )


# ─────────────────────────────────────────────────────────────────────────────
# YAML loader
# ─────────────────────────────────────────────────────────────────────────────

def load_experiment_config(
    path: str | Path = "config/experiment.yaml",
) -> ExperimentConfig:
    """
    Load an ExperimentConfig from a YAML file.

    :param path: Path to the YAML configuration file.
    :raises FileNotFoundError: If the YAML file does not exist.
    :raises KeyError:          If required YAML keys are missing.
    :return: Populated ExperimentConfig instance.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Experiment config not found: {path.resolve()}")

    with path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    exp      = raw.get("experiment", {})
    workloads = raw.get("workloads", {})
    analysis  = raw.get("analysis", {})
    thresholds_raw = analysis.get("thresholds", {})

    # Determine workload names: if explicit list provided use those; else derive
    # from the sizes × structures × redundancy cross-product in the YAML.
    workload_names: List[str] = exp.get("workload_names", [])
    if not workload_names:
        # Default: use all registered workloads
        workload_names = [w.name for w in WORKLOADS]

    serializer_names: List[str] = raw.get("serializers", ["json", "json_gzip", "messagepack"])
    network_profile_names: List[str] = list(
        raw.get("network_profiles", {}).get("profiles", {}).keys()
    ) or ["FAST", "MODERATE", "SLOW", "VERY_SLOW"]

    # Also try reading profiles from the profiles section key list
    if not network_profile_names:
        network_profile_names = ["FAST", "MODERATE", "SLOW", "VERY_SLOW"]

    thresholds = AnalysisThresholds(
        no_switch=float(thresholds_raw.get("no_switch", 0.05)),
        switch=float(thresholds_raw.get("switch", 0.20)),
    )

    return ExperimentConfig(
        name=exp.get("name", "benchmark"),
        version=str(exp.get("version", "1.0")),
        experiment_id=str(uuid.uuid4())[:8],
        repetitions=int(exp.get("repetitions", 10)),
        warmup_runs=int(exp.get("warmup_runs", 2)),
        workload_names=workload_names,
        serializer_names=serializer_names,
        network_profile_names=network_profile_names,
        gzip_compression_level=int(raw.get("gzip", {}).get("compression_level", 6)),
        thresholds=thresholds,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Matrix builder
# ─────────────────────────────────────────────────────────────────────────────

def build_matrix(config: ExperimentConfig) -> ExperimentMatrix:
    """
    Build the full experimental matrix from an ExperimentConfig.

    Computes the Cartesian product:
        workloads × serializer_names × network_profile_names

    :param config: ExperimentConfig loaded from YAML.
    :raises KeyError: If a workload name in config is not in the catalog.
    :return: ExperimentMatrix with all MatrixCell entries.
    """
    cells: List[MatrixCell] = []
    idx = 0
    for workload_name in config.workload_names:
        workload = get_workload(workload_name)
        for format_name in config.serializer_names:
            for profile_name in config.network_profile_names:
                cells.append(MatrixCell(
                    workload=workload,
                    format_name=format_name,
                    profile_name=profile_name,
                    cell_index=idx,
                ))
                idx += 1

    return ExperimentMatrix(cells=cells, config=config)


# ─────────────────────────────────────────────────────────────────────────────
# Quick preset configs for fast integration/smoke testing
# ─────────────────────────────────────────────────────────────────────────────

def quick_config(repetitions: int = 3, warmup_runs: int = 1) -> ExperimentConfig:
    """
    Minimal config for smoke testing: small workloads, all formats, all profiles.

    :param repetitions: Number of measured iterations (default 3).
    :param warmup_runs: Number of warmup iterations (default 1).
    :return: ExperimentConfig for fast validation runs.
    """
    # Pick only small-sized workloads for speed
    small_workloads = [
        w.name for w in WORKLOADS
        if w.target_size_kb <= 10.0
    ]
    return ExperimentConfig(
        name="quick_smoke_test",
        version="0.1",
        experiment_id=str(uuid.uuid4())[:8],
        repetitions=repetitions,
        warmup_runs=warmup_runs,
        workload_names=small_workloads[:3],   # max 3 for speed
        serializer_names=["json", "json_gzip", "messagepack"],
        network_profile_names=["FAST", "SLOW"],
        gzip_compression_level=6,
        thresholds=AnalysisThresholds(),
    )
