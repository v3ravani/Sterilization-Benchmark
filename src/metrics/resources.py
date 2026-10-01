"""
System resource monitor: CPU utilization and memory usage tracking via psutil.

Measures:
  - Process memory usage (RSS) in MB before and after each phase.
  - CPU time consumed (user + system) by the process during each phase.
  - Wall-clock CPU utilization % for the process during a measurement window.

Usage:
    monitor = ResourceMonitor()

    with monitor.measure("serialize") as snap:
        payload = serializer.serialize(data)

    print(snap.cpu_delta_ms)       # CPU time consumed (ms)
    print(snap.memory_rss_mb)      # RSS memory at end of window
    print(snap.memory_delta_mb)    # Memory change during window
"""

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Generator, Optional

import psutil


# ─────────────────────────────────────────────────────────────────────────────
# Snapshot helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get_process() -> psutil.Process:
    """Return the current process handle."""
    return psutil.Process()


def _rss_bytes() -> int:
    """Return current process resident set size in bytes."""
    return _get_process().memory_info().rss


def _cpu_times_ms() -> float:
    """Return total process CPU time (user + system) in milliseconds."""
    ct = _get_process().cpu_times()
    return (ct.user + ct.system) * 1000.0


@dataclass
class ResourceSnapshot:
    """
    Resource usage captured around a single benchmark phase.

    Attributes:
        phase:              Label for the measured phase (e.g. 'serialize').
        memory_start_bytes: RSS memory at start of window.
        memory_end_bytes:   RSS memory at end of window.
        cpu_start_ms:       Cumulative CPU time (user+sys) at start, in ms.
        cpu_end_ms:         Cumulative CPU time (user+sys) at end, in ms.
        wall_start_ns:      Wall clock at start (perf_counter_ns).
        wall_end_ns:        Wall clock at end (perf_counter_ns).
    """
    phase:               str   = ""
    memory_start_bytes:  int   = 0
    memory_end_bytes:    int   = 0
    cpu_start_ms:        float = 0.0
    cpu_end_ms:          float = 0.0
    wall_start_ns:       int   = 0
    wall_end_ns:         int   = 0

    @property
    def memory_rss_mb(self) -> float:
        """RSS memory at end of window in megabytes."""
        return self.memory_end_bytes / (1024 * 1024)

    @property
    def memory_start_mb(self) -> float:
        """RSS memory at start of window in megabytes."""
        return self.memory_start_bytes / (1024 * 1024)

    @property
    def memory_delta_bytes(self) -> int:
        """Change in RSS memory during the window (can be negative on GC)."""
        return self.memory_end_bytes - self.memory_start_bytes

    @property
    def memory_delta_mb(self) -> float:
        """Change in RSS memory in megabytes."""
        return self.memory_delta_bytes / (1024 * 1024)

    @property
    def cpu_delta_ms(self) -> float:
        """CPU time consumed (user + system) during the window in milliseconds."""
        return max(0.0, self.cpu_end_ms - self.cpu_start_ms)

    @property
    def wall_elapsed_ms(self) -> float:
        """Wall-clock elapsed time during the window in milliseconds."""
        return (self.wall_end_ns - self.wall_start_ns) / 1_000_000.0

    @property
    def cpu_utilization_pct(self) -> float:
        """
        Approximate CPU utilization % during the window.

        cpu_util = (cpu_delta_ms / wall_elapsed_ms) * 100
        Capped at 100% for single-core equivalent.
        """
        wall = self.wall_elapsed_ms
        if wall <= 0:
            return 0.0
        return min(100.0, (self.cpu_delta_ms / wall) * 100.0)

    def to_dict(self) -> dict:
        """Serialize to flat dictionary for CSV/JSON export."""
        return {
            "phase":                self.phase,
            "memory_rss_mb":        round(self.memory_rss_mb, 3),
            "memory_delta_mb":      round(self.memory_delta_mb, 3),
            "cpu_delta_ms":         round(self.cpu_delta_ms, 4),
            "wall_elapsed_ms":      round(self.wall_elapsed_ms, 4),
            "cpu_utilization_pct":  round(self.cpu_utilization_pct, 2),
        }

    def __repr__(self) -> str:
        return (
            f"ResourceSnapshot(phase={self.phase!r}, "
            f"mem={self.memory_rss_mb:.1f}MB Δ{self.memory_delta_mb:+.2f}MB, "
            f"cpu={self.cpu_delta_ms:.2f}ms, "
            f"util={self.cpu_utilization_pct:.1f}%)"
        )


@dataclass
class ResourceRecord:
    """
    Combined resource snapshot for a complete benchmark run.
    One record per format per run; holds snapshots for each pipeline phase.

    Attributes:
        format_name: Serializer format name.
        run_index:   Zero-based run index.
        serialize:   Resource snapshot for the serialization phase.
        compress:    Resource snapshot for the compression phase (GZIP only).
        decompress:  Resource snapshot for the decompression phase (GZIP only).
        deserialize: Resource snapshot for the deserialization phase.
    """
    format_name:  str
    run_index:    int                       = 0
    serialize:    Optional[ResourceSnapshot] = None
    compress:     Optional[ResourceSnapshot] = None
    decompress:   Optional[ResourceSnapshot] = None
    deserialize:  Optional[ResourceSnapshot] = None

    @property
    def peak_memory_mb(self) -> float:
        """Peak RSS memory across all phases in MB."""
        snapshots = [
            s for s in [self.serialize, self.compress, self.decompress, self.deserialize]
            if s is not None
        ]
        if not snapshots:
            return 0.0
        return max(s.memory_rss_mb for s in snapshots)

    @property
    def total_cpu_ms(self) -> float:
        """Total CPU time consumed across all phases."""
        return sum(
            s.cpu_delta_ms
            for s in [self.serialize, self.compress, self.decompress, self.deserialize]
            if s is not None
        )

    def to_dict(self) -> dict:
        """Flatten all phase snapshots into a single export dictionary."""
        d: dict = {
            "format":         self.format_name,
            "run_index":      self.run_index,
            "peak_memory_mb": round(self.peak_memory_mb, 3),
            "total_cpu_ms":   round(self.total_cpu_ms, 4),
        }
        for phase_name, snap in [
            ("ser", self.serialize),
            ("comp", self.compress),
            ("decomp", self.decompress),
            ("deser", self.deserialize),
        ]:
            if snap is not None:
                for k, v in snap.to_dict().items():
                    if k != "phase":
                        d[f"{phase_name}_{k}"] = v
        return d

    def __repr__(self) -> str:
        return (
            f"ResourceRecord(format={self.format_name!r}, "
            f"peak_mem={self.peak_memory_mb:.1f}MB, "
            f"total_cpu={self.total_cpu_ms:.2f}ms)"
        )


class ResourceMonitor:
    """
    Context-manager based system resource monitor.

    Captures before/after psutil snapshots around any measured code block.
    """

    def __init__(self):
        self._process = _get_process()

    @contextmanager
    def measure(self, phase: str = "") -> Generator[ResourceSnapshot, None, None]:
        """
        Context manager that captures resource usage around a code block.

        Yields a ResourceSnapshot that is populated on exit.

        Usage:
            monitor = ResourceMonitor()
            with monitor.measure("serialize") as snap:
                payload = serializer.serialize(data)
            print(snap.memory_rss_mb)
        """
        snap = ResourceSnapshot(phase=phase)
        snap.memory_start_bytes = self._process.memory_info().rss
        snap.cpu_start_ms = (
            self._process.cpu_times().user + self._process.cpu_times().system
        ) * 1000.0
        snap.wall_start_ns = time.perf_counter_ns()
        try:
            yield snap
        finally:
            snap.wall_end_ns        = time.perf_counter_ns()
            snap.memory_end_bytes   = self._process.memory_info().rss
            snap.cpu_end_ms         = (
                self._process.cpu_times().user + self._process.cpu_times().system
            ) * 1000.0

    def current_memory_mb(self) -> float:
        """Return current process RSS in megabytes."""
        return self._process.memory_info().rss / (1024 * 1024)

    def current_cpu_pct(self, interval: float = 0.05) -> float:
        """
        Return current process CPU utilization percentage.

        :param interval: Sampling interval in seconds.
        """
        return self._process.cpu_percent(interval=interval)
