"""
Pairwise format comparison module.

Computes head-to-head metrics between each non-JSON serializer and the
JSON baseline for a set of MetricRecord observations:

    Network Time Saved:
        N_f = T_net,JSON - T_net,f          (positive = format is faster)

    Computational Overhead:
        O_f = ProcessingTime_f - ProcessingTime_JSON
              where ProcessingTime = t_ser + t_comp + t_decomp + t_deser
              (positive = format is more expensive than JSON)

    Relative Gain:
        RelGain% = (T_e2e,JSON - T_e2e,f) / T_e2e,JSON × 100
                   (positive = format has lower end-to-end latency than JSON)

    Payload Reduction:
        PayloadReduction% = (S_JSON - S_f) / S_JSON × 100
                            (positive = format has smaller payload than JSON)

Usage:
    comparisons = compare_formats(records)
    for c in comparisons:
        print(c)
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Dict, List, Optional


# ─────────────────────────────────────────────────────────────────────────────
# FormatComparison result container
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class FormatComparison:
    """
    Pairwise comparison between one format and the JSON baseline.

    All values are averages across valid observations.

    Attributes:
        format_name:              The non-baseline format being evaluated.
        baseline:                 Baseline format name (always 'json').
        n_format:                 Number of valid observations for this format.
        n_baseline:               Number of valid baseline observations.
        network_time_saved_ms:    N_f = T_net,baseline - T_net,f  (ms).
        compute_overhead_ms:      O_f = ProcessingTime_f - ProcessingTime_baseline (ms).
        relative_gain_pct:        (T_e2e,baseline - T_e2e,f) / T_e2e,baseline × 100.
        payload_reduction_pct:    (S_baseline - S_f) / S_baseline × 100.
        mean_t_e2e_ms:            Mean end-to-end latency for this format (ms).
        mean_t_e2e_baseline_ms:   Mean end-to-end latency for baseline (ms).
        mean_payload_bytes:       Mean payload size for this format (bytes).
        mean_payload_baseline_bytes: Mean payload size for baseline (bytes).
    """
    format_name:               str
    baseline:                  str
    n_format:                  int
    n_baseline:                int
    network_time_saved_ms:     float
    compute_overhead_ms:       float
    relative_gain_pct:         float
    payload_reduction_pct:     float
    mean_t_e2e_ms:             float
    mean_t_e2e_baseline_ms:    float
    mean_payload_bytes:        float
    mean_payload_baseline_bytes: float

    def to_dict(self) -> dict:
        """Serialize to flat dictionary for CSV/JSON export."""
        return {
            "format_name":                  self.format_name,
            "baseline":                     self.baseline,
            "n_format":                     self.n_format,
            "n_baseline":                   self.n_baseline,
            "network_time_saved_ms":        round(self.network_time_saved_ms, 6),
            "compute_overhead_ms":          round(self.compute_overhead_ms, 6),
            "relative_gain_pct":            round(self.relative_gain_pct, 4),
            "payload_reduction_pct":        round(self.payload_reduction_pct, 4),
            "mean_t_e2e_ms":                round(self.mean_t_e2e_ms, 6),
            "mean_t_e2e_baseline_ms":       round(self.mean_t_e2e_baseline_ms, 6),
            "mean_payload_bytes":           round(self.mean_payload_bytes, 2),
            "mean_payload_baseline_bytes":  round(self.mean_payload_baseline_bytes, 2),
        }

    def __repr__(self) -> str:
        return (
            f"FormatComparison({self.format_name!r} vs {self.baseline!r}: "
            f"gain={self.relative_gain_pct:+.2f}%, "
            f"net_saved={self.network_time_saved_ms:+.3f}ms, "
            f"cpu_overhead={self.compute_overhead_ms:+.3f}ms, "
            f"payload_reduction={self.payload_reduction_pct:+.2f}%)"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _safe_mean(values: List[float]) -> float:
    """Return arithmetic mean of values, or 0.0 if list is empty."""
    return statistics.mean(values) if values else 0.0


def _extract_valid(records, format_name: str) -> list:
    """Return valid MetricRecord objects for a given format."""
    return [r for r in records if r.format_name == format_name and r.valid]


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def compare_formats(
    records,                      # List[MetricRecord]
    baseline: str = "json",
) -> List[FormatComparison]:
    """
    Compute pairwise comparisons between each non-baseline format and the baseline.

    :param records:  List of MetricRecord objects (from MetricsCollector or loaded CSV).
    :param baseline: Name of the baseline serializer (default: 'json').
    :return:         List of FormatComparison, one per non-baseline format found.
    """
    # Gather baseline statistics
    baseline_recs = _extract_valid(records, baseline)
    if not baseline_recs:
        return []

    t_net_baseline   = _safe_mean([r.t_net_ms        for r in baseline_recs])
    t_proc_baseline  = _safe_mean([r.t_processing_ms for r in baseline_recs])
    t_e2e_baseline   = _safe_mean([r.t_e2e_ms        for r in baseline_recs])
    payload_baseline = _safe_mean([r.payload_size_bytes for r in baseline_recs])

    # Identify all non-baseline formats present in the records
    all_formats = {r.format_name for r in records if r.valid}
    other_formats = sorted(all_formats - {baseline})

    comparisons: List[FormatComparison] = []
    for fmt in other_formats:
        fmt_recs = _extract_valid(records, fmt)
        if not fmt_recs:
            continue

        t_net_fmt    = _safe_mean([r.t_net_ms           for r in fmt_recs])
        t_proc_fmt   = _safe_mean([r.t_processing_ms    for r in fmt_recs])
        t_e2e_fmt    = _safe_mean([r.t_e2e_ms           for r in fmt_recs])
        payload_fmt  = _safe_mean([r.payload_size_bytes  for r in fmt_recs])

        # N_f: network time saved (positive = format uses less network time)
        network_time_saved_ms = t_net_baseline - t_net_fmt

        # O_f: compute overhead (positive = format is more CPU-expensive)
        compute_overhead_ms = t_proc_fmt - t_proc_baseline

        # Relative gain: (T_e2e,baseline - T_e2e,f) / T_e2e,baseline × 100
        if t_e2e_baseline > 0:
            relative_gain_pct = (t_e2e_baseline - t_e2e_fmt) / t_e2e_baseline * 100.0
        else:
            relative_gain_pct = 0.0

        # Payload reduction %
        if payload_baseline > 0:
            payload_reduction_pct = (payload_baseline - payload_fmt) / payload_baseline * 100.0
        else:
            payload_reduction_pct = 0.0

        comparisons.append(FormatComparison(
            format_name=fmt,
            baseline=baseline,
            n_format=len(fmt_recs),
            n_baseline=len(baseline_recs),
            network_time_saved_ms=network_time_saved_ms,
            compute_overhead_ms=compute_overhead_ms,
            relative_gain_pct=relative_gain_pct,
            payload_reduction_pct=payload_reduction_pct,
            mean_t_e2e_ms=t_e2e_fmt,
            mean_t_e2e_baseline_ms=t_e2e_baseline,
            mean_payload_bytes=payload_fmt,
            mean_payload_baseline_bytes=payload_baseline,
        ))

    return comparisons


def comparison_table(comparisons: List[FormatComparison]) -> str:
    """
    Format a list of FormatComparison objects as a human-readable table.

    :param comparisons: Output from compare_formats().
    :return: Formatted table string.
    """
    if not comparisons:
        return "(no comparisons)"

    header = (
        f"{'Format':<16} {'vs':<8} {'NetSaved(ms)':>14} "
        f"{'CPUOverhead(ms)':>16} {'Gain%':>8} {'PayloadRed%':>12}"
    )
    sep = "-" * len(header)
    rows = [header, sep]
    for c in comparisons:
        rows.append(
            f"{c.format_name:<16} {c.baseline:<8} {c.network_time_saved_ms:>+14.4f} "
            f"{c.compute_overhead_ms:>+16.4f} {c.relative_gain_pct:>+8.2f} "
            f"{c.payload_reduction_pct:>+12.2f}"
        )
    return "\n".join(rows)


def compare_two_formats(
    records,
    format_a: str,
    format_b: str,
) -> Optional[FormatComparison]:
    """
    Compare format_a against format_b as the baseline.

    Convenience wrapper around compare_formats() for arbitrary pairs.

    :param records:   List of MetricRecord objects.
    :param format_a:  Format to evaluate.
    :param format_b:  Baseline format.
    :return:          FormatComparison for format_a vs format_b, or None if insufficient data.
    """
    results = compare_formats(records, baseline=format_b)
    for c in results:
        if c.format_name == format_a:
            return c
    return None
