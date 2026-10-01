"""
Network profiles for the benchmark experiment.

Defines four canonical network conditions used across all benchmark runs.
Each profile specifies:
  - bandwidth_mbps : Simulated effective bandwidth in megabits per second.
  - latency_ms     : Simulated one-way network latency in milliseconds.
  - description    : Human-readable label for the profile.

Design note:
  True OS-level traffic shaping (tc, clumsy) requires elevated privileges
  and external tools. This module defines the *logical* profiles. The
  NetworkController (controller.py) applies them by injecting sleep-based
  latency and token-bucket rate limiting on the Python send/receive path,
  making the simulation portable, reproducible, and admin-free.
"""

from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class NetworkProfile:
    """
    Immutable descriptor for a simulated network condition.

    Attributes:
        name          : Identifier string (e.g. 'FAST').
        bandwidth_mbps: Effective bandwidth cap in Mbps.
        latency_ms    : One-way network latency in milliseconds.
        description   : Human-readable label.
    """
    name:           str
    bandwidth_mbps: float
    latency_ms:     float
    description:    str

    @property
    def bandwidth_bps(self) -> float:
        """Bandwidth in bits per second."""
        return self.bandwidth_mbps * 1_000_000

    @property
    def bandwidth_bytes_per_sec(self) -> float:
        """Bandwidth in bytes per second."""
        return self.bandwidth_bps / 8

    @property
    def latency_sec(self) -> float:
        """One-way latency in seconds."""
        return self.latency_ms / 1000.0

    @property
    def rtt_sec(self) -> float:
        """Round-trip time estimate in seconds (2 × one-way latency)."""
        return self.latency_sec * 2.0

    def theoretical_transfer_time_sec(self, payload_bytes: int) -> float:
        """
        Compute theoretical transfer time for a payload.

        T_net = latency + payload_size / bandwidth

        :param payload_bytes: Payload size in bytes.
        :return: Estimated transfer time in seconds.
        """
        return self.latency_sec + (payload_bytes / self.bandwidth_bytes_per_sec)

    def __str__(self) -> str:
        return (
            f"NetworkProfile({self.name}: "
            f"{self.bandwidth_mbps} Mbps, {self.latency_ms} ms latency)"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Canonical Profile Definitions
# ─────────────────────────────────────────────────────────────────────────────

PROFILES: Dict[str, NetworkProfile] = {

    "FAST": NetworkProfile(
        name="FAST",
        bandwidth_mbps=1000.0,
        latency_ms=1.0,
        description="Gigabit LAN / local loopback — effectively unconstrained",
    ),

    "MODERATE": NetworkProfile(
        name="MODERATE",
        bandwidth_mbps=100.0,
        latency_ms=15.0,
        description="Fast broadband / data-centre internal network",
    ),

    "SLOW": NetworkProfile(
        name="SLOW",
        bandwidth_mbps=10.0,
        latency_ms=50.0,
        description="Slow broadband / 4G mobile network",
    ),

    "VERY_SLOW": NetworkProfile(
        name="VERY_SLOW",
        bandwidth_mbps=1.0,
        latency_ms=150.0,
        description="Restricted mobile / 3G / high-latency remote connection",
    ),
}

# Convenience references
FAST      = PROFILES["FAST"]
MODERATE  = PROFILES["MODERATE"]
SLOW      = PROFILES["SLOW"]
VERY_SLOW = PROFILES["VERY_SLOW"]

# Ordered list for iteration (ascending constraint)
PROFILE_ORDER = [FAST, MODERATE, SLOW, VERY_SLOW]


def get_profile(name: str) -> NetworkProfile:
    """
    Retrieve a network profile by name (case-insensitive).

    :param name: Profile name, e.g. 'FAST', 'slow', 'Very_Slow'.
    :raises KeyError: If the profile name is not recognized.
    :return: NetworkProfile instance.
    """
    key = name.upper()
    if key not in PROFILES:
        raise KeyError(
            f"Unknown network profile '{name}'. "
            f"Available profiles: {list(PROFILES.keys())}"
        )
    return PROFILES[key]


def list_profiles() -> list:
    """Return list of all profile names in ascending constraint order."""
    return [p.name for p in PROFILE_ORDER]
