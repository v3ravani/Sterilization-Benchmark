"""
Break-even analysis engine.

Computes the network bandwidth at which switching from JSON to a compressed
or binary format becomes beneficial, using the exact formulas from the PRD:

    JSON vs MessagePack:
        B_BE = (S_JSON - S_MP) / [(T_ser,MP + T_deser,MP) - (T_ser,JSON + T_deser,JSON)]

    JSON vs GZIP:
        B_BE = (S_JSON - S_GZIP) / (T_comp,GZIP + T_decomp,GZIP)
              where T_comp = t_ser,GZIP and T_decomp = t_deser,GZIP
              (since GZIP folds compress/decompress into ser/deser timing)

    GZIP vs MessagePack:
        B_BE = (S_GZIP - S_MP) / [(T_ser,MP + T_deser,MP) - (T_ser,JSON + T_comp + T_decomp + T_deser,JSON)]

    Payload Break-Even Size:
        The payload size (bytes) at which relative gain first reaches
        the "evaluate" threshold (5%). Estimated by linear interpolation
        from mean stats across available payload sizes.

Units:
    - Sizes are in bytes.
    - Times are in milliseconds (divided by 1000 to give seconds for Bps).
    - B_BE is returned in bytes/sec and Mbps for human readability.

Usage:
    result = compute_breakeven_json_vs_mp(json_stats, mp_stats)
    print(result.bandwidth_be_mbps)
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Dict, List, Optional


# ─────────────────────────────────────────────────────────────────────────────
# BreakEvenResult container
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class BreakEvenResult:
    """
    Result of a single break-even bandwidth computation.

    Attributes:
        pair:                 Description of the format pair (e.g. 'json_vs_messagepack').
        bandwidth_be_bps:     Break-even bandwidth in bytes per second.
                              Below this bandwidth the alternative format is faster.
                              None if not computable (e.g. negative denominator).
        bandwidth_be_mbps:    Break-even bandwidth in megabits per second (Mbps).
        payload_be_bytes:     Estimated payload break-even size in bytes.
                              None if cannot be estimated from available data.
        formula_used:         Human-readable label for which formula was applied.
        size_diff_bytes:      Numerator: size saved by switching (bytes).
        time_diff_ms:         Denominator: extra CPU time required (ms).
        is_valid:             True if B_BE could be computed and is positive.
        note:                 Optional explanatory note (e.g. why B_BE is None).
    """
    pair:               str
    bandwidth_be_bps:   Optional[float]
    bandwidth_be_mbps:  Optional[float]
    payload_be_bytes:   Optional[int]
    formula_used:       str
    size_diff_bytes:    float
    time_diff_ms:       float
    is_valid:           bool
    note:               str = ""

    def to_dict(self) -> dict:
        """Serialize to flat dictionary for CSV/JSON export."""
        return {
            "pair":              self.pair,
            "bandwidth_be_bps":  round(self.bandwidth_be_bps, 2) if self.bandwidth_be_bps is not None else None,
            "bandwidth_be_mbps": round(self.bandwidth_be_mbps, 4) if self.bandwidth_be_mbps is not None else None,
            "payload_be_bytes":  self.payload_be_bytes,
            "formula_used":      self.formula_used,
            "size_diff_bytes":   round(self.size_diff_bytes, 2),
            "time_diff_ms":      round(self.time_diff_ms, 6),
            "is_valid":          self.is_valid,
            "note":              self.note,
        }

    def __repr__(self) -> str:
        if self.bandwidth_be_mbps is not None:
            bw = f"{self.bandwidth_be_mbps:.3f} Mbps"
        else:
            bw = "N/A"
        return (
            f"BreakEvenResult({self.pair!r}: "
            f"B_BE={bw}, payload_BE={self.payload_be_bytes}B, "
            f"valid={self.is_valid})"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _safe_mean(values: List[float]) -> float:
    return statistics.mean(values) if values else 0.0


def _bps_to_mbps(bps: float) -> float:
    """Convert bytes/sec to megabits/sec."""
    return bps * 8 / 1_000_000


def _build_result(
    pair: str,
    formula: str,
    size_diff_bytes: float,
    time_diff_ms: float,
    payload_be_bytes: Optional[int] = None,
) -> BreakEvenResult:
    """
    Compute B_BE from size/time deltas and wrap in a BreakEvenResult.

    B_BE = size_diff_bytes / (time_diff_ms / 1000)  [bytes/sec]
         = size_diff_bytes * 1000 / time_diff_ms    [bytes/sec]
    """
    if time_diff_ms <= 0:
        return BreakEvenResult(
            pair=pair,
            bandwidth_be_bps=None,
            bandwidth_be_mbps=None,
            payload_be_bytes=payload_be_bytes,
            formula_used=formula,
            size_diff_bytes=size_diff_bytes,
            time_diff_ms=time_diff_ms,
            is_valid=False,
            note=(
                "Cannot compute B_BE: denominator <= 0 "
                f"(time_diff_ms={time_diff_ms:.6f}). "
                "This means the alternative format has no extra CPU cost — "
                "the format is strictly better in all network conditions."
            ),
        )

    if size_diff_bytes <= 0:
        return BreakEvenResult(
            pair=pair,
            bandwidth_be_bps=None,
            bandwidth_be_mbps=None,
            payload_be_bytes=payload_be_bytes,
            formula_used=formula,
            size_diff_bytes=size_diff_bytes,
            time_diff_ms=time_diff_ms,
            is_valid=False,
            note=(
                "Cannot compute B_BE: size_diff <= 0 "
                f"(size_diff_bytes={size_diff_bytes:.1f}). "
                "The alternative format does not reduce payload size — "
                "JSON has equal or smaller payload."
            ),
        )

    # B_BE [bytes/sec] = bytes_saved / (extra_cpu_time_sec)
    bps  = size_diff_bytes / (time_diff_ms / 1000.0)
    mbps = _bps_to_mbps(bps)

    return BreakEvenResult(
        pair=pair,
        bandwidth_be_bps=bps,
        bandwidth_be_mbps=mbps,
        payload_be_bytes=payload_be_bytes,
        formula_used=formula,
        size_diff_bytes=size_diff_bytes,
        time_diff_ms=time_diff_ms,
        is_valid=True,
    )


def _estimate_payload_breakeven(
    records_json,
    records_other,
    threshold_pct: float = 5.0,
) -> Optional[int]:
    """
    Estimate the payload size at which relative gain first exceeds the threshold.

    Uses mean t_e2e values across records grouped by payload_size_bytes.
    Returns None if insufficient data for interpolation.

    :param records_json:  Valid MetricRecord list for JSON baseline.
    :param records_other: Valid MetricRecord list for the compared format.
    :param threshold_pct: Relative-gain threshold (%) to find break-even at.
    :return: Payload size in bytes at break-even, or None.
    """
    if not records_json or not records_other:
        return None

    # Group by rough payload size bucket (JSON payload as reference)
    json_by_size: Dict[int, List[float]] = {}
    for r in records_json:
        sz = r.payload_size_bytes
        json_by_size.setdefault(sz, []).append(r.t_e2e_ms)

    other_by_size: Dict[int, List[float]] = {}
    for r in records_other:
        sz = r.json_baseline_bytes  # use JSON baseline for fair comparison
        other_by_size.setdefault(sz, []).append(r.t_e2e_ms)

    # Find common sizes and compute gain at each
    common_sizes = sorted(set(json_by_size) & set(other_by_size))
    if len(common_sizes) < 2:
        return None

    gains = []
    for sz in common_sizes:
        t_json  = _safe_mean(json_by_size[sz])
        t_other = _safe_mean(other_by_size[sz])
        if t_json > 0:
            gains.append((sz, (t_json - t_other) / t_json * 100.0))

    if not gains:
        return None

    # Find the first size where gain >= threshold
    for sz, gain in gains:
        if gain >= threshold_pct:
            return sz

    # If never reached, extrapolate (linear) if we have at least 2 points
    if len(gains) >= 2:
        x1, g1 = gains[-2]
        x2, g2 = gains[-1]
        if g2 != g1:
            # Linear interpolation: x at which g = threshold_pct
            slope = (x2 - x1) / (g2 - g1)
            x_be  = x1 + slope * (threshold_pct - g1)
            return max(0, int(x_be))

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Public formula-specific functions
# ─────────────────────────────────────────────────────────────────────────────

def compute_breakeven_json_vs_mp(
    records,                    # List[MetricRecord]
    json_name:  str = "json",
    mp_name:    str = "messagepack",
    threshold_pct: float = 5.0,
) -> BreakEvenResult:
    """
    Compute break-even bandwidth for JSON vs MessagePack.

    Formula:
        B_BE = (S_JSON - S_MP) / [(T_ser,MP + T_deser,MP) - (T_ser,JSON + T_deser,JSON)]

    :param records:       List of MetricRecord objects.
    :param json_name:     Name used for JSON serializer.
    :param mp_name:       Name used for MessagePack serializer.
    :param threshold_pct: Gain threshold for payload break-even (default 5%).
    :return: BreakEvenResult for the JSON vs MessagePack pair.
    """
    json_recs = [r for r in records if r.format_name == json_name and r.valid]
    mp_recs   = [r for r in records if r.format_name == mp_name   and r.valid]

    if not json_recs or not mp_recs:
        return BreakEvenResult(
            pair="json_vs_messagepack",
            bandwidth_be_bps=None,
            bandwidth_be_mbps=None,
            payload_be_bytes=None,
            formula_used="B_BE = (S_JSON - S_MP) / [(Tser_MP + Tdeser_MP) - (Tser_JSON + Tdeser_JSON)]",
            size_diff_bytes=0.0,
            time_diff_ms=0.0,
            is_valid=False,
            note="Insufficient records for one or both formats.",
        )

    s_json  = _safe_mean([r.payload_size_bytes for r in json_recs])
    s_mp    = _safe_mean([r.payload_size_bytes for r in mp_recs])
    size_diff = s_json - s_mp

    t_ser_json   = _safe_mean([r.t_ser_ms   for r in json_recs])
    t_deser_json = _safe_mean([r.t_deser_ms for r in json_recs])
    t_ser_mp     = _safe_mean([r.t_ser_ms   for r in mp_recs])
    t_deser_mp   = _safe_mean([r.t_deser_ms for r in mp_recs])

    time_diff = (t_ser_mp + t_deser_mp) - (t_ser_json + t_deser_json)
    payload_be = _estimate_payload_breakeven(json_recs, mp_recs, threshold_pct)

    return _build_result(
        pair="json_vs_messagepack",
        formula="B_BE = (S_JSON - S_MP) / [(Tser_MP + Tdeser_MP) - (Tser_JSON + Tdeser_JSON)]",
        size_diff_bytes=size_diff,
        time_diff_ms=time_diff,
        payload_be_bytes=payload_be,
    )


def compute_breakeven_json_vs_gzip(
    records,
    json_name:  str = "json",
    gzip_name:  str = "json_gzip",
    threshold_pct: float = 5.0,
) -> BreakEvenResult:
    """
    Compute break-even bandwidth for JSON vs GZIP+JSON.

    Formula:
        B_BE = (S_JSON - S_GZIP) / (T_comp,GZIP + T_decomp,GZIP)

    Note: since t_comp and t_decomp are folded into t_ser/t_deser for the
    GZIP serializer, we use t_ser,GZIP as T_comp and t_deser,GZIP as T_decomp.

    :param records:       List of MetricRecord objects.
    :param json_name:     Name used for JSON serializer.
    :param gzip_name:     Name used for GZIP serializer.
    :param threshold_pct: Gain threshold for payload break-even (default 5%).
    :return: BreakEvenResult for the JSON vs GZIP pair.
    """
    json_recs = [r for r in records if r.format_name == json_name  and r.valid]
    gzip_recs = [r for r in records if r.format_name == gzip_name  and r.valid]

    if not json_recs or not gzip_recs:
        return BreakEvenResult(
            pair="json_vs_gzip",
            bandwidth_be_bps=None,
            bandwidth_be_mbps=None,
            payload_be_bytes=None,
            formula_used="B_BE = (S_JSON - S_GZIP) / (Tcomp_GZIP + Tdecomp_GZIP)",
            size_diff_bytes=0.0,
            time_diff_ms=0.0,
            is_valid=False,
            note="Insufficient records for one or both formats.",
        )

    s_json  = _safe_mean([r.payload_size_bytes for r in json_recs])
    s_gzip  = _safe_mean([r.payload_size_bytes for r in gzip_recs])
    size_diff = s_json - s_gzip

    # T_comp,GZIP = t_ser,GZIP  (compression folded into serialization)
    # T_decomp,GZIP = t_deser,GZIP (decompression folded into deserialization)
    t_comp_gzip   = _safe_mean([r.t_ser_ms   for r in gzip_recs])
    t_decomp_gzip = _safe_mean([r.t_deser_ms for r in gzip_recs])
    time_diff = t_comp_gzip + t_decomp_gzip

    payload_be = _estimate_payload_breakeven(json_recs, gzip_recs, threshold_pct)

    return _build_result(
        pair="json_vs_gzip",
        formula="B_BE = (S_JSON - S_GZIP) / (Tcomp_GZIP + Tdecomp_GZIP)",
        size_diff_bytes=size_diff,
        time_diff_ms=time_diff,
        payload_be_bytes=payload_be,
    )


def compute_breakeven_gzip_vs_mp(
    records,
    json_name:  str = "json",
    gzip_name:  str = "json_gzip",
    mp_name:    str = "messagepack",
    threshold_pct: float = 5.0,
) -> BreakEvenResult:
    """
    Compute break-even bandwidth for GZIP vs MessagePack.

    Formula (from PRD):
        B_BE = (S_GZIP - S_MP) / [(T_ser,MP + T_deser,MP) - (T_ser,JSON + T_comp + T_decomp + T_deser,JSON)]

    where T_comp + T_decomp are the GZIP compression/decompression times
    (= t_ser,GZIP + t_deser,GZIP), and T_ser,JSON / T_deser,JSON are from
    the plain JSON baseline.

    :param records:       List of MetricRecord objects.
    :param json_name:     Name used for JSON serializer.
    :param gzip_name:     Name used for GZIP serializer.
    :param mp_name:       Name used for MessagePack serializer.
    :param threshold_pct: Gain threshold for payload break-even (default 5%).
    :return: BreakEvenResult for the GZIP vs MessagePack pair.
    """
    json_recs = [r for r in records if r.format_name == json_name  and r.valid]
    gzip_recs = [r for r in records if r.format_name == gzip_name  and r.valid]
    mp_recs   = [r for r in records if r.format_name == mp_name    and r.valid]

    if not json_recs or not gzip_recs or not mp_recs:
        return BreakEvenResult(
            pair="gzip_vs_messagepack",
            bandwidth_be_bps=None,
            bandwidth_be_mbps=None,
            payload_be_bytes=None,
            formula_used="B_BE = (S_GZIP - S_MP) / [(Tser_MP + Tdeser_MP) - (Tser_JSON + Tcomp + Tdecomp + Tdeser_JSON)]",
            size_diff_bytes=0.0,
            time_diff_ms=0.0,
            is_valid=False,
            note="Insufficient records for one or more formats.",
        )

    s_gzip = _safe_mean([r.payload_size_bytes for r in gzip_recs])
    s_mp   = _safe_mean([r.payload_size_bytes for r in mp_recs])
    size_diff = s_gzip - s_mp

    t_ser_json   = _safe_mean([r.t_ser_ms   for r in json_recs])
    t_deser_json = _safe_mean([r.t_deser_ms for r in json_recs])
    t_comp_gzip  = _safe_mean([r.t_ser_ms   for r in gzip_recs])   # compression
    t_decomp_gzip= _safe_mean([r.t_deser_ms for r in gzip_recs])   # decompression
    t_ser_mp     = _safe_mean([r.t_ser_ms   for r in mp_recs])
    t_deser_mp   = _safe_mean([r.t_deser_ms for r in mp_recs])

    # Denominator: (Tser_MP + Tdeser_MP) - (Tser_JSON + Tcomp + Tdecomp + Tdeser_JSON)
    gzip_total_cpu = t_ser_json + t_comp_gzip + t_decomp_gzip + t_deser_json
    mp_total_cpu   = t_ser_mp + t_deser_mp
    time_diff = mp_total_cpu - gzip_total_cpu

    payload_be = _estimate_payload_breakeven(gzip_recs, mp_recs, threshold_pct)

    return _build_result(
        pair="gzip_vs_messagepack",
        formula="B_BE = (S_GZIP - S_MP) / [(Tser_MP + Tdeser_MP) - (Tser_JSON + Tcomp + Tdecomp + Tdeser_JSON)]",
        size_diff_bytes=size_diff,
        time_diff_ms=time_diff,
        payload_be_bytes=payload_be,
    )


def compute_all_breakevens(
    records,
    json_name:  str = "json",
    gzip_name:  str = "json_gzip",
    mp_name:    str = "messagepack",
    threshold_pct: float = 5.0,
) -> Dict[str, BreakEvenResult]:
    """
    Compute all three break-even pairs and return as a named dict.

    :param records:       List of MetricRecord objects.
    :param json_name:     JSON format name.
    :param gzip_name:     GZIP format name.
    :param mp_name:       MessagePack format name.
    :param threshold_pct: Gain threshold for payload break-even.
    :return: Dict with keys 'json_vs_messagepack', 'json_vs_gzip', 'gzip_vs_messagepack'.
    """
    return {
        "json_vs_messagepack": compute_breakeven_json_vs_mp(
            records, json_name, mp_name, threshold_pct
        ),
        "json_vs_gzip": compute_breakeven_json_vs_gzip(
            records, json_name, gzip_name, threshold_pct
        ),
        "gzip_vs_messagepack": compute_breakeven_gzip_vs_mp(
            records, json_name, gzip_name, mp_name, threshold_pct
        ),
    }


def compute_breakeven(
    records,
    pair: str = "json_vs_messagepack",
    json_name: str = "json",
    gzip_name: str = "json_gzip",
    mp_name: str = "messagepack",
    threshold_pct: float = 5.0,
) -> BreakEvenResult:
    """
    Compute break-even for a specific pair name.

    :param records:       List of MetricRecord objects.
    :param pair:          One of 'json_vs_messagepack', 'json_vs_gzip', 'gzip_vs_messagepack'.
    :return: BreakEvenResult.
    """
    pair_normalized = pair.lower().replace("json_gzip", "gzip")
    if pair_normalized in ("json_vs_messagepack", "json_vs_mp"):
        return compute_breakeven_json_vs_mp(records, json_name, mp_name, threshold_pct)
    elif pair_normalized in ("json_vs_gzip",):
        return compute_breakeven_json_vs_gzip(records, json_name, gzip_name, threshold_pct)
    elif pair_normalized in ("gzip_vs_messagepack", "gzip_vs_mp"):
        return compute_breakeven_gzip_vs_mp(records, json_name, gzip_name, mp_name, threshold_pct)
    else:
        raise ValueError(f"Unknown break-even pair: {pair!r}")
