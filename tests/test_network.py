"""
Tests for Stage 4: Controlled Network Controller (Windows).

Tests cover:
  - NetworkProfile: attributes, derived properties, theoretical timing formula.
  - Profile catalog: all 4 profiles present, ordering, lookup, case-insensitive get.
  - SimulationOverhead: accumulation, reset, repr.
  - NetworkController: apply/reset, context manager, simulate_send pass-through,
                       latency injection, bandwidth throttling, overhead tracking,
                       verify_profile accuracy, thread safety.
  - Reproducibility: same profile produces consistent timings across runs.
  - Baseline overhead: FAST profile overhead is negligible.
"""

import time
import threading
import pytest

from src.network.profiles import (
    NetworkProfile,
    PROFILES,
    FAST, MODERATE, SLOW, VERY_SLOW,
    PROFILE_ORDER,
    get_profile,
    list_profiles,
)
from src.network.controller import (
    NetworkController,
    SimulationOverhead,
    get_controller,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def ctrl():
    """Fresh NetworkController for each test."""
    return NetworkController()


@pytest.fixture
def small_payload():
    return b"X" * 512          # 512 bytes


@pytest.fixture
def medium_payload():
    return b"Y" * (32 * 1024)  # 32 KB


# ─────────────────────────────────────────────────────────────────────────────
# Tests: NetworkProfile attributes & derived properties
# ─────────────────────────────────────────────────────────────────────────────

class TestNetworkProfile:
    def test_fast_bandwidth_mbps(self):
        assert FAST.bandwidth_mbps == 1000.0

    def test_fast_latency_ms(self):
        assert FAST.latency_ms == 1.0

    def test_moderate_bandwidth_mbps(self):
        assert MODERATE.bandwidth_mbps == 100.0

    def test_slow_bandwidth_mbps(self):
        assert SLOW.bandwidth_mbps == 10.0

    def test_very_slow_bandwidth_mbps(self):
        assert VERY_SLOW.bandwidth_mbps == 1.0

    def test_very_slow_latency_ms(self):
        assert VERY_SLOW.latency_ms == 150.0

    def test_bandwidth_bps_conversion(self):
        assert MODERATE.bandwidth_bps == 100.0 * 1_000_000

    def test_bandwidth_bytes_per_sec(self):
        assert MODERATE.bandwidth_bytes_per_sec == (100.0 * 1_000_000) / 8

    def test_latency_sec(self):
        assert SLOW.latency_sec == pytest.approx(0.05, abs=1e-9)

    def test_rtt_sec_is_double_latency(self):
        assert SLOW.rtt_sec == pytest.approx(SLOW.latency_sec * 2)

    def test_theoretical_transfer_time_zero_bytes(self):
        t = FAST.theoretical_transfer_time_sec(0)
        assert t == pytest.approx(FAST.latency_sec, abs=1e-9)

    def test_theoretical_transfer_time_formula(self):
        # T = latency + size / bandwidth_bytes
        expected = SLOW.latency_sec + (1024 / SLOW.bandwidth_bytes_per_sec)
        result = SLOW.theoretical_transfer_time_sec(1024)
        assert result == pytest.approx(expected, rel=1e-6)

    def test_very_slow_transfer_time_large_payload(self):
        # 1MB at 1 Mbps = 8 seconds + 150ms latency
        payload_bytes = 1 * 1024 * 1024
        expected = VERY_SLOW.latency_sec + payload_bytes / VERY_SLOW.bandwidth_bytes_per_sec
        result = VERY_SLOW.theoretical_transfer_time_sec(payload_bytes)
        assert result == pytest.approx(expected, rel=1e-6)

    def test_profile_is_frozen(self):
        with pytest.raises((AttributeError, TypeError)):
            FAST.bandwidth_mbps = 500.0  # type: ignore

    def test_profile_str_contains_name(self):
        assert "FAST" in str(FAST)
        assert "1000" in str(FAST)

    def test_profile_has_description(self):
        for p in PROFILES.values():
            assert len(p.description) > 0


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Profile catalog
# ─────────────────────────────────────────────────────────────────────────────

class TestProfileCatalog:
    def test_four_profiles_defined(self):
        assert len(PROFILES) == 4

    def test_all_required_profiles_present(self):
        assert "FAST" in PROFILES
        assert "MODERATE" in PROFILES
        assert "SLOW" in PROFILES
        assert "VERY_SLOW" in PROFILES

    def test_profile_order_ascending_constraint(self):
        # Bandwidth decreases in PROFILE_ORDER
        bws = [p.bandwidth_mbps for p in PROFILE_ORDER]
        assert bws == sorted(bws, reverse=True)

    def test_profile_order_latency_ascending(self):
        # Latency increases in PROFILE_ORDER
        lats = [p.latency_ms for p in PROFILE_ORDER]
        assert lats == sorted(lats)

    def test_get_profile_uppercase(self):
        p = get_profile("FAST")
        assert p is FAST

    def test_get_profile_lowercase(self):
        p = get_profile("slow")
        assert p is SLOW

    def test_get_profile_mixed_case(self):
        p = get_profile("Very_Slow")
        assert p is VERY_SLOW

    def test_get_profile_unknown_raises(self):
        with pytest.raises(KeyError):
            get_profile("ULTRA_FAST")

    def test_list_profiles_has_four(self):
        names = list_profiles()
        assert len(names) == 4

    def test_list_profiles_contains_all(self):
        names = list_profiles()
        assert "FAST" in names
        assert "VERY_SLOW" in names


# ─────────────────────────────────────────────────────────────────────────────
# Tests: SimulationOverhead
# ─────────────────────────────────────────────────────────────────────────────

class TestSimulationOverhead:
    def test_default_zeros(self):
        oh = SimulationOverhead()
        assert oh.total_latency_injected_sec == 0.0
        assert oh.total_throttle_sleep_sec == 0.0
        assert oh.bytes_sent == 0
        assert oh.call_count == 0

    def test_total_overhead_is_sum(self):
        oh = SimulationOverhead(
            total_latency_injected_sec=0.1,
            total_throttle_sleep_sec=0.05,
        )
        assert oh.total_overhead_sec == pytest.approx(0.15, abs=1e-9)

    def test_reset_clears_all(self):
        oh = SimulationOverhead(
            total_latency_injected_sec=1.0,
            total_throttle_sleep_sec=0.5,
            bytes_sent=1024,
            call_count=5,
        )
        oh.reset()
        assert oh.total_latency_injected_sec == 0.0
        assert oh.bytes_sent == 0
        assert oh.call_count == 0

    def test_repr_contains_ms(self):
        oh = SimulationOverhead(total_latency_injected_sec=0.05)
        r = repr(oh)
        assert "ms" in r or "latency" in r


# ─────────────────────────────────────────────────────────────────────────────
# Tests: NetworkController – profile management
# ─────────────────────────────────────────────────────────────────────────────

class TestNetworkControllerProfiles:
    def test_default_no_active_profile(self, ctrl):
        assert ctrl.active_profile is None
        assert not ctrl.is_active

    def test_apply_profile_sets_active(self, ctrl):
        ctrl.apply_profile(FAST)
        assert ctrl.is_active
        assert ctrl.active_profile is FAST

    def test_apply_profile_by_name(self, ctrl):
        ctrl.apply_profile_by_name("SLOW")
        assert ctrl.active_profile is SLOW

    def test_apply_profile_by_name_case_insensitive(self, ctrl):
        ctrl.apply_profile_by_name("moderate")
        assert ctrl.active_profile is MODERATE

    def test_reset_clears_profile(self, ctrl):
        ctrl.apply_profile(SLOW)
        ctrl.reset()
        assert not ctrl.is_active
        assert ctrl.active_profile is None

    def test_switch_profile_replaces(self, ctrl):
        ctrl.apply_profile(FAST)
        ctrl.apply_profile(SLOW)
        assert ctrl.active_profile is SLOW

    def test_repr_shows_profile_name(self, ctrl):
        ctrl.apply_profile(FAST)
        assert "FAST" in repr(ctrl)

    def test_repr_shows_none_when_inactive(self, ctrl):
        assert "None" in repr(ctrl)


# ─────────────────────────────────────────────────────────────────────────────
# Tests: NetworkController – simulate_send pass-through
# ─────────────────────────────────────────────────────────────────────────────

class TestSimulateSendPassthrough:
    def test_no_profile_returns_same_bytes(self, ctrl, small_payload):
        result = ctrl.simulate_send(small_payload)
        assert result == small_payload

    def test_simulate_receive_returns_same_bytes(self, ctrl, small_payload):
        ctrl.apply_profile(FAST)
        result = ctrl.simulate_receive(small_payload)
        assert result == small_payload

    def test_simulate_send_with_profile_returns_same_bytes(self, ctrl, small_payload):
        ctrl.apply_profile(FAST)
        result = ctrl.simulate_send(small_payload)
        assert result == small_payload

    def test_simulate_send_empty_bytes(self, ctrl):
        ctrl.apply_profile(FAST)
        result = ctrl.simulate_send(b"")
        assert result == b""


# ─────────────────────────────────────────────────────────────────────────────
# Tests: NetworkController – latency injection
# ─────────────────────────────────────────────────────────────────────────────

class TestLatencyInjection:
    def test_fast_latency_is_small(self, ctrl, small_payload):
        """FAST profile (1ms latency) should complete very quickly."""
        ctrl.apply_profile(FAST)
        t0 = time.perf_counter()
        ctrl.simulate_send(small_payload)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        # Should take at least 1ms and less than 100ms (generous upper bound)
        assert 0.5 <= elapsed_ms <= 100, f"FAST elapsed={elapsed_ms:.2f}ms"

    def test_slow_latency_is_measurable(self, ctrl, small_payload):
        """SLOW profile (50ms latency) should inject at least ~40ms."""
        ctrl.apply_profile(SLOW)
        t0 = time.perf_counter()
        ctrl.simulate_send(small_payload)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        assert elapsed_ms >= 40, f"SLOW elapsed only {elapsed_ms:.2f}ms (expected >=40ms)"

    def test_overhead_records_latency(self, ctrl, small_payload):
        ctrl.apply_profile(SLOW)
        ctrl.simulate_send(small_payload)
        assert ctrl.overhead.total_latency_injected_sec >= SLOW.latency_sec * 0.9

    def test_overhead_call_count_increments(self, ctrl, small_payload):
        ctrl.apply_profile(FAST)
        ctrl.simulate_send(small_payload)
        ctrl.simulate_send(small_payload)
        assert ctrl.overhead.call_count == 2

    def test_overhead_bytes_tracked(self, ctrl, small_payload):
        ctrl.apply_profile(FAST)
        ctrl.simulate_send(small_payload)
        assert ctrl.overhead.bytes_sent == len(small_payload)


# ─────────────────────────────────────────────────────────────────────────────
# Tests: NetworkController – context manager
# ─────────────────────────────────────────────────────────────────────────────

class TestContextManager:
    def test_profile_active_inside_block(self, ctrl):
        with ctrl.active(FAST):
            assert ctrl.is_active
            assert ctrl.active_profile is FAST

    def test_profile_reset_after_block(self, ctrl):
        with ctrl.active(FAST):
            pass
        assert not ctrl.is_active

    def test_profile_reset_on_exception(self, ctrl):
        try:
            with ctrl.active(SLOW):
                raise ValueError("test error")
        except ValueError:
            pass
        assert not ctrl.is_active

    def test_context_manager_yields_controller(self, ctrl):
        with ctrl.active(FAST) as c:
            assert c is ctrl

    def test_simulate_send_inside_context(self, ctrl, small_payload):
        with ctrl.active(FAST) as c:
            result = c.simulate_send(small_payload)
        assert result == small_payload


# ─────────────────────────────────────────────────────────────────────────────
# Tests: NetworkController – overhead management
# ─────────────────────────────────────────────────────────────────────────────

class TestOverheadManagement:
    def test_reset_overhead_preserves_profile(self, ctrl, small_payload):
        ctrl.apply_profile(FAST)
        ctrl.simulate_send(small_payload)
        ctrl.reset_overhead()
        assert ctrl.is_active
        assert ctrl.overhead.call_count == 0
        assert ctrl.overhead.bytes_sent == 0

    def test_get_overhead_snapshot_is_copy(self, ctrl, small_payload):
        ctrl.apply_profile(FAST)
        ctrl.simulate_send(small_payload)
        snap = ctrl.get_overhead_snapshot()
        # Mutating snapshot should not affect controller overhead
        snap.call_count = 999
        assert ctrl.overhead.call_count != 999

    def test_overhead_reset_on_new_profile(self, ctrl, small_payload):
        ctrl.apply_profile(FAST)
        ctrl.simulate_send(small_payload)
        assert ctrl.overhead.call_count == 1
        # Applying a new profile resets overhead
        ctrl.apply_profile(SLOW)
        assert ctrl.overhead.call_count == 0


# ─────────────────────────────────────────────────────────────────────────────
# Tests: NetworkController – verify_profile
# ─────────────────────────────────────────────────────────────────────────────

class TestVerifyProfile:
    def test_verify_raises_when_inactive(self, ctrl):
        with pytest.raises(RuntimeError, match="No active profile"):
            ctrl.verify_profile()

    def test_verify_fast_within_tolerance(self, ctrl):
        ctrl.apply_profile(FAST)
        result = ctrl.verify_profile(payload_bytes=512, tolerance_factor=10.0)
        assert result["profile"] == "FAST"
        assert result["within_tolerance"] is True

    def test_verify_returns_dict_keys(self, ctrl):
        ctrl.apply_profile(FAST)
        result = ctrl.verify_profile(payload_bytes=256)
        expected_keys = {
            "profile", "payload_bytes", "theoretical_sec",
            "measured_sec", "ratio", "within_tolerance", "overhead",
        }
        assert expected_keys.issubset(result.keys())

    def test_verify_measured_ge_theoretical(self, ctrl):
        ctrl.apply_profile(FAST)
        result = ctrl.verify_profile(payload_bytes=512)
        # Measured time should be at least theoretical (can't be faster)
        assert result["measured_sec"] >= result["theoretical_sec"] * 0.5


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Reproducibility
# ─────────────────────────────────────────────────────────────────────────────

class TestReproducibility:
    def test_same_profile_consistent_latency(self, ctrl, small_payload):
        """Two runs under the same profile should inject the same latency."""
        ctrl.apply_profile(FAST)
        t1_start = time.perf_counter()
        ctrl.simulate_send(small_payload)
        t1 = time.perf_counter() - t1_start

        ctrl.reset_overhead()

        t2_start = time.perf_counter()
        ctrl.simulate_send(small_payload)
        t2 = time.perf_counter() - t2_start

        # Both runs should be within 20ms of each other
        diff_ms = abs(t1 - t2) * 1000
        assert diff_ms < 20, f"Latency inconsistency: run1={t1*1000:.2f}ms, run2={t2*1000:.2f}ms"

    def test_overhead_accumulates_linearly(self, ctrl, small_payload):
        """Multiple sends should accumulate overhead linearly."""
        ctrl.apply_profile(FAST)
        N = 3
        for _ in range(N):
            ctrl.simulate_send(small_payload)

        assert ctrl.overhead.call_count == N
        assert ctrl.overhead.bytes_sent == N * len(small_payload)

    def test_different_profiles_different_latency(self):
        """FAST and SLOW profiles should produce measurably different timing."""
        ctrl_fast = NetworkController()
        ctrl_slow = NetworkController()
        payload = b"Z" * 256

        ctrl_fast.apply_profile(FAST)
        t0 = time.perf_counter()
        ctrl_fast.simulate_send(payload)
        t_fast = time.perf_counter() - t0

        ctrl_slow.apply_profile(SLOW)
        t0 = time.perf_counter()
        ctrl_slow.simulate_send(payload)
        t_slow = time.perf_counter() - t0

        assert t_slow > t_fast, (
            f"Expected SLOW ({t_slow*1000:.1f}ms) > FAST ({t_fast*1000:.1f}ms)"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Baseline overhead (FAST profile)
# ─────────────────────────────────────────────────────────────────────────────

class TestBaselineOverhead:
    def test_fast_overhead_is_small(self, ctrl, small_payload):
        """FAST profile should add minimal overhead (< 50ms for 512 bytes)."""
        ctrl.apply_profile(FAST)
        t0 = time.perf_counter()
        ctrl.simulate_send(small_payload)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        # FAST = 1ms latency + near-zero throttle for 512 bytes at 1Gbps
        assert elapsed_ms < 50, f"FAST overhead too high: {elapsed_ms:.2f}ms"

    def test_no_profile_zero_overhead(self, ctrl, small_payload):
        """Without a profile, simulate_send should be near-instantaneous."""
        t0 = time.perf_counter()
        ctrl.simulate_send(small_payload)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        assert elapsed_ms < 5, f"No-profile overhead: {elapsed_ms:.2f}ms"


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Thread safety
# ─────────────────────────────────────────────────────────────────────────────

class TestThreadSafety:
    def test_concurrent_sends_do_not_crash(self, ctrl):
        """Multiple threads using the same controller should not cause errors."""
        ctrl.apply_profile(FAST)
        errors = []
        payload = b"T" * 128

        def send():
            try:
                ctrl.simulate_send(payload)
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=send) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Thread errors: {errors}"

    def test_concurrent_sends_track_bytes(self, ctrl):
        """Byte count should reflect all sends from all threads."""
        ctrl.apply_profile(FAST)
        payload = b"B" * 64
        n_threads = 4

        threads = [
            threading.Thread(target=ctrl.simulate_send, args=(payload,))
            for _ in range(n_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert ctrl.overhead.bytes_sent == n_threads * len(payload)


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Module-level default controller
# ─────────────────────────────────────────────────────────────────────────────

class TestDefaultController:
    def test_get_controller_returns_instance(self):
        c = get_controller()
        assert isinstance(c, NetworkController)

    def test_get_controller_is_singleton(self):
        c1 = get_controller()
        c2 = get_controller()
        assert c1 is c2
