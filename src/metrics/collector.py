"""
Metrics aggregator: combines LatencyRecord, SizeRecord, and ResourceRecord
into a single unified MetricRecord per benchmark run.

The MetricRecord is the atomic unit of benchmark output — one per
(workload × format × network_profile × run_index) combination.
"""

from dataclasses import dataclass, field, asdict
from typing import TYPE_CHECKING, Optional, Any

from src.metrics.latency import LatencyRecord
from src.metrics.size import SizeRecord
from src.metrics.resources import ResourceRecord


@dataclass
class MetricRecord:
    """
    Unified benchmark result record for one experimental run.

    Combines:
      - Workload context (data type, size target, redundancy, network profile)
      - Latency measurements (all pipeline timing components)
      - Size measurements (payload size, compression ratio, reduction %)
      - Resource measurements (peak memory, CPU usage per phase)

    This is the primary record written to results/raw/ CSV/JSON files.
    """

    # ── Experiment context ────────────────────────────────────────────────────
    experiment_id:    str   = ""
    workload_name:    str   = ""
    data_structure:   str   = ""
    target_size_kb:   float = 0.0
    redundancy:       str   = ""
    network_profile:  str   = ""
    format_name:      str   = ""
    run_index:        int   = 0
    seed:             int   = 42

    # ── Latency (ms) ──────────────────────────────────────────────────────────
    t_ser_ms:         float = 0.0
    t_comp_ms:        float = 0.0
    t_net_ms:         float = 0.0
    t_decomp_ms:      float = 0.0
    t_deser_ms:       float = 0.0
    t_e2e_ms:         float = 0.0
    t_processing_ms:  float = 0.0

    # ── Size (bytes) ─────────────────────────────────────────────────────────
    original_size_bytes:   int   = 0
    payload_size_bytes:    int   = 0
    json_baseline_bytes:   int   = 0
    compression_ratio:     float = 1.0
    payload_reduction_pct: float = 0.0
    bytes_saved:           int   = 0

    # ── Resources ─────────────────────────────────────────────────────────────
    peak_memory_mb:   float = 0.0
    total_cpu_ms:     float = 0.0
    ser_memory_mb:    float = 0.0
    deser_memory_mb:  float = 0.0
    ser_cpu_pct:      float = 0.0
    deser_cpu_pct:    float = 0.0

    # ── Validity ──────────────────────────────────────────────────────────────
    valid:            bool  = True

    def to_dict(self) -> dict:
        """Return all fields as a flat dictionary for CSV/JSON export."""
        return {k: v for k, v in self.__dict__.items()}

    as_dict = to_dict

    def __repr__(self) -> str:
        return (
            f"MetricRecord("
            f"workload={self.workload_name!r}, "
            f"format={self.format_name!r}, "
            f"net={self.network_profile!r}, "
            f"run={self.run_index}, "
            f"e2e={self.t_e2e_ms:.3f}ms, "
            f"payload={self.payload_size_bytes}B, "
            f"valid={self.valid})"
        )


class MetricsCollector:
    """
    Aggregates individual LatencyRecord, SizeRecord, and ResourceRecord
    instances into unified MetricRecord objects.

    Usage:
        collector = MetricsCollector()

        record = collector.build_record(
            experiment_id   = "exp_001",
            workload_name   = "flat_medium_high",
            data_structure  = "flat",
            target_size_kb  = 500.0,
            redundancy      = "high",
            network_profile = "SLOW",
            run_index       = 0,
            seed            = 42,
            latency         = latency_record,
            size            = size_record,
            resource        = resource_record,   # optional
        )

        collector.add(record)
        all_records = collector.get_all()
    """

    def __init__(self):
        self._records: list[MetricRecord] = []

    def build_record(
        self,
        experiment_id:   str,
        workload_name:   str,
        data_structure:  str,
        target_size_kb:  float,
        redundancy:      str,
        network_profile: str,
        run_index:       int,
        seed:            int,
        latency:         LatencyRecord,
        size:            SizeRecord,
        resource:        Optional[ResourceRecord] = None,
    ) -> MetricRecord:
        """
        Construct a MetricRecord from the three measurement components.

        :param experiment_id:   Unique experiment identifier string.
        :param workload_name:   Workload catalog name.
        :param data_structure:  Data structure type ('flat', 'nested', etc.).
        :param target_size_kb:  Target payload size in kilobytes.
        :param redundancy:      Redundancy level ('low'/'medium'/'high').
        :param network_profile: Network profile name ('FAST', 'SLOW', etc.).
        :param run_index:       Zero-based repetition index.
        :param seed:            Random seed used for data generation.
        :param latency:         Completed LatencyRecord.
        :param size:            Completed SizeRecord.
        :param resource:        Optional completed ResourceRecord.
        :return:                Populated MetricRecord.
        """
        rec = MetricRecord(
            experiment_id    = experiment_id,
            workload_name    = workload_name,
            data_structure   = data_structure,
            target_size_kb   = target_size_kb,
            redundancy       = redundancy,
            network_profile  = network_profile,
            format_name      = latency.format_name,
            run_index        = run_index,
            seed             = seed,
            # Latency
            t_ser_ms         = latency.t_ser_ms,
            t_comp_ms        = latency.t_comp_ms,
            t_net_ms         = latency.t_net_ms,
            t_decomp_ms      = latency.t_decomp_ms,
            t_deser_ms       = latency.t_deser_ms,
            t_e2e_ms         = latency.t_e2e_ms,
            t_processing_ms  = latency.t_processing_ms,
            # Size
            original_size_bytes   = size.original_size_bytes,
            payload_size_bytes    = size.payload_size_bytes,
            json_baseline_bytes   = size.json_baseline_bytes,
            compression_ratio     = size.compression_ratio,
            payload_reduction_pct = size.payload_reduction_pct,
            bytes_saved           = size.bytes_saved,
            # Validity
            valid            = latency.valid,
        )

        # Resource metrics (optional — skipped if monitor is not attached)
        if resource is not None:
            rec.peak_memory_mb  = resource.peak_memory_mb
            rec.total_cpu_ms    = resource.total_cpu_ms
            if resource.serialize is not None:
                rec.ser_memory_mb = resource.serialize.memory_rss_mb
                rec.ser_cpu_pct   = resource.serialize.cpu_utilization_pct
            if resource.deserialize is not None:
                rec.deser_memory_mb = resource.deserialize.memory_rss_mb
                rec.deser_cpu_pct   = resource.deserialize.cpu_utilization_pct

        return rec

    def build_record_from_transfer(
        self,
        transfer,                        # TransferResult (avoids circular import)
        size:            SizeRecord,
        experiment_id:   str   = "",
        workload_name:   str   = "",
        data_structure:  str   = "",
        target_size_kb:  float = 0.0,
        redundancy:      str   = "",
        network_profile: str   = "",
        seed:            int   = 42,
        resource:        Optional[ResourceRecord] = None,
    ) -> MetricRecord:
        """
        Build a MetricRecord directly from a TransferResult + SizeRecord.

        This is the convenience bridge used by the benchmark runner so it
        doesn't need to construct an intermediate LatencyRecord manually.

        :param transfer:        Completed TransferResult from BenchmarkClient.
        :param size:            Completed SizeRecord from SizeCollector.
        :param experiment_id:   Experiment identifier.
        :param workload_name:   Workload name from catalog.
        :param data_structure:  Data structure type.
        :param target_size_kb:  Target payload size in KB.
        :param redundancy:      Redundancy level.
        :param network_profile: Network profile name.
        :param seed:            Random seed.
        :param resource:        Optional ResourceRecord.
        :return:                Populated MetricRecord.
        """
        # Build a LatencyRecord from TransferResult fields
        latency = LatencyRecord(
            format_name = transfer.format_name,
            t_ser_ms    = transfer.t_ser_ms,
            t_comp_ms   = 0.0,                 # comp is included in t_ser for gzip
            t_net_ms    = transfer.t_net_ms,
            t_decomp_ms = transfer.t_decomp_ms,
            t_deser_ms  = transfer.t_deser_ms,
            run_index   = transfer.run_index,
            valid       = transfer.success,
        )
        return self.build_record(
            experiment_id   = experiment_id,
            workload_name   = workload_name,
            data_structure  = data_structure,
            target_size_kb  = target_size_kb,
            redundancy      = redundancy,
            network_profile = network_profile,
            run_index       = transfer.run_index,
            seed            = seed,
            latency         = latency,
            size            = size,
            resource        = resource,
        )

    def add(self, record: MetricRecord) -> None:
        """Append a completed MetricRecord."""
        self._records.append(record)

    def get_all(self) -> list[MetricRecord]:
        """Return all collected records."""
        return list(self._records)

    def get_by_format(self, format_name: str) -> list[MetricRecord]:
        """Filter records by serializer format name."""
        return [r for r in self._records if r.format_name == format_name]

    def get_by_profile(self, profile_name: str) -> list[MetricRecord]:
        """Filter records by network profile name."""
        return [r for r in self._records if r.network_profile == profile_name]

    def get_by_workload(self, workload_name: str) -> list[MetricRecord]:
        """Filter records by workload name."""
        return [r for r in self._records if r.workload_name == workload_name]

    def get_valid(self) -> list[MetricRecord]:
        """Return only records where data validation passed."""
        return [r for r in self._records if r.valid]

    def count(self) -> int:
        return len(self._records)

    def count_valid(self) -> int:
        return sum(1 for r in self._records if r.valid)

    def clear(self) -> None:
        self._records.clear()

    def to_dicts(self) -> list[dict]:
        """Return all records as flat dictionaries for export."""
        return [r.to_dict() for r in self._records]

    def __repr__(self) -> str:
        return (
            f"MetricsCollector("
            f"total={self.count()}, valid={self.count_valid()})"
        )
