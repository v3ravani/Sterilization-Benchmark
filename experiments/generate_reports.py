#!/usr/bin/env python3
"""
generate_reports.py — Automated Report, Plots, and Tables Generator.

Processes benchmark raw measurements and produces:
  - 10 visualization plots in plots/ (payload, performance, resources, breakeven)
  - 7 structured benchmark tables in results/tables/ (.md and .csv)

Usage:
    # Generate from latest raw results or run a quick benchmark
    python experiments/generate_reports.py --quick

    # Generate from a specific raw results file
    python experiments/generate_reports.py --input data/results/raw/xxxx.jsonl
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# Ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.analysis.plots import generate_all_plots
from src.analysis.tables import generate_all_tables
from src.benchmark.experiment import quick_config, build_matrix
from src.benchmark.runner import BenchmarkRunner
from src.metrics.collector import MetricRecord


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate publication-ready plots and benchmark tables from results.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--input",
        metavar="PATH",
        help="Path to raw JSONL or CSV results file. If omitted, runs quick benchmark.",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Run a quick benchmark before generating reports.",
    )
    parser.add_argument(
        "--plots-dir",
        default="plots",
        metavar="DIR",
        help="Directory to save plots (default: plots/)",
    )
    parser.add_argument(
        "--tables-dir",
        default="results/tables",
        metavar="DIR",
        help="Directory to save tables (default: results/tables/)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose DEBUG logging",
    )
    return parser.parse_args()


def _load_records_from_jsonl(path: Path) -> list[MetricRecord]:
    """Load MetricRecord instances from a JSONL file."""
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            r = MetricRecord(**{k: data[k] for k in MetricRecord.__dataclass_fields__ if k in data})
            records.append(r)
    return records


def _load_records_from_csv(path: Path) -> list[dict]:
    """Load records as dicts from a CSV file."""
    import pandas as pd
    df = pd.read_csv(path)
    return df.to_dict(orient="records")


def main() -> int:
    args = _parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    logger = logging.getLogger("generate_reports")

    records = []

    if args.input:
        in_path = Path(args.input)
        if not in_path.exists():
            print(f"ERROR: File not found: {in_path}", file=sys.stderr)
            return 1
        logger.info("Loading records from %s...", in_path)
        if in_path.suffix == ".jsonl":
            records = _load_records_from_jsonl(in_path)
        elif in_path.suffix == ".csv":
            records = _load_records_from_csv(in_path)
        else:
            print(f"ERROR: Unsupported file format {in_path.suffix}. Use .jsonl or .csv", file=sys.stderr)
            return 1
    else:
        logger.info("Running quick benchmark to produce fresh dataset...")
        config = quick_config(repetitions=2, warmup_runs=1)
        matrix = build_matrix(config)
        runner = BenchmarkRunner(config=config, output_dir="data/results")
        runner.run_experiment(matrix)
        records = runner._collector.get_all()

    if not records:
        print("ERROR: No benchmark records available to generate reports.", file=sys.stderr)
        return 1

    print(f"\n{'='*60}")
    print(f"  BENCHMARK REPORT GENERATOR (Stage 9)")
    print(f"{'='*60}")
    print(f"  Records:     {len(records)}")
    print(f"  Plots dir:   {args.plots_dir}")
    print(f"  Tables dir:  {args.tables_dir}")
    print(f"{'='*60}\n")

    # 1. Generate 10 Plots
    print("Generating 10 Research Plots (Matplotlib)...")
    plots = generate_all_plots(records, output_dir=args.plots_dir)
    for name, p in plots.items():
        print(f"  [PLOT] {name:<35} -> {p}")

    print()

    # 2. Generate 7 Benchmark Tables
    print("Generating 7 Benchmark Tables (.csv & .md)...")
    tables = generate_all_tables(records, output_dir=args.tables_dir)
    for name, files in tables.items():
        print(f"  [TABLE] {name:<12} -> {files['md']} | {files['csv']}")

    print(f"\n{'='*60}")
    print("  REPORT GENERATION COMPLETE")
    print(f"{'='*60}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
