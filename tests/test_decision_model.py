"""
Unit tests for Stage 8: Statistical Analysis & Cost/Break-Even Modeling.

Tests cover:
  - statistics.py   : FormatStats, compute_stats, compute_stats_for_records
  - comparison.py   : FormatComparison, compare_formats, compare_two_formats
  - breakeven.py    : BreakEvenResult, all three formula functions
  - decision_model.py: Zone/Regime classification, make_decision, run_decision_framework
"""

import math
import pytest

from src.metrics.collector import MetricRecord

# ── Stage 8: Analysis modules ─────────────────────────────────────────────────
from src.analysis.statistics import (
    compute_stats,
    compute_stats_for_records,
    summary_table,
    FormatStats,
)
from src.analysis.comparison import (
    compare_formats,
    compare_two_formats,
    comparison_table,
    FormatComparison,
)
from src.analysis.breakeven import (
    compute_breakeven_json_vs_mp,
    compute_breakeven_json_vs_gzip,
    compute_breakeven_gzip_vs_mp,
    compute_all_breakevens,
    BreakEvenResult,
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


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures / helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_record(
    format_name: str = "json",
    t_ser_ms: float = 1.0,
    t_comp_ms: float = 0.0,
    t_net_ms: float = 10.0,
    t_decomp_ms: float = 0.0,
    t_deser_ms: float = 0.5,
    payload_size_bytes: int = 1000,
    json_baseline_bytes: int = 1000,
    valid: bool = True,
    run_index: int = 0,
    network_profile: str = "SLOW",
    workload_name: str = "flat_small_low",
    target_size_kb: float = 10.0,
    redundancy: str = "low",
) -> MetricRecord:
    """Create a MetricRecord with controlled field values for testing."""
    return MetricRecord(
        experiment_id="test_exp",
        workload_name=workload_name,
        data_structure="flat",
        target_size_kb=target_size_kb,
        redundancy=redundancy,
        network_profile=network_profile,
        format_name=format_name,
        run_index=run_index,
        seed=42,
        t_ser_ms=t_ser_ms,
        t_comp_ms=t_comp_ms,
        t_net_ms=t_net_ms,
        t_decomp_ms=t_decomp_ms,
        t_deser_ms=t_deser_ms,
        t_e2e_ms=t_ser_ms + t_comp_ms + t_net_ms + t_decomp_ms + t_deser_ms,
        t_processing_ms=t_ser_ms + t_comp_ms + t_decomp_ms + t_deser_ms,
        original_size_bytes=json_baseline_bytes,
        payload_size_bytes=payload_size_bytes,
        json_baseline_bytes=json_baseline_bytes,
        compression_ratio=payload_size_bytes / json_baseline_bytes if json_baseline_bytes > 0 else 1.0,
        payload_reduction_pct=(1.0 - payload_size_bytes / json_baseline_bytes) * 100 if json_baseline_bytes > 0 else 0.0,
        bytes_saved=max(0, json_baseline_bytes - payload_size_bytes),
        valid=valid,
    )


def _json_records(n: int = 5, **kwargs) -> list:
    """Generate n JSON records."""
    base = {"t_ser_ms": 0.5, "t_net_ms": 10.0, "t_deser_ms": 0.3, "payload_size_bytes": 1000, **kwargs}
    return [_make_record(format_name="json", run_index=i, **base) for i in range(n)]


def _gzip_records(n: int = 5, **kwargs) -> list:
    """Generate n GZIP records (smaller payload, more processing)."""
    base = {"t_ser_ms": 2.0, "t_net_ms": 5.0, "t_deser_ms": 1.5, "payload_size_bytes": 400, "json_baseline_bytes": 1000, **kwargs}
    return [_make_record(format_name="json_gzip", run_index=i, **base) for i in range(n)]


def _mp_records(n: int = 5, **kwargs) -> list:
    """Generate n MessagePack records (smaller payload, minimal overhead)."""
    base = {"t_ser_ms": 0.8, "t_net_ms": 8.0, "t_deser_ms": 0.4, "payload_size_bytes": 700, "json_baseline_bytes": 1000, **kwargs}
    return [_make_record(format_name="messagepack", run_index=i, **base) for i in range(n)]


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 8.1: compute_stats
# ─────────────────────────────────────────────────────────────────────────────

class TestComputeStats:
    def test_mean_correct(self):
        s = compute_stats([10.0, 20.0, 30.0], format_name="json", field="t_e2e_ms")
        assert s.mean == pytest.approx(20.0)

    def test_median_odd_n(self):
        s = compute_stats([1.0, 3.0, 5.0], format_name="json", field="x")
        assert s.median == pytest.approx(3.0)

    def test_median_even_n(self):
        s = compute_stats([1.0, 2.0, 3.0, 4.0], format_name="json", field="x")
        assert s.median == pytest.approx(2.5)

    def test_p95_five_values(self):
        # P95 of [1,2,3,4,5] → index = 0.95*(5-1) = 3.8 → 4 + 0.8*(5-4) = 4.8
        s = compute_stats([1.0, 2.0, 3.0, 4.0, 5.0], format_name="f", field="x")
        assert s.p95 == pytest.approx(4.8, abs=1e-6)

    def test_min_max(self):
        s = compute_stats([7.0, 2.0, 9.0, 1.0], format_name="f", field="x")
        assert s.min == pytest.approx(1.0)
        assert s.max == pytest.approx(9.0)

    def test_std_known(self):
        # [2, 4, 4, 4, 5, 5, 7, 9]: population std = 2.0; sample std (ddof=1) ≈ 2.138
        s = compute_stats([2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0], format_name="f", field="x")
        assert s.std == pytest.approx(2.138, abs=0.01)

    def test_variance_is_std_squared(self):
        s = compute_stats([1.0, 2.0, 3.0, 4.0, 5.0], format_name="f", field="x")
        assert s.variance == pytest.approx(s.std ** 2, abs=1e-10)

    def test_ci95_interval_contains_mean(self):
        s = compute_stats([10.0] * 10, format_name="f", field="x")
        assert s.ci95_lower <= s.mean <= s.ci95_upper

    def test_ci95_narrows_with_more_data(self):
        s_small = compute_stats([10.0, 11.0, 12.0], format_name="f", field="x")
        s_large = compute_stats([10.0, 11.0, 12.0] * 20, format_name="f", field="x")
        assert (s_small.ci95_upper - s_small.ci95_lower) > (s_large.ci95_upper - s_large.ci95_lower)

    def test_single_value_std_zero(self):
        s = compute_stats([5.0], format_name="f", field="x")
        assert s.std == pytest.approx(0.0)
        assert s.ci95_lower == pytest.approx(s.mean)
        assert s.ci95_upper == pytest.approx(s.mean)

    def test_n_reported_correctly(self):
        s = compute_stats([1.0, 2.0, 3.0], format_name="f", field="x")
        assert s.n == 3

    def test_format_name_and_field_stored(self):
        s = compute_stats([1.0], format_name="json", field="t_e2e_ms")
        assert s.format_name == "json"
        assert s.field == "t_e2e_ms"

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            compute_stats([], format_name="f", field="x")

    def test_to_dict_has_all_keys(self):
        s = compute_stats([1.0, 2.0, 3.0], format_name="json", field="t_e2e_ms")
        d = s.to_dict()
        for key in ("mean", "median", "p95", "min", "max", "std", "variance", "ci95_lower", "ci95_upper", "n"):
            assert key in d, f"Missing key: {key}"


class TestComputeStatsForRecords:
    def test_groups_by_format(self):
        records = _json_records(5) + _mp_records(5)
        result  = compute_stats_for_records(records, field="t_e2e_ms")
        assert "json" in result
        assert "messagepack" in result

    def test_excludes_invalid(self):
        records = _json_records(4) + [_make_record(format_name="json", valid=False)]
        result  = compute_stats_for_records(records, field="t_e2e_ms", valid_only=True)
        assert result["json"].n == 4

    def test_includes_invalid_when_flag_off(self):
        records = _json_records(3) + [_make_record(format_name="json", valid=False)]
        result  = compute_stats_for_records(records, field="t_e2e_ms", valid_only=False)
        assert result["json"].n == 4

    def test_field_payload_size(self):
        records = _json_records(3, payload_size_bytes=1000)
        result  = compute_stats_for_records(records, field="payload_size_bytes")
        assert result["json"].mean == pytest.approx(1000.0)

    def test_summary_table_nonempty(self):
        records = _json_records(3) + _mp_records(3)
        result  = compute_stats_for_records(records, field="t_e2e_ms")
        table   = summary_table(result)
        assert "json" in table
        assert "messagepack" in table


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 8.2: compare_formats
# ─────────────────────────────────────────────────────────────────────────────

class TestFormatComparison:
    """
    JSON baseline: t_ser=0.5, t_net=10.0, t_deser=0.3 → t_e2e=10.8, t_proc=0.8, payload=1000
    GZIP:          t_ser=2.0, t_net=5.0,  t_deser=1.5 → t_e2e=8.5,  t_proc=3.5, payload=400
    MP:            t_ser=0.8, t_net=8.0,  t_deser=0.4 → t_e2e=9.2,  t_proc=1.2, payload=700
    """

    def _make_mixed_records(self):
        return _json_records(5) + _gzip_records(5) + _mp_records(5)

    def test_returns_two_comparisons(self):
        records = self._make_mixed_records()
        result  = compare_formats(records)
        assert len(result) == 2
        formats = {c.format_name for c in result}
        assert "json_gzip" in formats
        assert "messagepack" in formats

    def test_baseline_is_json(self):
        records = self._make_mixed_records()
        result  = compare_formats(records)
        for c in result:
            assert c.baseline == "json"

    def test_gzip_network_time_saved_positive(self):
        """GZIP uses less network time than JSON (smaller payload)."""
        records = self._make_mixed_records()
        result  = {c.format_name: c for c in compare_formats(records)}
        assert result["json_gzip"].network_time_saved_ms == pytest.approx(10.0 - 5.0, abs=0.01)

    def test_gzip_compute_overhead_positive(self):
        """GZIP processing time > JSON processing time (compression cost)."""
        records = self._make_mixed_records()
        result  = {c.format_name: c for c in compare_formats(records)}
        # proc_gzip=3.5, proc_json=0.8 → overhead=2.7
        assert result["json_gzip"].compute_overhead_ms == pytest.approx(3.5 - 0.8, abs=0.01)

    def test_mp_relative_gain_positive(self):
        """MessagePack should have a positive gain vs JSON."""
        records = self._make_mixed_records()
        result  = {c.format_name: c for c in compare_formats(records)}
        assert result["messagepack"].relative_gain_pct > 0

    def test_gzip_relative_gain_formula(self):
        """Relative gain = (T_e2e,json - T_e2e,f) / T_e2e,json × 100."""
        records = self._make_mixed_records()
        result  = {c.format_name: c for c in compare_formats(records)}
        # json e2e = 0.5+10.0+0.3 = 10.8; gzip e2e = 2.0+5.0+1.5 = 8.5
        expected_gain = (10.8 - 8.5) / 10.8 * 100
        assert result["json_gzip"].relative_gain_pct == pytest.approx(expected_gain, abs=0.05)

    def test_payload_reduction_gzip(self):
        """GZIP payload is 60% smaller than JSON (400 vs 1000)."""
        records = self._make_mixed_records()
        result  = {c.format_name: c for c in compare_formats(records)}
        expected = (1000 - 400) / 1000 * 100  # 60%
        assert result["json_gzip"].payload_reduction_pct == pytest.approx(expected, abs=0.1)

    def test_no_baseline_records_returns_empty(self):
        records = _mp_records(5)   # no JSON records
        result  = compare_formats(records)
        assert result == []

    def test_to_dict_keys(self):
        records = self._make_mixed_records()
        comp    = compare_formats(records)[0]
        d       = comp.to_dict()
        for key in ("format_name", "baseline", "relative_gain_pct",
                    "network_time_saved_ms", "compute_overhead_ms",
                    "payload_reduction_pct"):
            assert key in d

    def test_compare_two_formats(self):
        records = self._make_mixed_records()
        comp = compare_two_formats(records, "json_gzip", "json")
        assert comp is not None
        assert comp.format_name == "json_gzip"
        assert comp.baseline    == "json"

    def test_compare_two_formats_missing_returns_none(self):
        records = _json_records(5)
        result  = compare_two_formats(records, "messagepack", "json")
        assert result is None

    def test_n_format_and_n_baseline_correct(self):
        records = _json_records(3) + _mp_records(7)
        result  = {c.format_name: c for c in compare_formats(records)}
        assert result["messagepack"].n_baseline == 3
        assert result["messagepack"].n_format   == 7

    def test_comparison_table_nonempty(self):
        records = self._make_mixed_records()
        comps   = compare_formats(records)
        table   = comparison_table(comps)
        assert "json_gzip" in table
        assert "messagepack" in table


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 8.3: Break-even analysis
# ─────────────────────────────────────────────────────────────────────────────

class TestBreakEvenJsonVsMp:
    """
    JSON: ser=0.5, deser=0.3, payload=1000
    MP:   ser=0.8, deser=0.4, payload=700

    size_diff  = 1000 - 700 = 300 bytes
    time_diff  = (0.8+0.4) - (0.5+0.3) = 1.2 - 0.8 = 0.4 ms
    B_BE [bps] = 300 / (0.0004 s) = 750_000 bytes/sec
    B_BE [Mbps]= 750_000 * 8 / 1_000_000 = 6.0 Mbps
    """

    def _records(self):
        return _json_records(10) + _mp_records(10)

    def test_is_valid(self):
        result = compute_breakeven_json_vs_mp(self._records())
        assert result.is_valid

    def test_pair_name(self):
        result = compute_breakeven_json_vs_mp(self._records())
        assert result.pair == "json_vs_messagepack"

    def test_bandwidth_bps_approx(self):
        result = compute_breakeven_json_vs_mp(self._records())
        # size_diff=300, time_diff=0.4ms → B_BE = 300/0.0004 = 750000 Bps
        assert result.bandwidth_be_bps == pytest.approx(750_000, rel=0.05)

    def test_bandwidth_mbps_approx(self):
        result = compute_breakeven_json_vs_mp(self._records())
        assert result.bandwidth_be_mbps == pytest.approx(6.0, rel=0.05)

    def test_size_diff_bytes(self):
        result = compute_breakeven_json_vs_mp(self._records())
        assert result.size_diff_bytes == pytest.approx(300.0, abs=1.0)

    def test_time_diff_ms(self):
        result = compute_breakeven_json_vs_mp(self._records())
        assert result.time_diff_ms == pytest.approx(0.4, abs=0.01)

    def test_no_json_records_invalid(self):
        result = compute_breakeven_json_vs_mp(_mp_records(5))
        assert not result.is_valid

    def test_no_mp_records_invalid(self):
        result = compute_breakeven_json_vs_mp(_json_records(5))
        assert not result.is_valid

    def test_to_dict_keys(self):
        result = compute_breakeven_json_vs_mp(self._records())
        d = result.to_dict()
        for key in ("pair", "bandwidth_be_bps", "bandwidth_be_mbps",
                    "size_diff_bytes", "time_diff_ms", "is_valid"):
            assert key in d


class TestBreakEvenJsonVsGzip:
    """
    JSON:  ser=0.5, deser=0.3, payload=1000
    GZIP:  ser=2.0 (=Tcomp), deser=1.5 (=Tdecomp), payload=400

    size_diff  = 1000 - 400 = 600 bytes
    time_diff  = Tcomp + Tdecomp = 2.0 + 1.5 = 3.5 ms
    B_BE [bps] = 600 / (0.0035 s) ≈ 171_428 bytes/sec ≈ 1.371 Mbps
    """

    def _records(self):
        return _json_records(10) + _gzip_records(10)

    def test_is_valid(self):
        result = compute_breakeven_json_vs_gzip(self._records())
        assert result.is_valid

    def test_pair_name(self):
        result = compute_breakeven_json_vs_gzip(self._records())
        assert result.pair == "json_vs_gzip"

    def test_bandwidth_bps_approx(self):
        result = compute_breakeven_json_vs_gzip(self._records())
        expected = 600 / 0.0035
        assert result.bandwidth_be_bps == pytest.approx(expected, rel=0.05)

    def test_bandwidth_mbps_approx(self):
        result = compute_breakeven_json_vs_gzip(self._records())
        expected_mbps = (600 / 0.0035) * 8 / 1_000_000
        assert result.bandwidth_be_mbps == pytest.approx(expected_mbps, rel=0.05)

    def test_size_diff_positive(self):
        result = compute_breakeven_json_vs_gzip(self._records())
        assert result.size_diff_bytes == pytest.approx(600.0, abs=1.0)

    def test_formula_label(self):
        result = compute_breakeven_json_vs_gzip(self._records())
        assert "Tcomp" in result.formula_used or "comp" in result.formula_used.lower()


class TestBreakEvenGzipVsMp:
    """
    JSON:  ser=0.5, deser=0.3
    GZIP:  ser=2.0 (Tcomp), deser=1.5 (Tdecomp), payload=400
    MP:    ser=0.8, deser=0.4, payload=700

    size_diff = 400 - 700 = -300  → MP is LARGER than GZIP → is_valid=False
    """

    def _records(self):
        return _json_records(10) + _gzip_records(10) + _mp_records(10)

    def test_pair_name(self):
        result = compute_breakeven_gzip_vs_mp(self._records())
        assert result.pair == "gzip_vs_messagepack"

    def test_returns_breakeven_result(self):
        result = compute_breakeven_gzip_vs_mp(self._records())
        assert isinstance(result, BreakEvenResult)

    def test_invalid_when_mp_larger_than_gzip(self):
        """GZIP(400B) vs MP(700B): MP payload > GZIP payload → size_diff < 0 → invalid."""
        result = compute_breakeven_gzip_vs_mp(self._records())
        # In our fixture GZIP=400B, MP=700B so GZIP < MP → MP is NOT smaller
        assert not result.is_valid  # size_diff = 400-700 = -300

    def test_valid_when_mp_smaller_than_gzip(self):
        """
        For B_BE (GZIP vs MP) to be valid:
          - size_diff = S_GZIP - S_MP > 0
          - time_diff = (Tser_MP + Tdeser_MP) - (Tser_JSON + Tcomp + Tdecomp + Tdeser_JSON) > 0

        Fixture:
          JSON:  ser=0.5, deser=0.3               → JSON baseline contribution = 0.8ms
          GZIP:  ser=0.2 (Tcomp), deser=0.1 (Tdecomp) → GZIP pipeline = 0.8+0.2+0.1 = 1.1ms
          MP:    ser=3.0, deser=2.0               → MP total = 5.0ms
          time_diff = 5.0 - 1.1 = 3.9ms > 0 ✓
          size:  GZIP=700B, MP=400B → size_diff = 300B > 0 ✓
        """
        json_recs = [_make_record(
            format_name="json", run_index=i,
            t_ser_ms=0.5, t_net_ms=5.0, t_deser_ms=0.3,
            payload_size_bytes=1000, json_baseline_bytes=1000,
        ) for i in range(5)]
        gzip_recs = [_make_record(
            format_name="json_gzip", run_index=i,
            t_ser_ms=0.2, t_net_ms=3.0, t_deser_ms=0.1,
            payload_size_bytes=700, json_baseline_bytes=1000,
        ) for i in range(5)]
        mp_recs = [_make_record(
            format_name="messagepack", run_index=i,
            t_ser_ms=3.0, t_net_ms=2.0, t_deser_ms=2.0,
            payload_size_bytes=400, json_baseline_bytes=1000,
        ) for i in range(5)]
        records = json_recs + gzip_recs + mp_recs
        result  = compute_breakeven_gzip_vs_mp(records)
        assert result.is_valid, f"Expected valid B_BE, got: {result.note}"
        assert result.size_diff_bytes == pytest.approx(300.0, abs=1.0)
        assert result.bandwidth_be_bps > 0


    def test_missing_format_is_invalid(self):
        result = compute_breakeven_gzip_vs_mp(_json_records(5))
        assert not result.is_valid


class TestComputeAllBreakevens:
    def test_returns_dict_with_three_keys(self):
        records = _json_records(5) + _gzip_records(5) + _mp_records(5)
        result  = compute_all_breakevens(records)
        assert "json_vs_messagepack" in result
        assert "json_vs_gzip"        in result
        assert "gzip_vs_messagepack" in result

    def test_all_are_breakeven_results(self):
        records = _json_records(5) + _gzip_records(5) + _mp_records(5)
        result  = compute_all_breakevens(records)
        for be in result.values():
            assert isinstance(be, BreakEvenResult)


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 8.4: Decision model
# ─────────────────────────────────────────────────────────────────────────────

THRESHOLDS = {"no_switch": 0.05, "switch": 0.20}


class TestClassifyZone:
    def test_below_no_switch_threshold(self):
        assert classify_zone(4.9, THRESHOLDS) == Zone.NO_SWITCH

    def test_exactly_at_no_switch_threshold(self):
        assert classify_zone(5.0, THRESHOLDS) == Zone.EVALUATE

    def test_in_evaluate_zone(self):
        assert classify_zone(12.5, THRESHOLDS) == Zone.EVALUATE

    def test_just_below_switch_threshold(self):
        assert classify_zone(19.9, THRESHOLDS) == Zone.EVALUATE

    def test_exactly_at_switch_threshold(self):
        assert classify_zone(20.0, THRESHOLDS) == Zone.SWITCH

    def test_above_switch_threshold(self):
        assert classify_zone(35.0, THRESHOLDS) == Zone.SWITCH

    def test_negative_gain_is_no_switch(self):
        assert classify_zone(-5.0, THRESHOLDS) == Zone.NO_SWITCH

    def test_custom_thresholds(self):
        thresholds = {"no_switch": 0.10, "switch": 0.30}
        assert classify_zone(9.9, thresholds)  == Zone.NO_SWITCH
        assert classify_zone(10.0, thresholds) == Zone.EVALUATE
        assert classify_zone(29.9, thresholds) == Zone.EVALUATE
        assert classify_zone(30.0, thresholds) == Zone.SWITCH


class TestClassifyRegime:
    def _comparison(self, net_saved: float, cpu_overhead: float) -> FormatComparison:
        return FormatComparison(
            format_name="json_gzip",
            baseline="json",
            n_format=5,
            n_baseline=5,
            network_time_saved_ms=net_saved,
            compute_overhead_ms=cpu_overhead,
            relative_gain_pct=10.0,
            payload_reduction_pct=50.0,
            mean_t_e2e_ms=5.0,
            mean_t_e2e_baseline_ms=10.0,
            mean_payload_bytes=500.0,
            mean_payload_baseline_bytes=1000.0,
        )

    def test_network_bound_when_net_dominates(self):
        comp = self._comparison(net_saved=10.0, cpu_overhead=1.0)
        assert classify_regime(comp) == Regime.NETWORK_BOUND

    def test_cpu_bound_when_cpu_dominates(self):
        comp = self._comparison(net_saved=1.0, cpu_overhead=10.0)
        assert classify_regime(comp) == Regime.CPU_BOUND

    def test_balanced_when_similar(self):
        comp = self._comparison(net_saved=5.0, cpu_overhead=4.0)
        assert classify_regime(comp) == Regime.BALANCED

    def test_network_bound_strictly_above_boundary(self):
        # net=2.1, cpu=1.0 → net > cpu*2 strictly → NETWORK_BOUND
        comp = self._comparison(net_saved=2.1, cpu_overhead=1.0)
        assert classify_regime(comp) == Regime.NETWORK_BOUND

    def test_cpu_bound_strictly_above_boundary(self):
        # net=1.0, cpu=2.1 → cpu > net*2 strictly → CPU_BOUND
        comp = self._comparison(net_saved=1.0, cpu_overhead=2.1)
        assert classify_regime(comp) == Regime.CPU_BOUND


class TestMakeDecision:
    def _comparison(
        self, gain: float, net_saved: float = 5.0, cpu_overhead: float = 1.0,
        payload_red: float = 30.0, fmt: str = "json_gzip"
    ) -> FormatComparison:
        return FormatComparison(
            format_name=fmt,
            baseline="json",
            n_format=5,
            n_baseline=5,
            network_time_saved_ms=net_saved,
            compute_overhead_ms=cpu_overhead,
            relative_gain_pct=gain,
            payload_reduction_pct=payload_red,
            mean_t_e2e_ms=5.0,
            mean_t_e2e_baseline_ms=10.0,
            mean_payload_bytes=700.0,
            mean_payload_baseline_bytes=1000.0,
        )

    def test_no_switch_zone(self):
        comp = self._comparison(gain=2.0, net_saved=0.5, cpu_overhead=0.2)
        result = make_decision(comp, THRESHOLDS)
        assert result.zone == Zone.NO_SWITCH
        assert "json" in result.recommendation.lower() or "stay" in result.recommendation.lower()

    def test_switch_zone(self):
        comp = self._comparison(gain=25.0)
        result = make_decision(comp, THRESHOLDS)
        assert result.zone == Zone.SWITCH
        assert "switch" in result.recommendation.lower() or result.format_name in result.recommendation

    def test_evaluate_network_bound(self):
        comp = self._comparison(gain=10.0, net_saved=10.0, cpu_overhead=0.5)
        result = make_decision(comp, THRESHOLDS)
        assert result.zone == Zone.EVALUATE
        assert result.regime == Regime.NETWORK_BOUND

    def test_evaluate_cpu_bound(self):
        comp = self._comparison(gain=10.0, net_saved=0.5, cpu_overhead=10.0)
        result = make_decision(comp, THRESHOLDS)
        assert result.zone == Zone.EVALUATE
        assert result.regime == Regime.CPU_BOUND

    def test_decision_result_fields_populated(self):
        comp   = self._comparison(gain=22.0)
        result = make_decision(comp, THRESHOLDS)
        assert isinstance(result, DecisionResult)
        assert result.format_name == "json_gzip"
        assert result.relative_gain_pct == pytest.approx(22.0)
        assert result.recommendation != ""
        assert result.reasoning != ""

    def test_to_dict_all_keys(self):
        comp   = self._comparison(gain=15.0)
        result = make_decision(comp, THRESHOLDS)
        d      = result.to_dict()
        for key in ("format_name", "zone", "regime", "relative_gain_pct",
                    "recommendation", "reasoning"):
            assert key in d

    def test_zone_enum_serialized_as_string(self):
        comp = self._comparison(gain=3.0)
        d    = make_decision(comp, THRESHOLDS).to_dict()
        assert d["zone"] == "no_switch"

    def test_regime_enum_serialized_as_string(self):
        comp = self._comparison(gain=25.0, net_saved=10.0, cpu_overhead=1.0)
        d    = make_decision(comp, THRESHOLDS).to_dict()
        assert d["regime"] in ("network_bound", "cpu_bound", "balanced")


class TestRunDecisionFramework:
    def _mixed_records(self):
        return _json_records(5) + _gzip_records(5) + _mp_records(5)

    def test_returns_two_decisions(self):
        records   = self._mixed_records()
        decisions = run_decision_framework(records, THRESHOLDS)
        assert len(decisions) == 2

    def test_format_names_correct(self):
        records   = self._mixed_records()
        decisions = run_decision_framework(records, THRESHOLDS)
        formats   = {d.format_name for d in decisions}
        assert "json_gzip" in formats
        assert "messagepack" in formats

    def test_each_result_has_valid_zone(self):
        records   = self._mixed_records()
        decisions = run_decision_framework(records, THRESHOLDS)
        for d in decisions:
            assert d.zone in (Zone.NO_SWITCH, Zone.EVALUATE, Zone.SWITCH)

    def test_each_result_has_valid_regime(self):
        records   = self._mixed_records()
        decisions = run_decision_framework(records, THRESHOLDS)
        for d in decisions:
            assert d.regime in (Regime.NETWORK_BOUND, Regime.CPU_BOUND, Regime.BALANCED)

    def test_empty_records_returns_empty(self):
        decisions = run_decision_framework([], THRESHOLDS)
        assert decisions == []

    def test_decision_table_nonempty(self):
        records   = self._mixed_records()
        decisions = run_decision_framework(records, THRESHOLDS)
        table     = decision_table(decisions)
        assert "json_gzip" in table
        assert "Zone" in table or "zone" in table.lower()

    def test_all_json_returns_empty(self):
        """Only JSON records → no other formats → no decisions."""
        records   = _json_records(10)
        decisions = run_decision_framework(records, THRESHOLDS)
        assert decisions == []
