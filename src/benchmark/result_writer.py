"""
Immutable result writer — persists raw benchmark MetricRecord data.

Design principles:
  - Immutability: files are never overwritten (raises if path exists).
  - Atomicity: writes to a temp file, then renames (no partial files on crash).
  - Two formats: CSV (wide, columnar) and JSON Lines (one record per line).
  - Auto-generates timestamped filenames under data/results/raw/.
  - Writes a JSON run-summary metadata file alongside the data files.

Usage:
    writer = ResultWriter("data/results")
    csv_path  = writer.write_csv(records, experiment_id="abc123")
    json_path = writer.write_json(records, experiment_id="abc123")
"""

from __future__ import annotations

import csv
import json
import os
import tempfile
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from src.metrics.collector import MetricRecord


# ─────────────────────────────────────────────────────────────────────────────
# Column order for CSV output
# ─────────────────────────────────────────────────────────────────────────────

_CSV_COLUMNS = [
    # Context
    "experiment_id",
    "workload_name",
    "data_structure",
    "target_size_kb",
    "redundancy",
    "network_profile",
    "format_name",
    "run_index",
    "seed",
    # Latency (ms)
    "t_ser_ms",
    "t_comp_ms",
    "t_net_ms",
    "t_decomp_ms",
    "t_deser_ms",
    "t_e2e_ms",
    "t_processing_ms",
    # Size (bytes)
    "original_size_bytes",
    "payload_size_bytes",
    "json_baseline_bytes",
    "compression_ratio",
    "payload_reduction_pct",
    "bytes_saved",
    # Resources
    "peak_memory_mb",
    "total_cpu_ms",
    "ser_memory_mb",
    "deser_memory_mb",
    "ser_cpu_pct",
    "deser_cpu_pct",
    # Validity
    "valid",
]


# ─────────────────────────────────────────────────────────────────────────────
# ResultWriter
# ─────────────────────────────────────────────────────────────────────────────

class ResultWriter:
    """
    Writes raw benchmark MetricRecord data to immutable CSV and JSON files.

    All output files are placed under `output_dir/raw/` and named with
    the experiment_id and a UTC timestamp to guarantee uniqueness.

    :param output_dir: Root directory for all result files.
    """

    def __init__(self, output_dir: str | Path = "data/results"):
        self.output_dir = Path(output_dir)
        self.raw_dir    = self.output_dir / "raw"
        self.raw_dir.mkdir(parents=True, exist_ok=True)

    # ── Public interface ──────────────────────────────────────────────────────

    def write_csv(
        self,
        records: List[MetricRecord],
        experiment_id: str,
        filename: Optional[str] = None,
    ) -> Path:
        """
        Write all MetricRecord objects to a flat CSV file.

        Columns are ordered per _CSV_COLUMNS; any extra fields appear at end.

        :param records:       List of MetricRecord objects.
        :param experiment_id: Experiment identifier used in filename.
        :param filename:      Override auto-generated filename (for tests).
        :raises FileExistsError: If the target file already exists.
        :return: Path to the written CSV file.
        """
        path = self._resolve_path(experiment_id, "csv", filename)
        rows = [r.to_dict() for r in records]
        self._write_csv_atomic(rows, path)
        return path

    def write_json(
        self,
        records: List[MetricRecord],
        experiment_id: str,
        filename: Optional[str] = None,
    ) -> Path:
        """
        Write all MetricRecord objects to a JSON Lines file (.jsonl).

        Each line is one JSON object representing one MetricRecord.

        :param records:       List of MetricRecord objects.
        :param experiment_id: Experiment identifier used in filename.
        :param filename:      Override auto-generated filename (for tests).
        :raises FileExistsError: If the target file already exists.
        :return: Path to the written JSON Lines file.
        """
        path = self._resolve_path(experiment_id, "jsonl", filename)
        rows = [r.to_dict() for r in records]
        self._write_jsonl_atomic(rows, path)
        return path

    def write_run_summary(
        self,
        summary_dict: Dict,
        experiment_id: str,
        filename: Optional[str] = None,
    ) -> Path:
        """
        Write a JSON run summary metadata file.

        :param summary_dict:  Dict of summary fields (from RunSummary.to_dict()).
        :param experiment_id: Experiment identifier used in filename.
        :param filename:      Override auto-generated filename (for tests).
        :raises FileExistsError: If the target file already exists.
        :return: Path to the written JSON summary file.
        """
        path = self._resolve_path(experiment_id, "summary.json", filename)
        self._write_json_atomic(summary_dict, path)
        return path

    def list_result_files(self) -> List[Path]:
        """Return sorted list of all files in the raw directory."""
        return sorted(self.raw_dir.glob("*"))

    # ── Path helpers ─────────────────────────────────────────────────────────

    def _resolve_path(
        self,
        experiment_id: str,
        extension: str,
        override: Optional[str],
    ) -> Path:
        """Build the output path, using override name or auto-generating one."""
        if override:
            path = self.raw_dir / override
        else:
            ts   = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            path = self.raw_dir / f"{experiment_id}_{ts}.{extension}"
        return path

    # ── Atomic writers ────────────────────────────────────────────────────────

    def _write_csv_atomic(self, rows: List[dict], path: Path) -> None:
        """Write a list-of-dicts to CSV atomically via temp-file rename."""
        if path.exists():
            raise FileExistsError(f"Result file already exists (immutable): {path}")

        # Determine column order: known columns first, then any extras
        if rows:
            all_keys = list(rows[0].keys())
            extra    = [k for k in all_keys if k not in _CSV_COLUMNS]
            columns  = [c for c in _CSV_COLUMNS if c in all_keys] + extra
        else:
            columns = _CSV_COLUMNS

        tmp_path = path.with_suffix(".tmp")
        try:
            with tmp_path.open("w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(
                    fh, fieldnames=columns, extrasaction="ignore"
                )
                writer.writeheader()
                writer.writerows(rows)
            os.replace(tmp_path, path)
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise

    def _write_jsonl_atomic(self, rows: List[dict], path: Path) -> None:
        """Write a list-of-dicts to JSON Lines atomically via temp-file rename."""
        if path.exists():
            raise FileExistsError(f"Result file already exists (immutable): {path}")

        tmp_path = path.with_suffix(".tmp")
        try:
            with tmp_path.open("w", encoding="utf-8") as fh:
                for row in rows:
                    fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            os.replace(tmp_path, path)
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise

    def _write_json_atomic(self, data: dict, path: Path) -> None:
        """Write a single dict to JSON atomically via temp-file rename."""
        if path.exists():
            raise FileExistsError(f"Result file already exists (immutable): {path}")

        tmp_path = path.with_suffix(".tmp")
        try:
            with tmp_path.open("w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, ensure_ascii=False)
                fh.write("\n")
            os.replace(tmp_path, path)
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise

    def __repr__(self) -> str:
        return f"ResultWriter(raw_dir={self.raw_dir!r})"
