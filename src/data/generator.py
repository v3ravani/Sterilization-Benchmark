"""
Synthetic dataset generator for benchmark workloads.

Generates reproducible application-level data objects across four data types:
  - flat        : Flat key-value dictionary (typical API response)
  - nested      : Deeply nested hierarchical structures (typical config/document)
  - text_heavy  : Repeated string data (high redundancy, compressibility-friendly)
  - numeric     : Numeric arrays (low redundancy, binary-friendly)

All generators accept a target_size_kb parameter and scale output to hit that
approximate size. A random seed can be specified for reproducibility.
"""

import json
import math
import random
import string
from typing import Any, Dict, List, Union

# Type alias for application data objects
DataObject = Union[Dict[str, Any], List[Any]]


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _measure_json_size_bytes(data: DataObject) -> int:
    """Return the JSON-serialized byte size of a data object."""
    return len(json.dumps(data, separators=(',', ':')).encode('utf-8'))


def _random_string(length: int, rng: random.Random) -> str:
    """Return a random ASCII string of given length."""
    return ''.join(rng.choices(string.ascii_lowercase + string.digits + '_', k=length))


def _random_word(rng: random.Random) -> str:
    """Return a random English-like 4-10 char word."""
    return ''.join(rng.choices(string.ascii_lowercase, k=rng.randint(4, 10)))


# ─────────────────────────────────────────────────────────────────────────────
# 1. Flat Dictionary Generator
# ─────────────────────────────────────────────────────────────────────────────

def generate_flat_data(
    target_size_kb: float = 10.0,
    redundancy: str = "medium",
    seed: int = 42,
) -> Dict[str, Any]:
    """
    Generate a flat key-value dictionary dataset.

    Mimics a typical REST API response with scalar fields.
    Keys are unique strings; values include integers, floats, booleans, and strings.

    :param target_size_kb: Approximate target payload size in kilobytes.
    :param redundancy: 'low' | 'medium' | 'high' — controls string value repetition.
    :param seed: Random seed for reproducibility.
    :return: Flat dictionary object.
    """
    rng = random.Random(seed)
    target_bytes = int(target_size_kb * 1024)

    # Redundancy controls string pool size: smaller pool → more repeated values
    pool_sizes = {"low": 500, "medium": 50, "high": 5}
    pool_size = pool_sizes.get(redundancy, 50)

    string_pool = [_random_word(rng) + "_" + _random_word(rng) for _ in range(pool_size)]

    data: Dict[str, Any] = {}
    idx = 0

    def _add_field(i: int) -> None:
        key = f"field_{i:05d}"
        value_type = i % 5
        if value_type == 0:
            data[key] = rng.choice(string_pool)
        elif value_type == 1:
            data[key] = rng.randint(0, 1_000_000)
        elif value_type == 2:
            data[key] = round(rng.uniform(0.0, 9999.99), 4)
        elif value_type == 3:
            data[key] = rng.choice([True, False])
        else:
            data[key] = rng.choice(string_pool) + "_" + str(rng.randint(0, 999))

    # Fast estimation step: add first field to measure incremental size
    _add_field(idx)
    idx += 1
    sample_bytes = len(json.dumps(data).encode("utf-8")) + 1

    if target_bytes > sample_bytes:
        est_remaining = max(1, (target_bytes - sample_bytes) // sample_bytes)
        for _ in range(est_remaining):
            _add_field(idx)
            idx += 1

    current_size = _measure_json_size_bytes(data)
    while current_size < target_bytes:
        remaining_bytes = target_bytes - current_size
        step = max(1, remaining_bytes // sample_bytes)
        for _ in range(step):
            _add_field(idx)
            idx += 1
        current_size = _measure_json_size_bytes(data)

    return data


# ─────────────────────────────────────────────────────────────────────────────
# 2. Nested Hierarchy Generator
# ─────────────────────────────────────────────────────────────────────────────

def _generate_nested_node(
    depth: int,
    max_depth: int,
    breadth: int,
    rng: random.Random,
    string_pool: List[str],
) -> Dict[str, Any]:
    """Recursively build a nested dict tree node."""
    node: Dict[str, Any] = {
        "id": _random_string(8, rng),
        "value": rng.choice(string_pool),
        "count": rng.randint(0, 9999),
        "active": rng.choice([True, False]),
        "score": round(rng.uniform(0.0, 100.0), 3),
    }
    if depth < max_depth:
        node["metadata"] = {
            "created_at": f"2024-{rng.randint(1,12):02d}-{rng.randint(1,28):02d}",
            "tags": [rng.choice(string_pool) for _ in range(rng.randint(2, 5))],
            "priority": rng.randint(1, 5),
        }
        node["children"] = [
            _generate_nested_node(depth + 1, max_depth, breadth, rng, string_pool)
            for _ in range(breadth)
        ]
    return node


def generate_nested_data(
    target_size_kb: float = 10.0,
    redundancy: str = "medium",
    seed: int = 42,
) -> Dict[str, Any]:
    """
    Generate a deeply nested hierarchical dataset.

    Mimics complex API objects such as project/task trees, organizational
    hierarchies, or nested configuration documents.

    :param target_size_kb: Approximate target payload size in kilobytes.
    :param redundancy: 'low' | 'medium' | 'high' — controls string pool size.
    :param seed: Random seed for reproducibility.
    :return: Nested dict object.
    """
    rng = random.Random(seed)
    target_bytes = int(target_size_kb * 1024)

    pool_sizes = {"low": 500, "medium": 50, "high": 5}
    pool_size = pool_sizes.get(redundancy, 50)
    string_pool = [_random_word(rng) for _ in range(pool_size)]

    # Start with depth=3, breadth=2 and grow the root list
    max_depth = 3
    breadth = 2
    data: Dict[str, Any] = {
        "schema_version": "1.0",
        "experiment_id": _random_string(12, rng),
        "entries": [],
    }

    # Sample first entry to measure entry size
    sample_entry = _generate_nested_node(0, max_depth, breadth, rng, string_pool)
    data["entries"].append(sample_entry)
    sample_bytes = len(json.dumps(sample_entry).encode("utf-8")) + 1
    base_bytes = _measure_json_size_bytes(data)

    if target_bytes > base_bytes:
        est_remaining = max(1, (target_bytes - base_bytes) // sample_bytes)
        for _ in range(est_remaining):
            data["entries"].append(_generate_nested_node(0, max_depth, breadth, rng, string_pool))

    current_size = _measure_json_size_bytes(data)
    while current_size < target_bytes:
        remaining_bytes = target_bytes - current_size
        step = max(1, remaining_bytes // sample_bytes)
        for _ in range(step):
            data["entries"].append(_generate_nested_node(0, max_depth, breadth, rng, string_pool))
        current_size = _measure_json_size_bytes(data)

    return data


# ─────────────────────────────────────────────────────────────────────────────
# 3. Text-Heavy Generator (High Redundancy / Compressibility)
# ─────────────────────────────────────────────────────────────────────────────

def generate_text_heavy_data(
    target_size_kb: float = 10.0,
    redundancy: str = "high",
    seed: int = 42,
) -> Dict[str, Any]:
    """
    Generate a text-heavy dataset with high string redundancy.

    Ideal for testing GZIP compression effectiveness. Strings are drawn from
    a small pool of phrases, resulting in high compressibility.

    :param target_size_kb: Approximate target payload size in kilobytes.
    :param redundancy: 'low' | 'medium' | 'high' — controls phrase pool size.
    :param seed: Random seed for reproducibility.
    :return: Dictionary containing text-heavy string entries.
    """
    rng = random.Random(seed)
    target_bytes = int(target_size_kb * 1024)

    # Smaller pool = more repetition = better GZIP compression
    pool_sizes = {"low": 200, "medium": 20, "high": 4}
    pool_size = pool_sizes.get(redundancy, 20)

    phrase_pool = [
        " ".join(_random_word(rng) for _ in range(rng.randint(5, 12)))
        for _ in range(pool_size)
    ]

    data: Dict[str, Any] = {
        "type": "text_corpus",
        "redundancy": redundancy,
        "records": [],
    }

    record_idx = 0

    def _make_record(i: int) -> Dict[str, Any]:
        return {
            "record_id": i,
            "title": rng.choice(phrase_pool),
            "body": " ".join(rng.choice(phrase_pool) for _ in range(rng.randint(3, 8))),
            "author": rng.choice(phrase_pool).split()[0],
            "category": rng.choice(phrase_pool).split()[0],
            "summary": rng.choice(phrase_pool),
        }

    sample_rec = _make_record(record_idx)
    data["records"].append(sample_rec)
    record_idx += 1
    sample_bytes = len(json.dumps(sample_rec).encode("utf-8")) + 1
    base_bytes = _measure_json_size_bytes(data)

    if target_bytes > base_bytes:
        est_remaining = max(1, (target_bytes - base_bytes) // sample_bytes)
        for _ in range(est_remaining):
            data["records"].append(_make_record(record_idx))
            record_idx += 1

    current_size = _measure_json_size_bytes(data)
    while current_size < target_bytes:
        remaining_bytes = target_bytes - current_size
        step = max(1, remaining_bytes // sample_bytes)
        for _ in range(step):
            data["records"].append(_make_record(record_idx))
            record_idx += 1
        current_size = _measure_json_size_bytes(data)

    return data


# ─────────────────────────────────────────────────────────────────────────────
# 4. Numeric Array Generator (Low Redundancy / Binary-Friendly)
# ─────────────────────────────────────────────────────────────────────────────

def generate_numeric_data(
    target_size_kb: float = 10.0,
    redundancy: str = "low",
    seed: int = 42,
) -> Dict[str, Any]:
    """
    Generate a numeric dataset with arrays of float and integer values.

    Mimics sensor readings, financial time-series, or ML feature matrices.
    Low redundancy makes GZIP less effective; favors binary formats (MessagePack).

    :param target_size_kb: Approximate target payload size in kilobytes.
    :param redundancy: 'low' | 'medium' | 'high' — controls value range diversity.
    :param seed: Random seed for reproducibility.
    :return: Dictionary containing numeric arrays.
    """
    rng = random.Random(seed)
    target_bytes = int(target_size_kb * 1024)

    # Lower redundancy = wider unique value range
    precision_map = {"low": 6, "medium": 2, "high": 0}
    precision = precision_map.get(redundancy, 6)

    data: Dict[str, Any] = {
        "type": "numeric_series",
        "redundancy": redundancy,
        "series": [],
    }

    series_idx = 0

    def _make_series(idx: int) -> Dict[str, Any]:
        n_points = 50
        readings = [
            round(rng.uniform(-1e6, 1e6), precision) if precision > 0
            else rng.randint(-1_000_000, 1_000_000)
            for _ in range(n_points)
        ]
        return {
            "series_id": idx,
            "sensor": f"sensor_{idx % 20:03d}",
            "unit": rng.choice(["celsius", "pascal", "meters", "volts", "amps"]),
            "readings": readings,
            "min": min(readings),
            "max": max(readings),
            "mean": round(sum(readings) / len(readings), precision),
        }

    sample_series = _make_series(series_idx)
    data["series"].append(sample_series)
    series_idx += 1
    sample_bytes = len(json.dumps(sample_series).encode("utf-8")) + 1
    base_bytes = _measure_json_size_bytes(data)

    if target_bytes > base_bytes:
        est_remaining = max(1, (target_bytes - base_bytes) // sample_bytes)
        for _ in range(est_remaining):
            data["series"].append(_make_series(series_idx))
            series_idx += 1

    current_size = _measure_json_size_bytes(data)
    while current_size < target_bytes:
        remaining_bytes = target_bytes - current_size
        step = max(1, remaining_bytes // sample_bytes)
        for _ in range(step):
            data["series"].append(_make_series(series_idx))
            series_idx += 1
        current_size = _measure_json_size_bytes(data)

    return data


# ─────────────────────────────────────────────────────────────────────────────
# Unified generator interface
# ─────────────────────────────────────────────────────────────────────────────

GENERATOR_MAP = {
    "flat": generate_flat_data,
    "nested": generate_nested_data,
    "text_heavy": generate_text_heavy_data,
    "numeric": generate_numeric_data,
}


def generate(
    structure: str,
    target_size_kb: float = 10.0,
    redundancy: str = "medium",
    seed: int = 42,
) -> DataObject:
    """
    Unified entry point for data generation.

    :param structure: One of 'flat', 'nested', 'text_heavy', 'numeric'.
    :param target_size_kb: Approximate target payload size in kilobytes.
    :param redundancy: One of 'low', 'medium', 'high'.
    :param seed: Random seed for reproducibility.
    :return: Generated data object.
    :raises ValueError: If structure or redundancy is not recognized.
    """
    if structure not in GENERATOR_MAP:
        raise ValueError(
            f"Unknown structure '{structure}'. "
            f"Valid options: {sorted(GENERATOR_MAP.keys())}"
        )
    if redundancy not in ("low", "medium", "high"):
        raise ValueError(
            f"Unknown redundancy '{redundancy}'. Valid options: 'low', 'medium', 'high'"
        )
    return GENERATOR_MAP[structure](
        target_size_kb=target_size_kb,
        redundancy=redundancy,
        seed=seed,
    )
