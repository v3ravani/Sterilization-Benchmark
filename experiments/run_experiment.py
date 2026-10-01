#!/usr/bin/env python3
"""
run_experiment.py — Automated benchmark suite runner.

Executes the full experimental matrix defined in config/experiment.yaml:
    Workloads × Formats × Network Profiles × Repetitions

Raw results are written to data/results/raw/ as CSV and JSON Lines files.

Usage:
    python experiments/run_experiment.py
    python experiments/run_experiment.py --config config/experiment.yaml
    python experiments/run_experiment.py --output data/results --quick
    python experiments/run_experiment.py --quick --reps 2 --warmup 1 --verbose

Options:
    --config   PATH   Path to experiment YAML config (default: config/experiment.yaml)
    --output   PATH   Root directory for result files (default: data/results)
    --quick           Run only small workloads with reduced repetitions (smoke test)
    --reps     N      Override repetition count
    --warmup   N      Override warmup run count
    --verbose         Enable DEBUG-level logging
    --no-progress     Disable progress bar
    --analyze         Run statistical analysis on results after the experiment
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

# Ensure project root is on sys.path when run as a script
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.benchmark.experiment import (
    load_experiment_config,
    build_matrix,
    quick_config,
)
from src.benchmark.runner import BenchmarkRunner
from src.benchmark.result_writer import ResultWriter


# ─────────────────────────────────────────────────────────────────────────────
# CLI argument parsing
# ─────────────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the serialization format benchmark experiment suite.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--config",
        default="config/experiment.yaml",
        metavar="PATH",
        help="Path to experiment YAML configuration (default: config/experiment.yaml)",
    )
    parser.add_argument(
        "--output",
        default="data/results",
        metavar="PATH",
        help="Root directory for result files (default: data/results)",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Run only small workloads with reduced repetitions (fast smoke test)",
    )
    parser.add_argument(
        "--reps",
        type=int,
        default=None,
        metavar="N",
        help="Override the number of measured repetitions per cell",
    )
    parser.add_argument(
        "--warmup",
        type=int,
        default=None,
        metavar="N",
        help="Override the number of warmup iterations per cell",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable DEBUG logging",
    )
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable progress bar output",
    )
    parser.add_argument(
        "--analyze",
        action="store_true",
        help="Run statistical analysis on results after experiment completes",
    )
    return parser.parse_args()


# ─────────────────────────────────────────────────────────────────────────────
# Progress bar (simple, no external dependencies)
# ─────────────────────────────────────────────────────────────────────────────

class _SimpleProgress:
    """Minimal inline progress bar — no tqdm required."""

    def __init__(self, total: int, enabled: bool = True):
        self.total   = total
        self.current = 0
        self.enabled = enabled
        self._start  = time.perf_counter()

    def update(self, current: int, total: int, description: str) -> None:
        if not self.enabled:
            return
        self.current = current
        pct = current / total * 100 if total > 0 else 0
        elapsed = time.perf_counter() - self._start
        eta     = (elapsed / current) * (total - current) if current > 0 else 0
        bar_len = 30
        filled  = int(bar_len * current / total) if total > 0 else 0
        bar     = "█" * filled + "░" * (bar_len - filled)
        line = (
            f"\r[{bar}] {pct:5.1f}% ({current}/{total}) "
            f"ETA:{eta:.0f}s  {description[:50]:<50}"
        )
        print(line, end="", flush=True)
        if current >= total:
            print()  # newline when done


# ─────────────────────────────────────────────────────────────────────────────
# Analysis (optional post-run summary)
# ─────────────────────────────────────────────────────────────────────────────

def _run_analysis(records, thresholds: dict) -> None:
    """Print a statistical analysis summary to stdout."""
    from src.analysis.statistics import compute_stats_for_records, summary_table
    from src.analysis.comparison import compare_formats, comparison_table
    from src.analysis.decision_model import run_decision_framework, decision_table

    print("\n" + "=" * 70)
    print("STATISTICAL ANALYSIS - End-to-End Latency (t_e2e_ms)")
    print("=" * 70)
    stats = compute_stats_for_records(records, field="t_e2e_ms")
    print(summary_table(stats))

    print("\n" + "=" * 70)
    print("PAIRWISE FORMAT COMPARISON (vs JSON baseline)")
    print("=" * 70)
    comparisons = compare_formats(records)
    print(comparison_table(comparisons))

    print("\n" + "=" * 70)
    print("3-ZONE DECISION FRAMEWORK")
    print("=" * 70)
    decisions = run_decision_framework(records, thresholds)
    print(decision_table(decisions))
    print()


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

def main() -> int:
    args = _parse_args()

    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    logger = logging.getLogger("run_experiment")

    # -- Load configuration ----------------------------------------------------
    if args.quick:
        reps   = args.reps   or 3
        warmup = args.warmup or 1
        config = quick_config(repetitions=reps, warmup_runs=warmup)
        logger.info("Quick mode: %d workloads, %d reps, %d warmup", len(config.workload_names), reps, warmup)
    else:
        config_path = Path(args.config)
        if not config_path.exists():
            print(f"ERROR: Config file not found: {config_path}", file=sys.stderr)
            return 1
        config = load_experiment_config(config_path)
        if args.reps is not None:
            config.__dict__["repetitions"] = args.reps
        if args.warmup is not None:
            config.__dict__["warmup_runs"] = args.warmup

    # -- Build matrix ----------------------------------------------------------
    matrix = build_matrix(config)
    print(f"\n{'='*60}")
    print(f"  Experiment: {config.name} (id={config.experiment_id})")
    print(f"  Matrix:     {len(matrix.cells)} cells x {config.repetitions} reps")
    print(f"              = {matrix.total_runs} measured runs")
    print(f"              + {len(matrix.cells) * config.warmup_runs} warmup runs")
    print(f"  Formats:    {config.serializer_names}")
    print(f"  Profiles:   {config.network_profile_names}")
    print(f"  Workloads:  {len(config.workload_names)} workloads")
    print(f"  Output dir: {args.output}")
    print(f"{'='*60}\n")

    # -- Set up progress callback ----------------------------------------------
    show_progress = not args.no_progress
    progress      = _SimpleProgress(len(matrix.cells), enabled=show_progress)

    def progress_callback(current: int, total: int, description: str) -> None:
        progress.update(current, total, description)

    # -- Run benchmark ---------------------------------------------------------
    runner = BenchmarkRunner(
        config=config,
        output_dir=args.output,
        progress_callback=progress_callback,
    )

    t_start = time.perf_counter()
    summary = runner.run_experiment(matrix)
    t_total = time.perf_counter() - t_start

    # -- Print summary ---------------------------------------------------------
    print(f"\n{'='*60}")
    print(f"  BENCHMARK COMPLETE")
    print(f"{'='*60}")
    print(f"  Experiment ID:  {summary.experiment_id}")
    print(f"  Total runs:     {summary.total_runs}")
    print(f"  Valid runs:     {summary.valid_runs} ({summary.valid_pct:.1f}%)")
    print(f"  Failed runs:    {summary.failed_runs}")
    print(f"  Warmup runs:    {summary.skipped_warmup}")
    print(f"  Wall time:      {t_total:.1f}s")
    if summary.output_csv:
        print(f"  CSV output:     {summary.output_csv}")
    if summary.output_json:
        print(f"  JSONL output:   {summary.output_json}")
    if summary.error_messages:
        print(f"\n  Errors ({len(summary.error_messages)}):")
        for msg in summary.error_messages[:5]:
            print(f"    * {msg}")
    print(f"{'='*60}\n")

    # Optional analysis
    if args.analyze:
        all_records = runner._collector.get_all()
        if not all_records:
            # Fallback: read from the written JSONL file
            import json as _json
            if summary.output_json:
                from src.metrics.collector import MetricRecord
                all_records = []
                with open(summary.output_json) as fh:
                    for line in fh:
                        d = _json.loads(line)
                        r = MetricRecord(**{k: d[k] for k in MetricRecord.__dataclass_fields__ if k in d})
                        all_records.append(r)
        thresholds = {
            "no_switch": config.thresholds.no_switch,
            "switch":    config.thresholds.switch,
        }
        _run_analysis(all_records, thresholds)


    return 0 if summary.failed_runs == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
