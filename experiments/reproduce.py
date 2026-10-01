#!/usr/bin/env python3
"""
reproduce.py — Single-configuration benchmark re-runner for verification.

Re-runs a specific (workload, format, profile) combination to verify
timing reproducibility and data integrity. Useful for:
  - Validating a specific result that looks anomalous.
  - Confirming measurement stability across runs.
  - Debugging a particular configuration.

Usage:
    python experiments/reproduce.py \\
        --workload flat_medium_high \\
        --format json \\
        --profile SLOW \\
        --reps 5

    python experiments/reproduce.py \\
        --workload numeric_large_low \\
        --format messagepack \\
        --profile VERY_SLOW \\
        --reps 10 \\
        --warmup 2 \\
        --save

Options:
    --workload  NAME   Workload name (from catalog, e.g. flat_medium_high)
    --format    NAME   Serializer format (json | json_gzip | messagepack)
    --profile   NAME   Network profile (FAST | MODERATE | SLOW | VERY_SLOW)
    --reps      N      Number of measured iterations (default: 5)
    --warmup    N      Number of warmup iterations (default: 1)
    --save             Save results to data/results/raw/ as CSV + JSONL
    --output    PATH   Directory for saved results (default: data/results)
    --verbose          Enable DEBUG logging
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

# Ensure project root is on sys.path when run as a script
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.benchmark.experiment import quick_config
from src.benchmark.runner import BenchmarkRunner
from src.data.workloads import list_workload_names
from src.network.profiles import list_profiles
from src.serialization.registry import list_serializers


# ─────────────────────────────────────────────────────────────────────────────
# CLI argument parsing
# ─────────────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Re-run a specific benchmark configuration for verification.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--workload",
        required=True,
        metavar="NAME",
        help=f"Workload name. Available: {list_workload_names()[:5]}... "
             f"(run `python -c \"from src.data.workloads import list_workload_names; print(list_workload_names())\"` for full list)",
    )
    parser.add_argument(
        "--format",
        required=True,
        dest="format_name",
        metavar="NAME",
        choices=list_serializers(),
        help=f"Serializer format. Choices: {list_serializers()}",
    )
    parser.add_argument(
        "--profile",
        required=True,
        metavar="NAME",
        choices=list_profiles(),
        help=f"Network profile. Choices: {list_profiles()}",
    )
    parser.add_argument(
        "--reps",
        type=int,
        default=5,
        metavar="N",
        help="Number of measured repetitions (default: 5)",
    )
    parser.add_argument(
        "--warmup",
        type=int,
        default=1,
        metavar="N",
        help="Number of warmup iterations (default: 1)",
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="Save results to data/results/raw/ (CSV + JSONL)",
    )
    parser.add_argument(
        "--output",
        default="data/results",
        metavar="PATH",
        help="Root directory for saved results (default: data/results)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable DEBUG logging",
    )
    return parser.parse_args()


# ─────────────────────────────────────────────────────────────────────────────
# Result formatter
# ─────────────────────────────────────────────────────────────────────────────

def _print_results(records, workload: str, format_name: str, profile: str) -> None:
    """Print a per-iteration table and aggregate summary."""
    if not records:
        print("  (no records produced)")
        return

    print(f"\n{'-'*80}")
    print(f"  Configuration: workload={workload!r} | format={format_name!r} | profile={profile!r}")
    print(f"{'-'*80}")
    print(f"  {'Run':>4}  {'t_ser_ms':>10}  {'t_net_ms':>10}  {'t_deser_ms':>11}  "
          f"{'t_e2e_ms':>10}  {'payload_B':>10}  {'valid':>6}")
    print(f"  {'-'*4}  {'-'*10}  {'-'*10}  {'-'*11}  {'-'*10}  {'-'*10}  {'-'*6}")

    for r in records:
        print(
            f"  {r.run_index:>4}  {r.t_ser_ms:>10.4f}  {r.t_net_ms:>10.4f}  "
            f"{r.t_deser_ms:>11.4f}  {r.t_e2e_ms:>10.4f}  "
            f"{r.payload_size_bytes:>10}  {'PASS' if r.valid else 'FAIL':>6}"
        )

    # Aggregate stats
    valid_records = [r for r in records if r.valid]
    n = len(valid_records)
    if n == 0:
        print("\n  [WARN] All runs FAILED validation!")
        return

    import statistics as st

    e2e_values  = [r.t_e2e_ms for r in valid_records]
    ser_values  = [r.t_ser_ms for r in valid_records]
    net_values  = [r.t_net_ms for r in valid_records]
    pay_values  = [r.payload_size_bytes for r in valid_records]
    red_values  = [r.payload_reduction_pct for r in valid_records]

    print(f"\n  {'-'*78}")
    print(f"  AGGREGATE SUMMARY (n={n} valid runs)")
    print(f"  {'-'*78}")
    print(f"  {'Metric':<25}  {'Mean':>10}  {'Min':>10}  {'Max':>10}  {'Std':>10}")
    print(f"  {'-'*25}  {'-'*10}  {'-'*10}  {'-'*10}  {'-'*10}")

    def _row(label, values, fmt=".4f"):
        mean = st.mean(values)
        mn   = min(values)
        mx   = max(values)
        std  = st.stdev(values) if len(values) > 1 else 0.0
        return f"  {label:<25}  {mean:>10{fmt}}  {mn:>10{fmt}}  {mx:>10{fmt}}  {std:>10{fmt}}"

    print(_row("t_e2e_ms",        e2e_values))
    print(_row("  t_ser_ms",      ser_values))
    print(_row("  t_net_ms",      net_values))
    print(_row("payload_size_B",  pay_values, fmt=".1f"))
    print(_row("payload_red_%",   red_values, fmt=".2f"))

    # Validation summary
    all_valid = all(r.valid for r in records)
    valid_count = sum(1 for r in records if r.valid)
    print(f"\n  Validation: {valid_count}/{len(records)} runs passed ({'all valid' if all_valid else 'some failed'})")
    print(f"  Workload size: {records[0].target_size_kb:.1f} KB target | "
          f"JSON baseline: {records[0].json_baseline_bytes:,} B")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> int:
    args = _parse_args()

    log_level = logging.DEBUG if args.verbose else logging.WARNING
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    print(f"\n{'='*60}")
    print(f"  BENCHMARK REPRODUCE")
    print(f"{'='*60}")
    print(f"  Workload:  {args.workload}")
    print(f"  Format:    {args.format_name}")
    print(f"  Profile:   {args.profile}")
    print(f"  Reps:      {args.reps} measured + {args.warmup} warmup")
    print(f"{'='*60}")

    # Build a minimal config
    config = quick_config(repetitions=args.reps, warmup_runs=args.warmup)

    # Validate workload name
    available = list_workload_names()
    if args.workload not in available:
        print(f"\nERROR: Unknown workload {args.workload!r}.", file=sys.stderr)
        print(f"Available workloads:", file=sys.stderr)
        for name in available:
            print(f"  {name}", file=sys.stderr)
        return 1

    # Create runner (no output writer unless --save)
    if not args.save:
        from src.benchmark.result_writer import ResultWriter

        class _NoOpWriter:
            def write_csv(self, *a, **kw): return Path("/dev/null")
            def write_json(self, *a, **kw): return Path("/dev/null")
            def write_run_summary(self, *a, **kw): return Path("/dev/null")

        writer = _NoOpWriter()
    else:
        writer = None  # ResultWriter created automatically in BenchmarkRunner

    runner = BenchmarkRunner(
        config=config,
        output_dir=args.output,
        writer=writer,
    )

    print(f"\n  Running {args.warmup} warmup + {args.reps} measured iterations...")
    t_start = time.perf_counter()

    try:
        records = runner.run_single(
            workload_name=args.workload,
            format_name=args.format_name,
            profile_name=args.profile,
            repetitions=args.reps,
            warmup_runs=args.warmup,
        )
    except KeyError as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        return 1

    elapsed = time.perf_counter() - t_start
    print(f"  Done in {elapsed:.2f}s.\n")

    _print_results(records, args.workload, args.format_name, args.profile)

    # Optional save
    if args.save and records:
        from src.benchmark.result_writer import ResultWriter
        writer = ResultWriter(args.output)
        csv_path  = writer.write_csv(records,  config.experiment_id)
        json_path = writer.write_json(records, config.experiment_id)
        print(f"\n  Results saved:")
        print(f"    CSV:  {csv_path}")
        print(f"    JSONL: {json_path}")

    print()
    return 0 if all(r.valid for r in records) else 1


if __name__ == "__main__":
    sys.exit(main())
