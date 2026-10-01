"""
Statistical analysis module for benchmark results.

Computes descriptive statistics for a list of numeric measurements:
    - Mean
    - Median (P50)
    - P95 (95th percentile)
    - Min / Max
    - Standard Deviation
    - Variance
    - 95% Confidence Interval (CI95) using Student's t-distribution

Usage:
    from src.analysis.statistics import compute_stats, compute_stats_for_records

    stats = compute_stats(values=[10.5, 11.2, 9.8, 12.1], format_name="json", field="t_e2e_ms")
    print(stats.mean, stats.p95, stats.ci95_lower, stats.ci95_upper)

    # Or from a list of MetricRecord:
    all_stats = compute_stats_for_records(records, field="t_e2e_ms")
    for fmt, stats in all_stats.items():
        print(fmt, stats)
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Dict, List, Sequence


# ─────────────────────────────────────────────────────────────────────────────
# FormatStats result container
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class FormatStats:
    """
    Descriptive statistics for a single metric field across N observations.

    Attributes:
        format_name: Serializer format name (e.g. 'json', 'json_gzip').
        field:       Metric field name (e.g. 't_e2e_ms', 'payload_size_bytes').
        n:           Number of observations used.
        mean:        Arithmetic mean.
        median:      50th percentile (P50).
        p95:         95th percentile.
        min:         Minimum value.
        max:         Maximum value.
        std:         Sample standard deviation (ddof=1).
        variance:    Sample variance (ddof=1).
        ci95_lower:  Lower bound of the 95% confidence interval.
        ci95_upper:  Upper bound of the 95% confidence interval.
    """
    format_name: str
    field:       str
    n:           int
    mean:        float
    median:      float
    p95:         float
    min:         float
    max:         float
    std:         float
    variance:    float
    ci95_lower:  float
    ci95_upper:  float

    def to_dict(self) -> dict:
        """Serialize to flat dictionary for export."""
        return {
            "format_name": self.format_name,
            "field":       self.field,
            "n":           self.n,
            "mean":        round(self.mean, 6),
            "median":      round(self.median, 6),
            "p95":         round(self.p95, 6),
            "min":         round(self.min, 6),
            "max":         round(self.max, 6),
            "std":         round(self.std, 6),
            "variance":    round(self.variance, 6),
            "ci95_lower":  round(self.ci95_lower, 6),
            "ci95_upper":  round(self.ci95_upper, 6),
        }

    def __repr__(self) -> str:
        return (
            f"FormatStats({self.format_name!r}/{self.field!r}: "
            f"mean={self.mean:.4f}, p95={self.p95:.4f}, "
            f"CI95=[{self.ci95_lower:.4f},{self.ci95_upper:.4f}], n={self.n})"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _percentile(sorted_values: List[float], p: float) -> float:
    """
    Compute the p-th percentile using linear interpolation (numpy-compatible).

    :param sorted_values: Pre-sorted list of floats.
    :param p:             Percentile in range [0, 100].
    :return:              Interpolated percentile value.
    """
    n = len(sorted_values)
    if n == 0:
        return 0.0
    if n == 1:
        return sorted_values[0]

    # Hazen's formula: index = p/100 * (n-1)
    index = p / 100.0 * (n - 1)
    lower = int(math.floor(index))
    upper = int(math.ceil(index))
    if lower == upper:
        return sorted_values[lower]

    frac = index - lower
    return sorted_values[lower] + frac * (sorted_values[upper] - sorted_values[lower])


def _t_critical_95(df: int) -> float:
    """
    Return the two-tailed t critical value for 95% CI given degrees of freedom.

    Uses a lookup table for common df values and approximates for larger df.
    For df >= 30 the normal approximation (1.96) is used.

    :param df: Degrees of freedom (n - 1).
    :return:   t critical value for alpha=0.05 (two-tailed).
    """
    # Lookup table for small samples
    _T_TABLE = {
        1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571,
        6: 2.447,  7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228,
        11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131,
        16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086,
        25: 2.060, 29: 2.045,
    }
    if df in _T_TABLE:
        return _T_TABLE[df]
    if df >= 30:
        return 1.96   # Normal approximation
    # Linear interpolation between known values
    keys = sorted(_T_TABLE.keys())
    for i in range(len(keys) - 1):
        if keys[i] <= df <= keys[i + 1]:
            lo, hi = keys[i], keys[i + 1]
            frac = (df - lo) / (hi - lo)
            return _T_TABLE[lo] + frac * (_T_TABLE[hi] - _T_TABLE[lo])
    return 1.96  # fallback


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def compute_stats(
    values: Sequence[float],
    format_name: str = "",
    field: str = "",
) -> FormatStats:
    """
    Compute descriptive statistics for a sequence of numeric values.

    :param values:      Sequence of floats (e.g. list of t_e2e_ms measurements).
    :param format_name: Label for the format (used in FormatStats).
    :param field:       Label for the metric field (used in FormatStats).
    :raises ValueError: If `values` is empty.
    :return: FormatStats with all descriptive statistics populated.
    """
    if not values:
        raise ValueError("Cannot compute statistics on an empty sequence.")

    data = sorted(float(v) for v in values)
    n    = len(data)

    mean_val  = statistics.mean(data)
    median_val = _percentile(data, 50.0)
    p95_val   = _percentile(data, 95.0)
    min_val   = data[0]
    max_val   = data[-1]

    if n > 1:
        std_val = statistics.stdev(data)   # sample std (ddof=1)
    else:
        std_val = 0.0

    var_val = std_val ** 2

    # 95% confidence interval: mean ± t * (std / sqrt(n))
    if n > 1:
        se     = std_val / math.sqrt(n)
        t_crit = _t_critical_95(n - 1)
        margin = t_crit * se
        ci_lo  = mean_val - margin
        ci_hi  = mean_val + margin
    else:
        ci_lo = mean_val
        ci_hi = mean_val

    return FormatStats(
        format_name=format_name,
        field=field,
        n=n,
        mean=mean_val,
        median=median_val,
        p95=p95_val,
        min=min_val,
        max=max_val,
        std=std_val,
        variance=var_val,
        ci95_lower=ci_lo,
        ci95_upper=ci_hi,
    )


def compute_stats_for_records(
    records,              # List[MetricRecord]
    field: str,
    valid_only: bool = True,
) -> Dict[str, FormatStats]:
    """
    Compute per-format statistics for a named metric field across all records.

    :param records:    List of MetricRecord objects (from MetricsCollector).
    :param field:      Attribute name on MetricRecord (e.g. 't_e2e_ms').
    :param valid_only: If True, only use records where valid=True.
    :raises AttributeError: If `field` is not an attribute of MetricRecord.
    :return: Dict mapping format_name → FormatStats.
    """
    # Group values by format
    groups: Dict[str, List[float]] = {}
    for rec in records:
        if valid_only and not rec.valid:
            continue
        fmt = rec.format_name
        if fmt not in groups:
            groups[fmt] = []
        groups[fmt].append(float(getattr(rec, field)))

    result: Dict[str, FormatStats] = {}
    for fmt, values in groups.items():
        if values:
            result[fmt] = compute_stats(values, format_name=fmt, field=field)

    return result


def summary_table(
    stats_by_format: Dict[str, FormatStats],
) -> str:
    """
    Format a multi-format stats dict as a human-readable table string.

    :param stats_by_format: Dict from compute_stats_for_records().
    :return: Formatted table string.
    """
    if not stats_by_format:
        return "(no data)"

    header = (
        f"{'Format':<16} {'n':>4} {'Mean':>10} {'Median':>10} "
        f"{'P95':>10} {'Std':>10} {'CI95 Lo':>10} {'CI95 Hi':>10}"
    )
    sep    = "-" * len(header)
    rows   = [header, sep]
    for fmt in sorted(stats_by_format):
        s = stats_by_format[fmt]
        rows.append(
            f"{fmt:<16} {s.n:>4} {s.mean:>10.4f} {s.median:>10.4f} "
            f"{s.p95:>10.4f} {s.std:>10.4f} {s.ci95_lower:>10.4f} {s.ci95_upper:>10.4f}"
        )
    return "\n".join(rows)
