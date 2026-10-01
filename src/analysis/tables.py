"""
Automated Benchmark Tables Generator.

Generates 7 structured, publication-ready benchmark tables exported to results/tables/
in both Markdown (.md) and CSV (.csv) formats:
  Table 1: Experimental Configuration & Dataset Summary
  Table 2: Encoding, Decoding & Compression Benchmark
  Table 3: Payload and Network Transmission Benchmark
  Table 4: End-to-End Performance & Relative Gain Benchmark
  Table 5: Workload & Network Condition Comparative Benchmark
  Table 6: Break-Even and Computational Trade-Off Results
  Table 7: Final Decision Framework Results & Recommendations
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

import pandas as pd

from src.analysis.breakeven import compute_breakeven
from src.analysis.comparison import compare_formats
from src.analysis.decision_model import run_decision_framework
from src.analysis.plots import _records_to_df
from src.analysis.statistics import compute_stats
from src.metrics.collector import MetricRecord

logger = logging.getLogger(__name__)


def _write_table_outputs(df: pd.DataFrame, base_path: Path, title: str) -> Dict[str, Path]:
    """Write DataFrame as both CSV and GitHub Markdown table."""
    base_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path = base_path.with_suffix(".csv")
    md_path  = base_path.with_suffix(".md")

    # CSV output
    df.to_csv(csv_path, index=False)

    # Markdown output
    md_lines = [f"# {title}\n", df.to_markdown(index=False), ""]
    md_path.write_text("\n".join(md_lines), encoding="utf-8")

    return {"csv": csv_path, "md": md_path}


class TableGenerator:
    """
    Generates paper-ready summary and comparison tables.
    """

    def __init__(self, output_dir: Union[str, Path] = "results/tables") -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    # ─────────────────────────────────────────────────────────────────────────
    # Table 1: Experimental Configuration & Dataset Summary
    # ─────────────────────────────────────────────────────────────────────────
    def generate_table1_config_summary(
        self,
        df: pd.DataFrame,
        config: Optional[Any] = None,
    ) -> Dict[str, Path]:
        """Table 1: Experimental Configuration & Dataset Summary."""
        out_base = self.output_dir / "table1_config_dataset_summary"
        rows = []

        if df.empty:
            rows.append({"Workload": "None", "Structure": "None", "Target Size": "0 KB",
                         "Original Bytes": 0, "Formats Tested": "None", "Profiles Tested": "None", "Runs": 0})
        else:
            for w_name, grp in df.groupby("workload_name"):
                target_kb = grp["target_size_kb"].iloc[0] if "target_size_kb" in grp else 0
                orig_bytes = int(grp["original_size_bytes"].mean()) if "original_size_bytes" in grp else 0
                fmts = ", ".join(sorted(grp["format_name"].unique()))
                profs = ", ".join(sorted(grp["network_profile"].unique()))
                struct = w_name.split("_")[0] if "_" in w_name else "general"

                rows.append({
                    "Workload": w_name,
                    "Structure": struct,
                    "Target Size": f"{target_kb:.1f} KB",
                    "Original Bytes": orig_bytes,
                    "Formats Tested": fmts,
                    "Profiles Tested": profs,
                    "Total Measured Runs": len(grp),
                })

        table_df = pd.DataFrame(rows)
        return _write_table_outputs(table_df, out_base, "Table 1: Experimental Configuration & Dataset Summary")

    # ─────────────────────────────────────────────────────────────────────────
    # Table 2: Encoding, Decoding & Compression Benchmark
    # ─────────────────────────────────────────────────────────────────────────
    def generate_table2_encoding_decoding(self, df: pd.DataFrame) -> Dict[str, Path]:
        """Table 2: Encoding, Decoding & Compression Benchmark."""
        out_base = self.output_dir / "table2_encoding_decoding_compression"
        rows = []

        if not df.empty and "format_name" in df.columns:
            for fmt, grp in df.groupby("format_name"):
                n = len(grp)
                ser_mean = grp["t_ser_ms"].mean()
                ser_p95  = grp["t_ser_ms"].quantile(0.95)
                deser_mean = grp["t_deser_ms"].mean()
                deser_p95  = grp["t_deser_ms"].quantile(0.95)
                comp_mean  = grp["t_comp_ms"].mean() if "t_comp_ms" in grp else 0.0
                decomp_mean = grp["t_decomp_ms"].mean() if "t_decomp_ms" in grp else 0.0
                proc_mean = ser_mean + deser_mean + comp_mean + decomp_mean

                rows.append({
                    "Format": fmt,
                    "Samples": n,
                    "T_ser Mean (ms)": round(ser_mean, 4),
                    "T_ser P95 (ms)": round(ser_p95, 4),
                    "T_deser Mean (ms)": round(deser_mean, 4),
                    "T_deser P95 (ms)": round(deser_p95, 4),
                    "T_comp Mean (ms)": round(comp_mean, 4),
                    "T_decomp Mean (ms)": round(decomp_mean, 4),
                    "Total Proc CPU (ms)": round(proc_mean, 4),
                })

        table_df = pd.DataFrame(rows)
        return _write_table_outputs(table_df, out_base, "Table 2: Encoding, Decoding & Compression Benchmark")

    # ─────────────────────────────────────────────────────────────────────────
    # Table 3: Payload and Network Transmission Benchmark
    # ─────────────────────────────────────────────────────────────────────────
    def generate_table3_payload_transmission(self, df: pd.DataFrame) -> Dict[str, Path]:
        """Table 3: Payload and Network Transmission Benchmark."""
        out_base = self.output_dir / "table3_payload_network_transmission"
        rows = []

        if not df.empty and "format_name" in df.columns:
            for (fmt, prof), grp in df.groupby(["format_name", "network_profile"]):
                mean_payload = int(grp["payload_size_bytes"].mean())
                orig_size    = int(grp["original_size_bytes"].mean()) if "original_size_bytes" in grp else mean_payload
                red_pct      = grp["payload_reduction_pct"].mean() if "payload_reduction_pct" in grp else 0.0
                t_net_mean   = grp["t_net_ms"].mean()
                t_net_p95    = grp["t_net_ms"].quantile(0.95)

                rows.append({
                    "Format": fmt,
                    "Profile": prof,
                    "Original Size (B)": orig_size,
                    "Payload Size (B)": mean_payload,
                    "Reduction (%)": round(red_pct, 2),
                    "T_net Mean (ms)": round(t_net_mean, 4),
                    "T_net P95 (ms)": round(t_net_p95, 4),
                })

        table_df = pd.DataFrame(rows)
        return _write_table_outputs(table_df, out_base, "Table 3: Payload and Network Transmission Benchmark")

    # ─────────────────────────────────────────────────────────────────────────
    # Table 4: End-to-End Performance & Relative Gain Benchmark
    # ─────────────────────────────────────────────────────────────────────────
    def generate_table4_e2e_relative_gain(self, df: pd.DataFrame) -> Dict[str, Path]:
        """Table 4: End-to-End Performance & Relative Gain Benchmark."""
        out_base = self.output_dir / "table4_e2e_relative_gain"
        rows = []

        if not df.empty and "format_name" in df.columns:
            # Baseline mean
            json_grp = df[df["format_name"] == "json"]
            json_mean_e2e = json_grp["t_e2e_ms"].mean() if not json_grp.empty else 1.0

            for fmt, grp in df.groupby("format_name"):
                e2e_mean = grp["t_e2e_ms"].mean()
                e2e_p50  = grp["t_e2e_ms"].median()
                e2e_p95  = grp["t_e2e_ms"].quantile(0.95)
                e2e_std  = grp["t_e2e_ms"].std() if len(grp) > 1 else 0.0
                gain_pct = (json_mean_e2e - e2e_mean) / json_mean_e2e * 100.0 if json_mean_e2e > 0 else 0.0

                rows.append({
                    "Format": fmt,
                    "Samples": len(grp),
                    "E2E Mean (ms)": round(e2e_mean, 4),
                    "E2E Median (ms)": round(e2e_p50, 4),
                    "E2E P95 (ms)": round(e2e_p95, 4),
                    "E2E Std (ms)": round(e2e_std, 4),
                    "Relative Gain vs JSON (%)": round(gain_pct, 2),
                })

        table_df = pd.DataFrame(rows)
        return _write_table_outputs(table_df, out_base, "Table 4: End-to-End Performance & Relative Gain Benchmark")

    # ─────────────────────────────────────────────────────────────────────────
    # Table 5: Workload & Network Condition Comparative Benchmark
    # ─────────────────────────────────────────────────────────────────────────
    def generate_table5_workload_network_comparative(self, df: pd.DataFrame) -> Dict[str, Path]:
        """Table 5: Workload & Network Condition Comparative Benchmark."""
        out_base = self.output_dir / "table5_workload_network_comparative"
        rows = []

        if not df.empty and "workload_name" in df.columns and "network_profile" in df.columns:
            for (w_name, prof), grp in df.groupby(["workload_name", "network_profile"]):
                row = {
                    "Workload": w_name,
                    "Profile": prof,
                }
                for fmt in ["json", "json_gzip", "messagepack"]:
                    sub = grp[grp["format_name"] == fmt]
                    if not sub.empty:
                        row[f"{fmt} E2E (ms)"] = round(sub["t_e2e_ms"].mean(), 3)
                        row[f"{fmt} Size (B)"] = int(sub["payload_size_bytes"].mean())
                    else:
                        row[f"{fmt} E2E (ms)"] = "-"
                        row[f"{fmt} Size (B)"] = "-"
                rows.append(row)

        table_df = pd.DataFrame(rows)
        return _write_table_outputs(table_df, out_base, "Table 5: Workload & Network Condition Comparative Benchmark")

    # ─────────────────────────────────────────────────────────────────────────
    # Table 6: Break-Even and Computational Trade-Off Results
    # ─────────────────────────────────────────────────────────────────────────
    def generate_table6_breakeven_tradeoffs(
        self,
        records: Sequence[Union[MetricRecord, dict]],
    ) -> Dict[str, Path]:
        """Table 6: Break-Even and Computational Trade-Off Results."""
        out_base = self.output_dir / "table6_breakeven_computational_tradeoffs"
        rows = []

        # Convert records to MetricRecord objects if needed
        metric_records = []
        for r in records:
            if isinstance(r, MetricRecord):
                metric_records.append(r)
            elif isinstance(r, dict):
                metric_records.append(MetricRecord(**{k: r[k] for k in MetricRecord.__dataclass_fields__ if k in r}))

        if metric_records:
            stats_by_fmt = {
                fmt: compute_stats([r.t_e2e_ms for r in metric_records if r.format_name == fmt], fmt, "t_e2e_ms")
                for fmt in set(r.format_name for r in metric_records)
            }
            pairs = [
                ("json", "messagepack", "json_vs_messagepack"),
                ("json", "json_gzip",    "json_vs_gzip"),
                ("json_gzip", "messagepack", "gzip_vs_messagepack"),
            ]
            for f1, f2, pair_name in pairs:
                if f1 in stats_by_fmt and f2 in stats_by_fmt:
                    be = compute_breakeven(metric_records, pair=pair_name)
                    rows.append({
                        "Comparison Pair": pair_name,
                        "Format A": f1,
                        "Format B": f2,
                        "Break-Even Valid": be.is_valid,
                        "B_BE (Mbps)": round(be.bandwidth_be_mbps, 4) if be.is_valid else "N/A",
                        "Formula Applied": be.formula_used,
                        "Interpretation": be.note,
                    })

        table_df = pd.DataFrame(rows)
        return _write_table_outputs(table_df, out_base, "Table 6: Break-Even and Computational Trade-Off Results")

    # ─────────────────────────────────────────────────────────────────────────
    # Table 7: Final Decision Framework Results & Recommendations
    # ─────────────────────────────────────────────────────────────────────────
    def generate_table7_decision_recommendations(
        self,
        records: Sequence[Union[MetricRecord, dict]],
        thresholds: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Path]:
        """Table 7: Final Decision Framework Results & Recommendations."""
        out_base = self.output_dir / "table7_decision_framework_recommendations"
        rows = []

        metric_records = []
        for r in records:
            if isinstance(r, MetricRecord):
                metric_records.append(r)
            elif isinstance(r, dict):
                metric_records.append(MetricRecord(**{k: r[k] for k in MetricRecord.__dataclass_fields__ if k in r}))

        if metric_records:
            if thresholds is None:
                thresholds = {"no_switch": 0.05, "switch": 0.20}
            decisions = run_decision_framework(metric_records, thresholds=thresholds)
            for d in decisions:
                rows.append({
                    "Format": d.format_name,
                    "Decision Zone": d.zone.value.upper(),
                    "Regime": d.regime.value.upper(),
                    "Relative Gain (%)": round(d.relative_gain_pct, 2),
                    "Net Time Saved (ms)": round(d.network_time_saved_ms, 3),
                    "CPU Overhead (ms)": round(d.compute_overhead_ms, 3),
                    "Recommendation": d.recommendation,
                })

        table_df = pd.DataFrame(rows)
        return _write_table_outputs(table_df, out_base, "Table 7: Final Decision Framework Results & Recommendations")

    # ─────────────────────────────────────────────────────────────────────────
    # Batch generation
    # ─────────────────────────────────────────────────────────────────────────
    def generate_all_tables(
        self,
        records: Sequence[Union[MetricRecord, dict]],
        config: Optional[Any] = None,
    ) -> Dict[str, Dict[str, Path]]:
        """
        Generate all 7 tables in both CSV and Markdown formats.
        """
        df = _records_to_df(records)
        tables = {
            "table1": self.generate_table1_config_summary(df, config),
            "table2": self.generate_table2_encoding_decoding(df),
            "table3": self.generate_table3_payload_transmission(df),
            "table4": self.generate_table4_e2e_relative_gain(df),
            "table5": self.generate_table5_workload_network_comparative(df),
            "table6": self.generate_table6_breakeven_tradeoffs(records),
            "table7": self.generate_table7_decision_recommendations(records),
        }
        return tables


def generate_all_tables(
    records: Sequence[Union[MetricRecord, dict]],
    config: Optional[Any] = None,
    output_dir: Union[str, Path] = "results/tables",
) -> Dict[str, Dict[str, Path]]:
    """Convenience helper to generate all 7 tables."""
    generator = TableGenerator(output_dir=output_dir)
    return generator.generate_all_tables(records, config=config)
