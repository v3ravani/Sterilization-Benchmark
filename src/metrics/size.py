"""
Payload and data size measurement for benchmark runs.

Tracks:
  - Original dataset size before serialization (JSON reference size)
  - Serialized payload size (transmitted bytes)
  - Compression ratio (payload / json_baseline)
  - Payload reduction percentage (1 - format_size / json_size)

JSON is used as the universal baseline for all size comparisons per the PRD.
"""

import json
from dataclasses import dataclass
from typing import Any, Optional, Union


def measure_json_size(data: Union[dict, list]) -> int:
    """
    Measure the byte size of data as compact JSON (no whitespace).

    This is the universal baseline size reference used throughout the benchmark.

    :param data: Python dict or list to measure.
    :return: Byte count of compact UTF-8 JSON encoding.
    """
    return len(json.dumps(data, separators=(',', ':'), ensure_ascii=False).encode('utf-8'))


def measure_payload_size(payload: bytes) -> int:
    """
    Return the byte size of a serialized payload.

    :param payload: Serialized bytes.
    :return: Byte count.
    """
    return len(payload)


@dataclass
class SizeRecord:
    """
    Payload size metrics for a single benchmark run.

    Attributes:
        format_name:       Serializer name ('json', 'json_gzip', 'messagepack').
        original_size_bytes: Size of the raw data object as compact JSON (baseline).
        payload_size_bytes:  Actual transmitted payload size in bytes.
        json_baseline_bytes: JSON payload size for this same data
                             (== original_size_bytes for JSON format,
                              set to JSON size for GZIP/MessagePack runs).
        run_index:           Zero-based run index.
    """
    format_name:          str
    original_size_bytes:  int
    payload_size_bytes:   int
    json_baseline_bytes:  int
    run_index:            int  = 0

    @property
    def compression_ratio(self) -> float:
        """
        Ratio of transmitted payload to JSON baseline.
        Values < 1.0 indicate size reduction.

        Compression Ratio = payload_size / json_baseline
        """
        if self.json_baseline_bytes == 0:
            return 1.0
        return self.payload_size_bytes / self.json_baseline_bytes

    @property
    def payload_reduction(self) -> float:
        """
        Fractional payload size reduction versus JSON baseline.

        Payload Reduction = 1 - (payload_size / json_baseline)
        Values > 0.0 mean the payload is smaller than JSON.
        """
        return 1.0 - self.compression_ratio

    @property
    def payload_reduction_pct(self) -> float:
        """Payload reduction as a percentage (0–100)."""
        return self.payload_reduction * 100.0

    @property
    def bytes_saved(self) -> int:
        """Absolute bytes saved versus JSON baseline."""
        return max(0, self.json_baseline_bytes - self.payload_size_bytes)

    @property
    def overhead_bytes(self) -> int:
        """Absolute bytes added versus JSON baseline (positive = larger than JSON)."""
        return max(0, self.payload_size_bytes - self.json_baseline_bytes)

    def to_dict(self) -> dict:
        """Serialize to flat dictionary for CSV/JSON export."""
        return {
            "format":               self.format_name,
            "run_index":            self.run_index,
            "original_size_bytes":  self.original_size_bytes,
            "payload_size_bytes":   self.payload_size_bytes,
            "json_baseline_bytes":  self.json_baseline_bytes,
            "compression_ratio":    round(self.compression_ratio, 6),
            "payload_reduction":    round(self.payload_reduction, 6),
            "payload_reduction_pct": round(self.payload_reduction_pct, 3),
            "bytes_saved":          self.bytes_saved,
        }

    def __repr__(self) -> str:
        return (
            f"SizeRecord(format={self.format_name!r}, "
            f"payload={self.payload_size_bytes}B, "
            f"reduction={self.payload_reduction_pct:.1f}%)"
        )


class SizeCollector:
    """
    Accumulates SizeRecord instances across multiple benchmark runs.
    """

    def __init__(self):
        self._records: list[SizeRecord] = []

    def add(self, record: SizeRecord) -> None:
        """Append a completed SizeRecord."""
        self._records.append(record)

    def get_all(self) -> list[SizeRecord]:
        """Return all recorded size records."""
        return list(self._records)

    def get_by_format(self, format_name: str) -> list[SizeRecord]:
        """Return all records for a given serializer format."""
        return [r for r in self._records if r.format_name == format_name]

    def average_payload_size(self, format_name: Optional[str] = None) -> float:
        """
        Return average payload size in bytes across all records.

        :param format_name: If given, filter to that format.
        """
        records = self.get_by_format(format_name) if format_name else self._records
        if not records:
            return 0.0
        return sum(r.payload_size_bytes for r in records) / len(records)

    def average_compression_ratio(self, format_name: Optional[str] = None) -> float:
        """Return average compression ratio across records."""
        records = self.get_by_format(format_name) if format_name else self._records
        if not records:
            return 1.0
        return sum(r.compression_ratio for r in records) / len(records)

    def count(self) -> int:
        return len(self._records)

    def clear(self) -> None:
        self._records.clear()

    def to_dicts(self) -> list[dict]:
        return [r.to_dict() for r in self._records]

    def __repr__(self) -> str:
        return f"SizeCollector(records={len(self._records)})"
