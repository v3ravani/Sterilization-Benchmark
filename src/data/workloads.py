"""
Workload configuration definitions for the benchmark experiment.

Defines named workload presets combining:
  - Target payload size (KB)
  - Data structure type
  - Redundancy level
  - Random seed for reproducibility

These are the canonical workload configurations referenced by the
experiment runner and experiment.yaml.
"""

from dataclasses import dataclass, field
from typing import List, Dict


# ─────────────────────────────────────────────────────────────────────────────
# Size targets (KB)
# ─────────────────────────────────────────────────────────────────────────────

class SizeTarget:
    """Canonical payload size targets in kilobytes."""
    SMALL  = 10.0      # ~10 KB
    MEDIUM = 500.0     # ~500 KB
    LARGE  = 5_000.0   # ~5 MB


# ─────────────────────────────────────────────────────────────────────────────
# Redundancy levels
# ─────────────────────────────────────────────────────────────────────────────

class RedundancyLevel:
    """
    Redundancy level determines how compressible the generated data is.
      - LOW:    Highly unique values → poor GZIP compression → favors binary formats.
      - MEDIUM: Moderate repetition → moderate GZIP gains.
      - HIGH:   Heavy string repetition → excellent GZIP compression.
    """
    LOW    = "low"
    MEDIUM = "medium"
    HIGH   = "high"


# ─────────────────────────────────────────────────────────────────────────────
# Data structure types
# ─────────────────────────────────────────────────────────────────────────────

class DataStructure:
    """Supported synthetic data structure types."""
    FLAT        = "flat"
    NESTED      = "nested"
    TEXT_HEAVY  = "text_heavy"
    NUMERIC     = "numeric"


# ─────────────────────────────────────────────────────────────────────────────
# Workload definition
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Workload:
    """
    Immutable definition of a single benchmark workload configuration.

    Attributes:
        name:           Human-readable workload identifier.
        structure:      Data structure type (flat/nested/text_heavy/numeric).
        target_size_kb: Target serialized payload size in kilobytes.
        redundancy:     Redundancy level (low/medium/high).
        seed:           Fixed random seed for reproducibility.
        description:    Optional description of the workload intent.
    """
    name:           str
    structure:      str
    target_size_kb: float
    redundancy:     str
    seed:           int   = 42
    description:    str   = ""

    def __str__(self) -> str:
        return (
            f"Workload({self.name} | {self.structure} | "
            f"{self.target_size_kb}KB | redundancy={self.redundancy})"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Canonical workload catalog
# ─────────────────────────────────────────────────────────────────────────────

WORKLOADS: List[Workload] = [

    # ── Flat ─────────────────────────────────────────────────────────────────
    Workload("flat_small_low",    DataStructure.FLAT, SizeTarget.SMALL,  RedundancyLevel.LOW,    seed=1, description="Small flat dict, low redundancy"),
    Workload("flat_small_medium", DataStructure.FLAT, SizeTarget.SMALL,  RedundancyLevel.MEDIUM, seed=2, description="Small flat dict, medium redundancy"),
    Workload("flat_small_high",   DataStructure.FLAT, SizeTarget.SMALL,  RedundancyLevel.HIGH,   seed=3, description="Small flat dict, high redundancy"),

    Workload("flat_medium_low",    DataStructure.FLAT, SizeTarget.MEDIUM, RedundancyLevel.LOW,    seed=4, description="Medium flat dict, low redundancy"),
    Workload("flat_medium_medium", DataStructure.FLAT, SizeTarget.MEDIUM, RedundancyLevel.MEDIUM, seed=5, description="Medium flat dict, medium redundancy"),
    Workload("flat_medium_high",   DataStructure.FLAT, SizeTarget.MEDIUM, RedundancyLevel.HIGH,   seed=6, description="Medium flat dict, high redundancy"),

    Workload("flat_large_low",    DataStructure.FLAT, SizeTarget.LARGE,  RedundancyLevel.LOW,    seed=7, description="Large flat dict, low redundancy"),
    Workload("flat_large_medium", DataStructure.FLAT, SizeTarget.LARGE,  RedundancyLevel.MEDIUM, seed=8, description="Large flat dict, medium redundancy"),
    Workload("flat_large_high",   DataStructure.FLAT, SizeTarget.LARGE,  RedundancyLevel.HIGH,   seed=9, description="Large flat dict, high redundancy"),

    # ── Nested ───────────────────────────────────────────────────────────────
    Workload("nested_small_low",    DataStructure.NESTED, SizeTarget.SMALL,  RedundancyLevel.LOW,    seed=10, description="Small nested tree, low redundancy"),
    Workload("nested_small_medium", DataStructure.NESTED, SizeTarget.SMALL,  RedundancyLevel.MEDIUM, seed=11, description="Small nested tree, medium redundancy"),
    Workload("nested_small_high",   DataStructure.NESTED, SizeTarget.SMALL,  RedundancyLevel.HIGH,   seed=12, description="Small nested tree, high redundancy"),

    Workload("nested_medium_low",    DataStructure.NESTED, SizeTarget.MEDIUM, RedundancyLevel.LOW,    seed=13, description="Medium nested tree, low redundancy"),
    Workload("nested_medium_medium", DataStructure.NESTED, SizeTarget.MEDIUM, RedundancyLevel.MEDIUM, seed=14, description="Medium nested tree, medium redundancy"),
    Workload("nested_medium_high",   DataStructure.NESTED, SizeTarget.MEDIUM, RedundancyLevel.HIGH,   seed=15, description="Medium nested tree, high redundancy"),

    Workload("nested_large_low",    DataStructure.NESTED, SizeTarget.LARGE,  RedundancyLevel.LOW,    seed=16, description="Large nested tree, low redundancy"),
    Workload("nested_large_medium", DataStructure.NESTED, SizeTarget.LARGE,  RedundancyLevel.MEDIUM, seed=17, description="Large nested tree, medium redundancy"),
    Workload("nested_large_high",   DataStructure.NESTED, SizeTarget.LARGE,  RedundancyLevel.HIGH,   seed=18, description="Large nested tree, high redundancy"),

    # ── Text-Heavy ───────────────────────────────────────────────────────────
    Workload("text_small_medium", DataStructure.TEXT_HEAVY, SizeTarget.SMALL,  RedundancyLevel.MEDIUM, seed=19, description="Small text corpus, medium redundancy"),
    Workload("text_small_high",   DataStructure.TEXT_HEAVY, SizeTarget.SMALL,  RedundancyLevel.HIGH,   seed=20, description="Small text corpus, high redundancy"),

    Workload("text_medium_medium", DataStructure.TEXT_HEAVY, SizeTarget.MEDIUM, RedundancyLevel.MEDIUM, seed=21, description="Medium text corpus, medium redundancy"),
    Workload("text_medium_high",   DataStructure.TEXT_HEAVY, SizeTarget.MEDIUM, RedundancyLevel.HIGH,   seed=22, description="Medium text corpus, high redundancy"),

    Workload("text_large_medium", DataStructure.TEXT_HEAVY, SizeTarget.LARGE,  RedundancyLevel.MEDIUM, seed=23, description="Large text corpus, medium redundancy"),
    Workload("text_large_high",   DataStructure.TEXT_HEAVY, SizeTarget.LARGE,  RedundancyLevel.HIGH,   seed=24, description="Large text corpus, high redundancy"),

    # ── Numeric ──────────────────────────────────────────────────────────────
    Workload("numeric_small_low",    DataStructure.NUMERIC, SizeTarget.SMALL,  RedundancyLevel.LOW,    seed=25, description="Small numeric arrays, low redundancy"),
    Workload("numeric_small_medium", DataStructure.NUMERIC, SizeTarget.SMALL,  RedundancyLevel.MEDIUM, seed=26, description="Small numeric arrays, medium redundancy"),

    Workload("numeric_medium_low",    DataStructure.NUMERIC, SizeTarget.MEDIUM, RedundancyLevel.LOW,    seed=27, description="Medium numeric arrays, low redundancy"),
    Workload("numeric_medium_medium", DataStructure.NUMERIC, SizeTarget.MEDIUM, RedundancyLevel.MEDIUM, seed=28, description="Medium numeric arrays, medium redundancy"),

    Workload("numeric_large_low",    DataStructure.NUMERIC, SizeTarget.LARGE,  RedundancyLevel.LOW,    seed=29, description="Large numeric arrays, low redundancy"),
    Workload("numeric_large_medium", DataStructure.NUMERIC, SizeTarget.LARGE,  RedundancyLevel.MEDIUM, seed=30, description="Large numeric arrays, medium redundancy"),
]


# ─────────────────────────────────────────────────────────────────────────────
# Lookup helpers
# ─────────────────────────────────────────────────────────────────────────────

_WORKLOAD_INDEX: Dict[str, Workload] = {w.name: w for w in WORKLOADS}


def get_workload(name: str) -> Workload:
    """
    Retrieve a workload by name.

    :param name: Workload name string (e.g. 'flat_medium_high').
    :raises KeyError: If no workload with that name exists.
    :return: Workload instance.
    """
    if name not in _WORKLOAD_INDEX:
        raise KeyError(
            f"No workload named '{name}'. "
            f"Available: {list_workload_names()}"
        )
    return _WORKLOAD_INDEX[name]


def list_workload_names() -> List[str]:
    """Return sorted list of all registered workload names."""
    return sorted(_WORKLOAD_INDEX.keys())


def get_workloads_by_structure(structure: str) -> List[Workload]:
    """Return all workloads for a given data structure type."""
    return [w for w in WORKLOADS if w.structure == structure]


def get_workloads_by_size(size_label: str) -> List[Workload]:
    """
    Return all workloads matching a size label.

    :param size_label: One of 'small', 'medium', 'large'.
    """
    size_map = {
        "small":  SizeTarget.SMALL,
        "medium": SizeTarget.MEDIUM,
        "large":  SizeTarget.LARGE,
    }
    target = size_map.get(size_label.lower())
    if target is None:
        raise ValueError(f"Unknown size label '{size_label}'. Use 'small', 'medium', or 'large'.")
    return [w for w in WORKLOADS if w.target_size_kb == target]
