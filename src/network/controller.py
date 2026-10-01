"""
Windows-compatible network simulation controller.

Applies controlled bandwidth throttling and latency injection on the Python
send/receive path using:

  1. Latency injection  — time.sleep() on the sending side to simulate
                          one-way propagation delay.
  2. Token-bucket rate  — byte-paced sleep to throttle throughput to the
                          profile's bandwidth cap without OS-level tools.
  3. Context manager    — clean activation/deactivation around each benchmark
                          run via `with controller.active(profile): ...`

Design principles:
  - No admin / elevated privileges required.
  - No third-party tools (clumsy, tc, netem, WaanSim).
  - Portable: works identically on all Windows Python environments.
  - Isolated: all simulation happens inside Python — benchmark code does
    not contain any Windows-specific commands.
  - Measurable: the controller tracks injected latency and throttle time
    so callers can subtract simulation overhead from measured timings.

Limitation:
  This is application-layer simulation, not OS-kernel traffic shaping.
  It accurately models the *time cost* of network conditions for a single
  client/server pair (which is exactly what this benchmark measures), but
  does not affect other processes or system-wide traffic.
"""

import time
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Generator, Optional

from src.network.profiles import NetworkProfile, get_profile, FAST


# ─────────────────────────────────────────────────────────────────────────────
# Simulation result / overhead record
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SimulationOverhead:
    """
    Tracks the cumulative simulation overhead injected during a run.
    This is subtracted from raw timings to isolate actual serialization cost.

    Attributes:
        total_latency_injected_sec:  Total sleep time added for latency simulation.
        total_throttle_sleep_sec:    Total sleep time added for bandwidth throttling.
        bytes_sent:                  Cumulative bytes processed through the throttler.
        call_count:                  Number of throttle_send calls made.
    """
    total_latency_injected_sec: float = 0.0
    total_throttle_sleep_sec:   float = 0.0
    bytes_sent:                 int   = 0
    call_count:                 int   = 0

    @property
    def total_overhead_sec(self) -> float:
        return self.total_latency_injected_sec + self.total_throttle_sleep_sec

    def reset(self) -> None:
        self.total_latency_injected_sec = 0.0
        self.total_throttle_sleep_sec   = 0.0
        self.bytes_sent                 = 0
        self.call_count                 = 0

    def __repr__(self) -> str:
        return (
            f"SimulationOverhead("
            f"latency={self.total_latency_injected_sec*1000:.2f}ms, "
            f"throttle={self.total_throttle_sleep_sec*1000:.2f}ms, "
            f"bytes={self.bytes_sent}, "
            f"calls={self.call_count})"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Token-bucket rate limiter
# ─────────────────────────────────────────────────────────────────────────────

class _TokenBucket:
    """
    Simple token-bucket rate limiter for byte-paced bandwidth throttling.

    Tokens refill at `rate_bytes_per_sec`. Consuming more tokens than
    currently available causes the caller to sleep until tokens replenish.
    """

    def __init__(self, rate_bytes_per_sec: float):
        self._rate = rate_bytes_per_sec          # bytes/sec refill rate
        self._tokens = rate_bytes_per_sec        # start full (1 second bucket)
        self._max_tokens = rate_bytes_per_sec    # cap bucket at 1-second worth
        self._last_refill = time.perf_counter()
        self._lock = threading.Lock()

    def consume(self, n_bytes: int) -> float:
        """
        Consume `n_bytes` tokens, sleeping if insufficient tokens available.

        :param n_bytes: Number of bytes to consume.
        :return: Seconds slept waiting for tokens.
        """
        with self._lock:
            # Refill tokens based on elapsed time
            now = time.perf_counter()
            elapsed = now - self._last_refill
            self._tokens = min(
                self._max_tokens,
                self._tokens + elapsed * self._rate,
            )
            self._last_refill = now

            sleep_time = 0.0
            if self._tokens < n_bytes:
                deficit = n_bytes - self._tokens
                sleep_time = deficit / self._rate
                time.sleep(sleep_time)
                self._tokens = 0.0
            else:
                self._tokens -= n_bytes

            return sleep_time

    def update_rate(self, rate_bytes_per_sec: float) -> None:
        with self._lock:
            self._rate = rate_bytes_per_sec
            self._max_tokens = rate_bytes_per_sec
            self._tokens = min(self._tokens, self._max_tokens)


# ─────────────────────────────────────────────────────────────────────────────
# Network Controller
# ─────────────────────────────────────────────────────────────────────────────

class NetworkController:
    """
    Windows-compatible network simulation controller.

    Usage:

        controller = NetworkController()

        # Use as a context manager (recommended):
        with controller.active(profile):
            payload = controller.simulate_send(serialized_bytes)
            # ... send payload over HTTP ...
            controller.simulate_receive(payload)

        # Or manually:
        controller.apply_profile(profile)
        controller.simulate_send(data)
        controller.reset()
    """

    def __init__(self):
        self._active_profile: Optional[NetworkProfile] = None
        self._bucket: Optional[_TokenBucket] = None
        self._overhead = SimulationOverhead()
        self._lock = threading.Lock()

    # ── Profile management ───────────────────────────────────────────────────

    @property
    def active_profile(self) -> Optional[NetworkProfile]:
        """Currently active network profile, or None if no profile is set."""
        return self._active_profile

    @property
    def is_active(self) -> bool:
        """True if a network profile is currently active."""
        return self._active_profile is not None

    def apply_profile(self, profile: NetworkProfile) -> None:
        """
        Activate a network profile.

        :param profile: NetworkProfile to apply.
        """
        with self._lock:
            self._active_profile = profile
            self._bucket = _TokenBucket(profile.bandwidth_bytes_per_sec)
            self._overhead.reset()

    def apply_profile_by_name(self, name: str) -> None:
        """
        Activate a network profile by name.

        :param name: Profile name (e.g. 'SLOW', 'fast').
        """
        self.apply_profile(get_profile(name))

    def reset(self) -> None:
        """Deactivate any active profile and clear simulation state."""
        with self._lock:
            self._active_profile = None
            self._bucket = None
            self._overhead.reset()

    # ── Simulation interface ─────────────────────────────────────────────────

    def simulate_send(self, payload: bytes) -> bytes:
        """
        Simulate sending a payload over the network.

        Injects:
          1. One-way latency sleep (propagation delay).
          2. Token-bucket throttle sleep (bandwidth cap).

        :param payload: Bytes to simulate sending.
        :return: The same payload (pass-through).
        """
        if not self.is_active:
            return payload

        profile = self._active_profile
        n_bytes = len(payload)

        # 1. Inject latency (one-way propagation delay)
        latency_sleep = profile.latency_sec
        time.sleep(latency_sleep)

        # 2. Token-bucket throttle
        throttle_sleep = self._bucket.consume(n_bytes)

        # Record overhead
        with self._lock:
            self._overhead.total_latency_injected_sec += latency_sleep
            self._overhead.total_throttle_sleep_sec   += throttle_sleep
            self._overhead.bytes_sent                 += n_bytes
            self._overhead.call_count                 += 1

        return payload

    def simulate_receive(self, payload: bytes) -> bytes:
        """
        Simulate receiving a payload from the network.

        For a loopback benchmark, receive does not add extra latency since
        the send side already modelled the full one-way delay. This method
        exists for API symmetry and future extensibility.

        :param payload: Bytes to simulate receiving.
        :return: The same payload (pass-through).
        """
        return payload

    def measure_transfer_time(self, payload: bytes) -> float:
        """
        Simulate a send and return the actual wall-clock time taken.

        Useful for calibrating the controller against profile expectations.

        :param payload: Payload to measure.
        :return: Elapsed seconds for the simulated transfer.
        """
        t_start = time.perf_counter()
        self.simulate_send(payload)
        return time.perf_counter() - t_start

    # ── Overhead reporting ───────────────────────────────────────────────────

    @property
    def overhead(self) -> SimulationOverhead:
        """Current cumulative simulation overhead record."""
        return self._overhead

    def get_overhead_snapshot(self) -> SimulationOverhead:
        """Return a copy of the current overhead state."""
        snap = SimulationOverhead(
            total_latency_injected_sec=self._overhead.total_latency_injected_sec,
            total_throttle_sleep_sec=self._overhead.total_throttle_sleep_sec,
            bytes_sent=self._overhead.bytes_sent,
            call_count=self._overhead.call_count,
        )
        return snap

    def reset_overhead(self) -> None:
        """Reset overhead counters without changing the active profile."""
        self._overhead.reset()

    # ── Context manager ──────────────────────────────────────────────────────

    @contextmanager
    def active(
        self, profile: NetworkProfile
    ) -> Generator["NetworkController", None, None]:
        """
        Context manager that activates a profile for the duration of the block
        and automatically resets when the block exits (including on error).

        Usage:
            controller = NetworkController()
            with controller.active(SLOW):
                result = controller.simulate_send(payload)

        :param profile: NetworkProfile to activate.
        :yields: This NetworkController instance.
        """
        self.apply_profile(profile)
        try:
            yield self
        finally:
            self.reset()

    # ── Verification helpers ─────────────────────────────────────────────────

    def verify_profile(
        self,
        payload_bytes: int = 1024,
        tolerance_factor: float = 2.5,
    ) -> dict:
        """
        Verify that the active profile produces realistic simulated timings.

        Sends a test payload and compares the measured transfer time to the
        theoretical time from the profile formula:
            T_net = latency + size / bandwidth

        :param payload_bytes:     Size of test payload in bytes.
        :param tolerance_factor:  Allowed multiple above theoretical time.
        :return: Verification result dictionary.
        """
        if not self.is_active:
            raise RuntimeError("No active profile — call apply_profile() first.")

        profile = self._active_profile
        test_payload = b"x" * payload_bytes

        self.reset_overhead()
        t_start = time.perf_counter()
        self.simulate_send(test_payload)
        elapsed = time.perf_counter() - t_start

        theoretical = profile.theoretical_transfer_time_sec(payload_bytes)
        ratio = elapsed / theoretical if theoretical > 0 else float("inf")
        within_tolerance = ratio <= tolerance_factor

        return {
            "profile":            profile.name,
            "payload_bytes":      payload_bytes,
            "theoretical_sec":    round(theoretical, 6),
            "measured_sec":       round(elapsed, 6),
            "ratio":              round(ratio, 3),
            "within_tolerance":   within_tolerance,
            "overhead":           str(self.get_overhead_snapshot()),
        }

    def __repr__(self) -> str:
        profile_name = self._active_profile.name if self._active_profile else "None"
        return f"NetworkController(active_profile={profile_name})"


# ─────────────────────────────────────────────────────────────────────────────
# Module-level default controller instance
# ─────────────────────────────────────────────────────────────────────────────

_default_controller = NetworkController()


def get_controller() -> NetworkController:
    """Return the module-level default NetworkController instance."""
    return _default_controller
