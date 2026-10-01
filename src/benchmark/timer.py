"""
High-resolution precision timer for sub-millisecond benchmark measurement.

Uses time.perf_counter_ns() which provides nanosecond resolution on all
modern operating systems. All public methods return values in the most
useful unit for the caller (nanoseconds internally, milliseconds externally).

Usage:
    timer = PrecisionTimer()
    with timer.measure() as t:
        do_work()
    print(t.elapsed_ms)       # milliseconds
    print(t.elapsed_ns)       # nanoseconds

Or manually:
    timer = PrecisionTimer()
    timer.start()
    do_work()
    elapsed_ms = timer.stop_ms()
"""

import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Generator, Optional


@dataclass
class TimingRecord:
    """
    A single timing measurement record.

    Attributes:
        start_ns:   Wall-clock start time in nanoseconds (perf_counter_ns).
        end_ns:     Wall-clock end time in nanoseconds (perf_counter_ns).
        label:      Optional descriptive label for this measurement.
    """
    start_ns: int
    end_ns:   int
    label:    str = ""

    @property
    def elapsed_ns(self) -> int:
        """Elapsed time in nanoseconds."""
        return self.end_ns - self.start_ns

    @property
    def elapsed_us(self) -> float:
        """Elapsed time in microseconds."""
        return self.elapsed_ns / 1_000.0

    @property
    def elapsed_ms(self) -> float:
        """Elapsed time in milliseconds."""
        return self.elapsed_ns / 1_000_000.0

    @property
    def elapsed_sec(self) -> float:
        """Elapsed time in seconds."""
        return self.elapsed_ns / 1_000_000_000.0

    def __repr__(self) -> str:
        label = f"'{self.label}' " if self.label else ""
        return f"TimingRecord({label}{self.elapsed_ms:.4f}ms)"


class _MutableTimingRecord:
    """Mutable version used during context-manager measurement."""
    def __init__(self, label: str):
        self.label    = label
        self.start_ns = 0
        self.end_ns   = 0

    @property
    def elapsed_ns(self) -> int:
        return self.end_ns - self.start_ns

    @property
    def elapsed_ms(self) -> float:
        return self.elapsed_ns / 1_000_000.0

    @property
    def elapsed_sec(self) -> float:
        return self.elapsed_ns / 1_000_000_000.0

    def to_record(self) -> TimingRecord:
        return TimingRecord(
            start_ns=self.start_ns,
            end_ns=self.end_ns,
            label=self.label,
        )


class PrecisionTimer:
    """
    High-resolution nanosecond-precision timer.

    Wraps time.perf_counter_ns() for consistent measurement across the
    benchmark pipeline. Maintains an internal history of all measurements
    made via the context manager.
    """

    def __init__(self):
        self._start_ns: Optional[int] = None
        self._history: list[TimingRecord] = []

    def start(self) -> None:
        """Start the timer. Call stop() or stop_ms() to complete measurement."""
        self._start_ns = time.perf_counter_ns()

    def stop_ns(self) -> int:
        """
        Stop the timer and return elapsed nanoseconds.

        :raises RuntimeError: If start() was not called first.
        """
        if self._start_ns is None:
            raise RuntimeError("Timer was not started. Call start() first.")
        elapsed = time.perf_counter_ns() - self._start_ns
        self._start_ns = None
        return elapsed

    def stop_ms(self) -> float:
        """Stop the timer and return elapsed milliseconds."""
        return self.stop_ns() / 1_000_000.0

    def stop_sec(self) -> float:
        """Stop the timer and return elapsed seconds."""
        return self.stop_ns() / 1_000_000_000.0

    @contextmanager
    def measure(self, label: str = "") -> Generator[_MutableTimingRecord, None, None]:
        """
        Context manager for timing a block of code.

        Yields a mutable record that is populated on exit.
        The completed record is also appended to self.history.

        Usage:
            with timer.measure("serialize") as t:
                payload = serializer.serialize(data)
            print(t.elapsed_ms)
        """
        record = _MutableTimingRecord(label=label)
        record.start_ns = time.perf_counter_ns()
        try:
            yield record
        finally:
            record.end_ns = time.perf_counter_ns()
            self._history.append(record.to_record())

    @property
    def history(self) -> list[TimingRecord]:
        """All completed timing records since last clear."""
        return list(self._history)

    def clear_history(self) -> None:
        """Clear all stored timing records."""
        self._history.clear()

    @staticmethod
    def now_ns() -> int:
        """Return the current perf_counter timestamp in nanoseconds."""
        return time.perf_counter_ns()

    @staticmethod
    def now_ms() -> float:
        """Return the current perf_counter timestamp in milliseconds."""
        return time.perf_counter_ns() / 1_000_000.0


# ─────────────────────────────────────────────────────────────────────────────
# Convenience: time a callable directly
# ─────────────────────────────────────────────────────────────────────────────

def time_call(fn, *args, **kwargs) -> tuple:
    """
    Time a callable and return (result, elapsed_ms).

    :param fn:    Callable to time.
    :param args:  Positional arguments for fn.
    :param kwargs: Keyword arguments for fn.
    :return:      Tuple of (fn(*args, **kwargs), elapsed_ms).
    """
    t0 = time.perf_counter_ns()
    result = fn(*args, **kwargs)
    elapsed_ms = (time.perf_counter_ns() - t0) / 1_000_000.0
    return result, elapsed_ms
