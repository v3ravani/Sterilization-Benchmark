"""
Benchmark runner — orchestrates the full experimental matrix.

Executes:
    workloads × formats × network profiles × repetitions

For each (workload, format, profile, run_index) cell the runner:
  1. Generates synthetic data (seeded, reproducible).
  2. Runs warmup iterations (discarded, not recorded).
  3. Runs N measured iterations:
       a. Serializes data  → records t_ser_ms.
       b. Simulates network transfer → records t_net_ms.
       c. Deserializes data → records t_deser_ms.
       d. Validates round-trip integrity → sets valid flag.
       e. Measures payload sizes.
       f. Assembles MetricRecord via MetricsCollector.
  4. Streams each MetricRecord to the ResultWriter immediately
     (no data is lost on crash mid-run).

Usage:
    config = load_experiment_config("config/experiment.yaml")
    matrix = build_matrix(config)
    runner = BenchmarkRunner(config, output_dir="data/results")
    summary = runner.run_experiment(matrix)
    print(summary)
"""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.benchmark.experiment import ExperimentConfig, ExperimentMatrix, MatrixCell
from src.benchmark.timer import PrecisionTimer
from src.data.generator import generate
from src.data.validator import validate as validate_data
from src.metrics.collector import MetricRecord, MetricsCollector
from src.metrics.latency import LatencyRecord
from src.metrics.size import SizeRecord, measure_json_size, measure_payload_size
from src.network.controller import NetworkController
from src.network.profiles import get_profile
from src.serialization.registry import SerializerRegistry

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Run summary
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class RunSummary:
    """
    High-level summary of a completed benchmark run.

    Attributes:
        experiment_id:  Unique experiment identifier.
        total_cells:    Number of (workload × format × profile) cells.
        total_runs:     Total measured iterations (cells × repetitions).
        valid_runs:     Runs where data validation passed.
        failed_runs:    Runs where serialization/validation failed.
        skipped_warmup: Total warmup iterations executed (not recorded).
        duration_sec:   Wall-clock time for the entire experiment.
        output_csv:     Path to the raw CSV results file (if written).
        output_json:    Path to the raw JSON Lines results file (if written).
        error_messages: List of non-fatal error summaries.
    """
    experiment_id:  str
    total_cells:    int   = 0
    total_runs:     int   = 0
    valid_runs:     int   = 0
    failed_runs:    int   = 0
    skipped_warmup: int   = 0
    duration_sec:   float = 0.0
    output_csv:     Optional[str] = None
    output_json:    Optional[str] = None
    error_messages: List[str] = field(default_factory=list)

    @property
    def valid_pct(self) -> float:
        """Percentage of measured runs that passed validation."""
        if self.total_runs == 0:
            return 0.0
        return self.valid_runs / self.total_runs * 100.0

    def __repr__(self) -> str:
        return (
            f"RunSummary("
            f"id={self.experiment_id!r}, "
            f"runs={self.valid_runs}/{self.total_runs} valid, "
            f"cells={self.total_cells}, "
            f"duration={self.duration_sec:.1f}s)"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Benchmark Runner
# ─────────────────────────────────────────────────────────────────────────────

class BenchmarkRunner:
    """
    Orchestrates benchmark execution across the full experimental matrix.

    Responsibilities:
      - Iterates over all MatrixCell objects in the ExperimentMatrix.
      - Runs warmup + measured iterations per cell.
      - Validates data integrity after every roundtrip.
      - Assembles MetricRecord for every measured iteration.
      - Streams results to ResultWriter immediately (crash-safe).

    The runner does NOT import from src.api (no HTTP server needed) — it
    performs the serialize/transmit/deserialize loop inline using the
    NetworkController for timing isolation. This keeps the runner fast,
    hermetic, and network-server-independent.

    Usage:
        from src.benchmark.runner import BenchmarkRunner
        from src.benchmark.experiment import load_experiment_config, build_matrix

        config = load_experiment_config("config/experiment.yaml")
        matrix = build_matrix(config)
        runner = BenchmarkRunner(config, output_dir="data/results")
        summary = runner.run_experiment(matrix)
    """

    def __init__(
        self,
        config: ExperimentConfig,
        output_dir: str | Path = "data/results",
        writer=None,           # Optional[ResultWriter] — injected for tests
        progress_callback=None,  # Optional[Callable[[int, int, str], None]]
        abort_checker=None,      # Optional[Callable[[], bool]]
        max_workers: int = 1,    # Number of concurrent worker threads
    ):
        """
        Initialise the runner.

        :param config:            ExperimentConfig for this run.
        :param output_dir:        Root directory for result files.
        :param writer:            Optional ResultWriter; created automatically if None.
        :param progress_callback: Optional callback(current, total, description).
        :param abort_checker:     Optional callback() -> bool to check for run cancellation.
        :param max_workers:       Max concurrent worker threads (>=1).
        """
        self.config    = config
        self.output_dir = Path(output_dir)
        self.max_workers = max(1, int(max_workers))
        self._registry  = SerializerRegistry()
        self._collector = MetricsCollector()
        self._net_ctrl  = NetworkController()
        self._timer     = PrecisionTimer()
        self._progress_callback = progress_callback
        self._abort_checker = abort_checker

        # Dataset cache keyed by (structure, target_size_kb, redundancy, seed)
        # Guarantees all 3 formats benchmark against the identical dataset in memory
        self._dataset_cache: Dict[Tuple[str, float, str, int], Tuple[Any, int, int]] = {}
        self._cache_lock = threading.Lock()
        self._summary_lock = threading.Lock()
        self._collector_lock = threading.Lock()

        # Import here to avoid circular at module level
        if writer is None:
            from src.benchmark.result_writer import ResultWriter
            self._writer = ResultWriter(self.output_dir)
        else:
            self._writer = writer

    # ── Dataset Caching Helper ────────────────────────────────────────────────

    def _get_dataset(self, cell: MatrixCell, run_index: int) -> Tuple[Any, int, int]:
        """
        Retrieve or generate the dataset for this workload and run_index.

        Cached by (structure, target_size_kb, redundancy, seed) to guarantee
        that all three formats (json, json_gzip, messagepack) benchmark against
        the exact same payload in memory without redundant generation overhead.
        """
        workload = cell.workload
        run_seed = workload.seed + run_index
        cache_key = (workload.structure, workload.target_size_kb, workload.redundancy, run_seed)

        with self._cache_lock:
            cached = self._dataset_cache.get(cache_key)

        if cached is not None:
            return cached

        data = generate(
            structure=workload.structure,
            target_size_kb=workload.target_size_kb,
            redundancy=workload.redundancy,
            seed=run_seed,
        )
        json_baseline_bytes = measure_json_size(data)
        result = (data, run_seed, json_baseline_bytes)

        with self._cache_lock:
            self._dataset_cache[cache_key] = result

        return result

    # ── Public API ────────────────────────────────────────────────────────────

    def run_experiment(self, matrix: ExperimentMatrix) -> RunSummary:
        """
        Execute the full experimental matrix and return a run summary.

        Supports both sequential (max_workers=1) and concurrent (max_workers>1)
        execution using thread pool workers with isolated network controllers.

        :param matrix: Pre-computed ExperimentMatrix.
        :return: RunSummary with aggregate statistics and output paths.
        """
        summary = RunSummary(
            experiment_id=self.config.experiment_id,
            total_cells=len(matrix.cells),
        )
        all_records: List[MetricRecord] = []
        t_experiment_start = time.perf_counter()
        total_cells = len(matrix.cells)

        if self.max_workers <= 1 or total_cells <= 1:
            for cell_idx, cell in enumerate(matrix.cells):
                if self._abort_checker and self._abort_checker():
                    logger.info("Experiment %s aborted by user at cell %d/%d", self.config.experiment_id, cell_idx, total_cells)
                    summary.error_messages.append("Aborted by user.")
                    break

                cell_records = self._run_cell(cell, summary)
                all_records.extend(cell_records)

                if self._progress_callback:
                    description = (
                        f"[{cell_idx+1}/{total_cells}] "
                        f"{cell.workload.name} | {cell.format_name} | {cell.profile_name}"
                    )
                    self._progress_callback(cell_idx + 1, total_cells, description)
        else:
            # Concurrent execution across matrix cells
            completed_cells = 0
            completed_lock = threading.Lock()

            def _worker_task(cell: MatrixCell) -> List[MetricRecord]:
                if self._abort_checker and self._abort_checker():
                    return []
                # Dedicated thread-local network controller & timer to prevent cross-thread interference
                w_net_ctrl = NetworkController()
                w_timer = PrecisionTimer()
                records = self._run_cell(cell, summary, net_ctrl=w_net_ctrl, timer=w_timer)

                nonlocal completed_cells
                with completed_lock:
                    completed_cells += 1
                    current = completed_cells
                    if self._progress_callback:
                        desc = f"[{current}/{total_cells}] {cell.workload.name} | {cell.format_name} | {cell.profile_name}"
                        self._progress_callback(current, total_cells, desc)

                return records

            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = {executor.submit(_worker_task, cell): cell for cell in matrix.cells}
                for future in as_completed(futures):
                    if self._abort_checker and self._abort_checker():
                        summary.error_messages.append("Aborted by user.")
                        executor.shutdown(wait=False, cancel_futures=True)
                        break
                    try:
                        recs = future.result()
                        all_records.extend(recs)
                    except Exception as exc:
                        msg = f"Worker failed on cell {futures[future]}: {exc}"
                        logger.error(msg)
                        with self._summary_lock:
                            summary.error_messages.append(msg)

        summary.duration_sec = time.perf_counter() - t_experiment_start

        # Write consolidated results
        try:
            csv_path  = self._writer.write_csv(all_records, self.config.experiment_id)
            json_path = self._writer.write_json(all_records, self.config.experiment_id)
            summary.output_csv  = str(csv_path)
            summary.output_json = str(json_path)
        except Exception as exc:
            msg = f"ResultWriter failed: {exc}"
            logger.error(msg)
            summary.error_messages.append(msg)

        logger.info(
            "Experiment %s complete: %d/%d valid runs in %.1fs",
            summary.experiment_id, summary.valid_runs, summary.total_runs,
            summary.duration_sec,
        )
        return summary

    def run_single(
        self,
        workload_name: str,
        format_name: str,
        profile_name: str,
        repetitions: int = 5,
        warmup_runs: int = 1,
    ) -> List[MetricRecord]:
        """
        Run a single (workload, format, profile) configuration.

        Convenience method used by the reproduce CLI and integration tests.

        :param workload_name: Workload catalog name.
        :param format_name:   Serializer format name.
        :param profile_name:  Network profile name.
        :param repetitions:   Number of measured iterations.
        :param warmup_runs:   Number of warmup iterations (discarded).
        :return: List of MetricRecord (one per measured iteration).
        """
        from src.benchmark.experiment import MatrixCell
        from src.data.workloads import get_workload

        workload = get_workload(workload_name)
        cell     = MatrixCell(
            workload=workload,
            format_name=format_name,
            profile_name=profile_name,
            cell_index=0,
        )
        # Temporarily override repetitions / warmup for single run
        orig_reps   = self.config.repetitions
        orig_warmup = self.config.warmup_runs
        self.config.__dict__["repetitions"]  = repetitions
        self.config.__dict__["warmup_runs"]  = warmup_runs

        dummy_summary = RunSummary(experiment_id=self.config.experiment_id)
        records = self._run_cell(cell, dummy_summary)

        # Restore config fields
        self.config.__dict__["repetitions"]  = orig_reps
        self.config.__dict__["warmup_runs"]  = orig_warmup
        return records

    # ── Internal: cell-level loop ─────────────────────────────────────────────

    def _run_cell(
        self,
        cell: MatrixCell,
        summary: RunSummary,
        net_ctrl: Optional[NetworkController] = None,
        timer: Optional[PrecisionTimer] = None,
    ) -> List[MetricRecord]:
        """
        Execute all iterations for one MatrixCell and return measured records.

        :param cell:     The matrix cell to run.
        :param summary:  Mutable summary to update with counts.
        :param net_ctrl: Dedicated NetworkController (for worker threads).
        :param timer:    Dedicated PrecisionTimer (for worker threads).
        :return: List of MetricRecord (warmup excluded).
        """
        cell_records: List[MetricRecord] = []
        total_iters = self.config.warmup_runs + self.config.repetitions
        active_net_ctrl = net_ctrl or self._net_ctrl
        active_timer = timer or self._timer

        for i in range(total_iters):
            if self._abort_checker and self._abort_checker():
                break
            is_warmup = i < self.config.warmup_runs
            run_index = i - self.config.warmup_runs  # negative during warmup

            try:
                record = self._run_single_iteration(
                    cell=cell,
                    run_index=max(run_index, 0),
                    is_warmup=is_warmup,
                    net_ctrl=active_net_ctrl,
                    timer=active_timer,
                )
            except Exception as exc:  # pragma: no cover
                msg = (
                    f"Exception in cell {cell} iter {i}: {type(exc).__name__}: {exc}"
                )
                logger.warning(msg)
                with self._summary_lock:
                    summary.error_messages.append(msg)
                    if not is_warmup:
                        summary.total_runs  += 1
                        summary.failed_runs += 1
                continue

            if is_warmup:
                with self._summary_lock:
                    summary.skipped_warmup += 1
                continue

            # Measured iteration
            with self._summary_lock:
                summary.total_runs += 1
                if record.valid:
                    summary.valid_runs += 1
                else:
                    summary.failed_runs += 1

            cell_records.append(record)

        return cell_records

    # ── Internal: single timed iteration ─────────────────────────────────────

    def _run_single_iteration(
        self,
        cell: MatrixCell,
        run_index: int,
        is_warmup: bool = False,
        net_ctrl: Optional[NetworkController] = None,
        timer: Optional[PrecisionTimer] = None,
    ) -> MetricRecord:
        """
        Execute one timed benchmark iteration for a given MatrixCell.

        Pipeline:
          1. Retrieve cached or generate data (seeded by workload.seed + run_index)
          2. Serialize  → t_ser_ms
          3. Measure payload size
          4. Simulate network transfer → t_net_ms
          5. Deserialize → t_deser_ms
          6. Validate round-trip
          7. Assemble MetricRecord

        :param cell:      MatrixCell (workload + format + profile).
        :param run_index: Zero-based measured-iteration index.
        :param is_warmup: If True, results are discarded (not counted).
        :param net_ctrl:  NetworkController instance.
        :param timer:     PrecisionTimer instance.
        :return:          MetricRecord for this iteration.
        """
        active_net_ctrl = net_ctrl or self._net_ctrl
        active_timer = timer or self._timer

        workload = cell.workload
        serializer = self._registry.get(cell.format_name)
        profile    = get_profile(cell.profile_name)

        # ── 1. Retrieve data (cached across formats for reproducibility) ───────
        data, run_seed, json_baseline_bytes = self._get_dataset(cell, run_index)

        # ── 2. Serialize ──────────────────────────────────────────────────────
        with active_timer.measure("serialize") as t_ser:
            payload: bytes = serializer.serialize(data)
        t_ser_ms = t_ser.elapsed_ms

        payload_size_bytes = measure_payload_size(payload)

        # ── 3. Simulate network transfer ─────────────────────────────────────
        active_net_ctrl.apply_profile(profile)
        active_net_ctrl.reset_overhead()
        try:
            with active_timer.measure("network") as t_net:
                transmitted = active_net_ctrl.simulate_send(payload)
        finally:
            active_net_ctrl.reset()
        t_net_ms = t_net.elapsed_ms

        # ── 4. Deserialize ────────────────────────────────────────────────────
        with active_timer.measure("deserialize") as t_deser:
            reconstructed = serializer.deserialize(transmitted)
        t_deser_ms = t_deser.elapsed_ms

        # ── 5. Validate round-trip ────────────────────────────────────────────
        validation = validate_data(data, reconstructed)
        is_valid   = validation.valid

        if not is_valid and not is_warmup:
            logger.warning(
                "Validation FAILED: cell=%s run=%d errors=%s",
                cell, run_index, validation.errors[:2],
            )

        # ── 6. Determine compression timing (GZIP-specific) ──────────────────
        # For GZIP: t_ser_ms includes compression, t_deser_ms includes decompression.
        # We record t_comp_ms and t_decomp_ms as 0 since they're folded into ser/deser.
        t_comp_ms   = 0.0
        t_decomp_ms = 0.0

        # ── 7. Build MetricRecord ─────────────────────────────────────────────
        latency = LatencyRecord(
            format_name=cell.format_name,
            t_ser_ms=t_ser_ms,
            t_comp_ms=t_comp_ms,
            t_net_ms=t_net_ms,
            t_decomp_ms=t_decomp_ms,
            t_deser_ms=t_deser_ms,
            run_index=run_index,
            valid=is_valid,
        )
        size = SizeRecord(
            format_name=cell.format_name,
            original_size_bytes=json_baseline_bytes,
            payload_size_bytes=payload_size_bytes,
            json_baseline_bytes=json_baseline_bytes,
            run_index=run_index,
        )

        record = self._collector.build_record(
            experiment_id   = self.config.experiment_id,
            workload_name   = workload.name,
            data_structure  = workload.structure,
            target_size_kb  = workload.target_size_kb,
            redundancy      = workload.redundancy,
            network_profile = cell.profile_name,
            run_index       = run_index,
            seed            = run_seed,
            latency         = latency,
            size            = size,
        )

        logger.debug(
            "%s run=%d %s",
            ("WARMUP" if is_warmup else "RUN   "),
            run_index, record,
        )
        # Also register with the collector for in-memory access (--analyze etc.)
        if not is_warmup:
            with self._collector_lock:
                self._collector.add(record)
        return record

