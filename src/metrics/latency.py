"""
Latency measurement record for a single benchmark pipeline run.

Captures all timing components of the end-to-end serialization pipeline:

    T_e2e = T_ser + T_comp + T_net + T_decomp + T_deser

Where:
    T_ser    = serialization time
    T_comp   = compression time   (GZIP only; 0.0 for JSON and MessagePack)
    T_net    = network transmission time
    T_decomp = decompression time (GZIP only; 0.0 for JSON and MessagePack)
    T_deser  = deserialization time
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class LatencyRecord:
    """
    Stores all timing components (in milliseconds) for one benchmark run.

    Attributes:
        format_name:       Serializer name ('json', 'json_gzip', 'messagepack').
        t_ser_ms:          Serialization time in milliseconds.
        t_comp_ms:         Compression time in milliseconds (0.0 if not applicable).
        t_net_ms:          Network transmission time in milliseconds.
        t_decomp_ms:       Decompression time in milliseconds (0.0 if not applicable).
        t_deser_ms:        Deserialization time in milliseconds.
        run_index:         Zero-based run index within the experiment.
        valid:             True if data validated successfully after roundtrip.
    """
    format_name:  str
    t_ser_ms:     float = 0.0
    t_comp_ms:    float = 0.0
    t_net_ms:     float = 0.0
    t_decomp_ms:  float = 0.0
    t_deser_ms:   float = 0.0
    run_index:    int   = 0
    valid:        bool  = True

    @property
    def t_e2e_ms(self) -> float:
        """Total end-to-end latency in milliseconds."""
        return self.t_ser_ms + self.t_comp_ms + self.t_net_ms + self.t_decomp_ms + self.t_deser_ms

    @property
    def t_processing_ms(self) -> float:
        """Total CPU-side processing time (excludes network)."""
        return self.t_ser_ms + self.t_comp_ms + self.t_decomp_ms + self.t_deser_ms

    @property
    def t_network_savings_vs_json_ms(self) -> Optional[float]:
        """
        Placeholder for network time saved versus JSON baseline.
        Populated by the comparison module after all formats are measured.
        """
        return None

    def to_dict(self) -> dict:
        """Serialize record to a flat dictionary for CSV/JSON export."""
        return {
            "format":       self.format_name,
            "run_index":    self.run_index,
            "t_ser_ms":     round(self.t_ser_ms, 6),
            "t_comp_ms":    round(self.t_comp_ms, 6),
            "t_net_ms":     round(self.t_net_ms, 6),
            "t_decomp_ms":  round(self.t_decomp_ms, 6),
            "t_deser_ms":   round(self.t_deser_ms, 6),
            "t_e2e_ms":     round(self.t_e2e_ms, 6),
            "t_processing_ms": round(self.t_processing_ms, 6),
            "valid":        self.valid,
        }

    def __repr__(self) -> str:
        return (
            f"LatencyRecord(format={self.format_name!r}, "
            f"e2e={self.t_e2e_ms:.3f}ms, "
            f"[ser={self.t_ser_ms:.3f} comp={self.t_comp_ms:.3f} "
            f"net={self.t_net_ms:.3f} decomp={self.t_decomp_ms:.3f} "
            f"deser={self.t_deser_ms:.3f}], valid={self.valid})"
        )


class LatencyCollector:
    """
    Accumulates LatencyRecord instances across multiple benchmark runs.

    Provides per-format retrieval and summary statistics access.
    """

    def __init__(self):
        self._records: list[LatencyRecord] = []

    def add(self, record: LatencyRecord) -> None:
        """Append a completed LatencyRecord."""
        self._records.append(record)

    def get_all(self) -> list[LatencyRecord]:
        """Return all recorded latency records."""
        return list(self._records)

    def get_by_format(self, format_name: str) -> list[LatencyRecord]:
        """Return all records for a specific serializer format."""
        return [r for r in self._records if r.format_name == format_name]

    def get_valid_only(self) -> list[LatencyRecord]:
        """Return only records where validation passed."""
        return [r for r in self._records if r.valid]

    def e2e_ms_list(self, format_name: Optional[str] = None) -> list[float]:
        """
        Return a list of end-to-end latency values (ms).

        :param format_name: If given, filter to that format only.
        """
        records = self.get_by_format(format_name) if format_name else self._records
        return [r.t_e2e_ms for r in records if r.valid]

    def count(self) -> int:
        """Total number of records collected."""
        return len(self._records)

    def clear(self) -> None:
        """Reset all stored records."""
        self._records.clear()

    def to_dicts(self) -> list[dict]:
        """Return all records as a list of flat dictionaries."""
        return [r.to_dict() for r in self._records]

    def __repr__(self) -> str:
        return f"LatencyCollector(records={len(self._records)})"
