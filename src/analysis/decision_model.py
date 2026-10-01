"""
3-Zone Decision Framework for serialization format selection.

Classifies each format comparison into one of three decision zones:

    Zone 1 — No Switch (Relative Gain < 5%):
        End-to-end latency improvement is negligible. JSON's universality
        and zero CPU overhead make it the optimal choice.

    Zone 2 — Evaluate (5% ≤ Gain < 20%):
        Marginal improvement. Decision depends on the workload regime:
        - Network-bound: consider switching (bandwidth savings dominate).
        - CPU-bound: stay with JSON (processing overhead negates network gain).

    Zone 3 — Switch (Gain ≥ 20%):
        Significant latency improvement. Recommended format switch.

Regime classification:
    Network-bound:  |network_time_saved| > |compute_overhead| × 2
    CPU-bound:      |compute_overhead|   > |network_time_saved| × 2
    Balanced:       neither condition holds

Usage:
    decisions = run_decision_framework(records, thresholds={"no_switch": 0.05, "switch": 0.20})
    for d in decisions:
        print(d.recommendation)
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Dict, List

from src.analysis.comparison import FormatComparison, compare_formats


# ─────────────────────────────────────────────────────────────────────────────
# Enumerations
# ─────────────────────────────────────────────────────────────────────────────

class Zone(enum.Enum):
    """
    Decision zone classification based on relative end-to-end latency gain.

    NO_SWITCH: Gain < 5%  — stay with JSON.
    EVALUATE:  5% ≤ Gain < 20% — context-dependent decision.
    SWITCH:    Gain ≥ 20% — recommended format switch.
    """
    NO_SWITCH = "no_switch"
    EVALUATE  = "evaluate"
    SWITCH    = "switch"


class Regime(enum.Enum):
    """
    Workload performance regime classification.

    NETWORK_BOUND: Payload size savings dominate — bandwidth-sensitive workloads.
    CPU_BOUND:     Serialization/compression overhead dominates — compute-sensitive.
    BALANCED:      Neither network nor CPU is the dominant factor.
    """
    NETWORK_BOUND = "network_bound"
    CPU_BOUND     = "cpu_bound"
    BALANCED      = "balanced"


# ─────────────────────────────────────────────────────────────────────────────
# DecisionResult container
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DecisionResult:
    """
    Full decision output for one format comparison.

    Attributes:
        format_name:       The evaluated format (vs JSON baseline).
        zone:              Decision zone (NO_SWITCH / EVALUATE / SWITCH).
        regime:            Workload regime (NETWORK_BOUND / CPU_BOUND / BALANCED).
        relative_gain_pct: End-to-end latency gain over JSON (%).
        network_time_saved_ms: Network transmission time saved (ms).
        compute_overhead_ms:   Extra CPU processing time (ms).
        payload_reduction_pct: Payload size reduction (%).
        recommendation:    One-line action recommendation.
        reasoning:         Multi-sentence reasoning behind the decision.
    """
    format_name:            str
    zone:                   Zone
    regime:                 Regime
    relative_gain_pct:      float
    network_time_saved_ms:  float
    compute_overhead_ms:    float
    payload_reduction_pct:  float
    recommendation:         str
    reasoning:              str

    def to_dict(self) -> dict:
        """Serialize to flat dictionary for CSV/JSON export."""
        return {
            "format_name":           self.format_name,
            "zone":                  self.zone.value,
            "regime":                self.regime.value,
            "relative_gain_pct":     round(self.relative_gain_pct, 4),
            "network_time_saved_ms": round(self.network_time_saved_ms, 6),
            "compute_overhead_ms":   round(self.compute_overhead_ms, 6),
            "payload_reduction_pct": round(self.payload_reduction_pct, 4),
            "recommendation":        self.recommendation,
            "reasoning":             self.reasoning,
        }

    def __repr__(self) -> str:
        return (
            f"DecisionResult({self.format_name!r}: "
            f"zone={self.zone.value}, regime={self.regime.value}, "
            f"gain={self.relative_gain_pct:+.2f}%)"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Classification functions
# ─────────────────────────────────────────────────────────────────────────────

def classify_zone(
    relative_gain_pct: float,
    thresholds: Dict[str, float],
) -> Zone:
    """
    Classify a relative gain percentage into a decision zone.

    :param relative_gain_pct: (T_e2e,JSON - T_e2e,f) / T_e2e,JSON × 100.
    :param thresholds:        Dict with 'no_switch' (fraction) and 'switch' (fraction).
                              e.g. {"no_switch": 0.05, "switch": 0.20}
    :return: Zone enum value.
    """
    if thresholds is None:
        thresholds = {"no_switch": 0.05, "switch": 0.20}

    no_switch_pct = thresholds.get("no_switch", 0.05) * 100.0
    switch_pct    = thresholds.get("switch",    0.20) * 100.0

    if relative_gain_pct < no_switch_pct:
        return Zone.NO_SWITCH
    elif relative_gain_pct < switch_pct:
        return Zone.EVALUATE
    else:
        return Zone.SWITCH


def classify_regime(comparison: FormatComparison) -> Regime:
    """
    Classify a comparison as network-bound, CPU-bound, or balanced.

    Rules:
        NETWORK_BOUND: |net_saved| > |cpu_overhead| × 2
        CPU_BOUND:     |cpu_overhead| > |net_saved| × 2
        BALANCED:      otherwise

    :param comparison: FormatComparison from compare_formats().
    :return: Regime enum value.
    """
    net  = abs(comparison.network_time_saved_ms)
    cpu  = abs(comparison.compute_overhead_ms)

    if net > cpu * 2.0:
        return Regime.NETWORK_BOUND
    elif cpu > net * 2.0:
        return Regime.CPU_BOUND
    else:
        return Regime.BALANCED


def _build_recommendation(
    fmt: str,
    zone: Zone,
    regime: Regime,
    gain_pct: float,
    net_saved_ms: float,
    cpu_overhead_ms: float,
    payload_red_pct: float,
) -> tuple[str, str]:
    """
    Build the recommendation text and reasoning for a given decision.

    :return: Tuple of (recommendation, reasoning).
    """
    if zone == Zone.NO_SWITCH:
        rec = f"Stay with JSON. {fmt!r} offers <5% gain ({gain_pct:+.2f}%)."
        reasoning = (
            f"The end-to-end latency improvement of {gain_pct:.2f}% is below the 5% "
            f"significance threshold. JSON's broad compatibility, zero extra CPU cost, "
            f"and negligible payload difference make it the optimal choice for this workload. "
            f"Network time saved: {net_saved_ms:+.3f}ms; CPU overhead: {cpu_overhead_ms:+.3f}ms; "
            f"Payload reduction: {payload_red_pct:.2f}%."
        )

    elif zone == Zone.EVALUATE:
        if regime == Regime.NETWORK_BOUND:
            rec = (
                f"Consider switching to {fmt!r}. "
                f"Network-bound workload gains {gain_pct:+.2f}% — evaluate bandwidth cost."
            )
            reasoning = (
                f"The {gain_pct:.2f}% latency gain is in the evaluate zone (5–20%) and the "
                f"workload is network-bound (net_saved={net_saved_ms:+.3f}ms >> "
                f"cpu_overhead={cpu_overhead_ms:+.3f}ms). Switching to {fmt!r} is "
                f"likely beneficial in bandwidth-constrained environments. "
                f"Verify that the extra CPU overhead ({cpu_overhead_ms:+.3f}ms) is "
                f"acceptable for your throughput targets."
            )
        elif regime == Regime.CPU_BOUND:
            rec = (
                f"Stay with JSON. CPU overhead of {fmt!r} negates network savings "
                f"({gain_pct:+.2f}% gain, CPU-bound regime)."
            )
            reasoning = (
                f"Although {fmt!r} saves {net_saved_ms:+.3f}ms in network time, the "
                f"CPU overhead ({cpu_overhead_ms:+.3f}ms) dominates, resulting in a "
                f"marginal {gain_pct:.2f}% e2e gain. For CPU-bound workloads the extra "
                f"serialization cost erodes bandwidth savings. JSON is preferred unless "
                f"network bandwidth is severely constrained."
            )
        else:  # BALANCED
            rec = (
                f"Evaluate {fmt!r} for your environment: "
                f"{gain_pct:+.2f}% gain, balanced network/CPU trade-off."
            )
            reasoning = (
                f"{fmt!r} delivers a {gain_pct:.2f}% latency gain (evaluate zone) with "
                f"balanced network ({net_saved_ms:+.3f}ms) and CPU ({cpu_overhead_ms:+.3f}ms) "
                f"trade-offs. Switching is worthwhile if payload bandwidth cost dominates "
                f"your operational profile (e.g. high-volume, low-latency APIs). "
                f"Payload reduction: {payload_red_pct:.2f}%."
            )

    else:  # Zone.SWITCH
        rec = (
            f"Switch to {fmt!r}. {gain_pct:+.2f}% e2e gain "
            f"with {payload_red_pct:.2f}% smaller payloads."
        )
        reasoning = (
            f"{fmt!r} achieves a {gain_pct:.2f}% end-to-end latency improvement (≥20% "
            f"switch threshold), driven by {payload_red_pct:.2f}% smaller payloads and "
            f"{net_saved_ms:+.3f}ms network time savings. Regime: {regime.value}. "
            f"Additional CPU overhead ({cpu_overhead_ms:+.3f}ms) is outweighed by "
            f"the network gains at this payload size and network profile."
        )

    return rec, reasoning


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def make_decision(
    comparison: FormatComparison,
    thresholds: Dict[str, float],
) -> DecisionResult:
    """
    Apply the 3-zone decision framework to a single FormatComparison.

    :param comparison: FormatComparison from compare_formats().
    :param thresholds: Dict with 'no_switch' and 'switch' fraction keys.
    :return: DecisionResult with zone, regime, recommendation, and reasoning.
    """
    zone   = classify_zone(comparison.relative_gain_pct, thresholds)
    regime = classify_regime(comparison)

    rec, reasoning = _build_recommendation(
        fmt             = comparison.format_name,
        zone            = zone,
        regime          = regime,
        gain_pct        = comparison.relative_gain_pct,
        net_saved_ms    = comparison.network_time_saved_ms,
        cpu_overhead_ms = comparison.compute_overhead_ms,
        payload_red_pct = comparison.payload_reduction_pct,
    )

    return DecisionResult(
        format_name            = comparison.format_name,
        zone                   = zone,
        regime                 = regime,
        relative_gain_pct      = comparison.relative_gain_pct,
        network_time_saved_ms  = comparison.network_time_saved_ms,
        compute_overhead_ms    = comparison.compute_overhead_ms,
        payload_reduction_pct  = comparison.payload_reduction_pct,
        recommendation         = rec,
        reasoning              = reasoning,
    )


def run_decision_framework(
    records,                         # List[MetricRecord]
    thresholds: Dict[str, float],
    baseline: str = "json",
) -> List[DecisionResult]:
    """
    Run the full 3-zone decision framework over a set of benchmark records.

    :param records:    List of MetricRecord objects from the benchmark runner.
    :param thresholds: Dict with 'no_switch' (fraction) and 'switch' (fraction).
    :param baseline:   Baseline format name (default 'json').
    :return:           List of DecisionResult, one per non-baseline format.
    """
    comparisons = compare_formats(records, baseline=baseline)
    decisions   = [make_decision(c, thresholds) for c in comparisons]
    return decisions


def decision_table(decisions: List[DecisionResult]) -> str:
    """
    Format a list of DecisionResult objects as a human-readable table.

    :param decisions: Output from run_decision_framework().
    :return: Formatted table string.
    """
    if not decisions:
        return "(no decisions)"

    header = (
        f"{'Format':<16} {'Zone':<12} {'Regime':<16} "
        f"{'Gain%':>8} {'NetSaved':>10} {'CPUOver':>10}"
    )
    sep  = "-" * len(header)
    rows = [header, sep]
    for d in decisions:
        rows.append(
            f"{d.format_name:<16} {d.zone.value:<12} {d.regime.value:<16} "
            f"{d.relative_gain_pct:>+8.2f} {d.network_time_saved_ms:>+10.3f} "
            f"{d.compute_overhead_ms:>+10.3f}"
        )
    rows.append(sep)
    for d in decisions:
        rows.append(f"  -> {d.format_name}: {d.recommendation}")
    return "\n".join(rows)
