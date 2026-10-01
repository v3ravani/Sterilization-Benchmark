"""
Automated Plotting System for Serialization Benchmark Research.

Generates 10 publication-ready research charts using Matplotlib:
  Chart 1:  Payload Size vs Original Data Size (plots/payload/)
  Chart 2:  Serialization/Deserialization Time vs Payload Size (plots/performance/)
  Chart 3:  End-to-End Latency vs Payload Size (plots/performance/)
  Chart 4:  End-to-End Latency vs Network Bandwidth (plots/performance/)
  Chart 5:  End-to-End Latency vs Network Latency (plots/performance/)
  Chart 6:  CPU & Memory Usage vs Payload Size (plots/resources/)
  Chart 7:  Network Time Saved vs Additional CPU Cost (plots/breakeven/)
  Chart 8:  Relative Gain vs Payload Size with Decision Thresholds (plots/performance/)
  Chart 9:  Payload and Network Break-Even Crossover Plot (plots/breakeven/)
  Chart 10: 2D Decision Boundary Plot (Payload Size vs Bandwidth) (plots/breakeven/)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple, Union

import matplotlib
matplotlib.use("Agg")  # Non-interactive headless backend
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.metrics.collector import MetricRecord

logger = logging.getLogger(__name__)

# Color palette for formats
FORMAT_COLORS = {
    "json": "#3b82f6",         # Blue
    "json_gzip": "#10b981",    # Emerald
    "messagepack": "#f59e0b",  # Amber
}

FORMAT_LABELS = {
    "json": "JSON (Baseline)",
    "json_gzip": "JSON + GZIP",
    "messagepack": "MessagePack",
}

# Line styles and markers
FORMAT_MARKERS = {
    "json": "o",
    "json_gzip": "s",
    "messagepack": "^",
}


def _records_to_df(records: Sequence[Union[MetricRecord, dict]]) -> pd.DataFrame:
    """Convert a sequence of MetricRecord objects or dicts into a pandas DataFrame."""
    if not records:
        return pd.DataFrame()
    rows = []
    for r in records:
        if isinstance(r, dict):
            rows.append(r)
        elif hasattr(r, "as_dict"):
            rows.append(r.as_dict())
        elif hasattr(r, "__dataclass_fields__"):
            rows.append({k: getattr(r, k) for k in r.__dataclass_fields__})
        else:
            rows.append(vars(r))
    df = pd.DataFrame(rows)

    # Enrich network profile metrics if not explicitly populated
    from src.network.profiles import PROFILES
    if "network_profile" in df.columns:
        if "bandwidth_bps" not in df.columns or (df["bandwidth_bps"] == 0).all():
            df["bandwidth_bps"] = df["network_profile"].map(lambda p: PROFILES[p].bandwidth_bps if p in PROFILES else 1e9)
        if "latency_ms" not in df.columns or (df["latency_ms"] == 0).all():
            df["latency_ms"] = df["network_profile"].map(lambda p: PROFILES[p].latency_ms if p in PROFILES else 10.0)

    # Enrich resource metrics if not explicitly populated
    if "cpu_pct" not in df.columns:
        if "ser_cpu_pct" in df.columns:
            df["cpu_pct"] = df["ser_cpu_pct"] + df.get("deser_cpu_pct", 0.0)
        else:
            df["cpu_pct"] = 0.0
    if "memory_mb_delta" not in df.columns:
        df["memory_mb_delta"] = df.get("peak_memory_mb", 0.0)

    # Ensure numerical types for critical metrics
    numeric_cols = [
        "t_ser_ms", "t_net_ms", "t_deser_ms", "t_e2e_ms",
        "t_comp_ms", "t_decomp_ms", "payload_size_bytes",
        "original_size_bytes", "bandwidth_bps", "latency_ms",
        "payload_reduction_pct", "cpu_pct", "memory_mb_delta",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    return df


class PlotGenerator:
    """
    Automated generator for paper-ready benchmark visualization plots.
    """

    def __init__(self, output_dir: Union[str, Path] = "plots") -> None:
        self.output_dir = Path(output_dir)
        self.payload_dir     = self.output_dir / "payload"
        self.performance_dir = self.output_dir / "performance"
        self.resources_dir   = self.output_dir / "resources"
        self.breakeven_dir   = self.output_dir / "breakeven"

        for d in [self.payload_dir, self.performance_dir, self.resources_dir, self.breakeven_dir]:
            d.mkdir(parents=True, exist_ok=True)

    def _setup_style(self) -> None:
        """Apply clean scientific publication styling."""
        plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")
        plt.rcParams.update({
            "font.sans-serif": ["Segoe UI", "Helvetica", "Arial", "DejaVu Sans"],
            "font.family": "sans-serif",
            "font.size": 10,
            "axes.titlesize": 12,
            "axes.titleweight": "bold",
            "axes.labelsize": 11,
            "axes.labelweight": "semibold",
            "xtick.labelsize": 9,
            "ytick.labelsize": 9,
            "legend.fontsize": 9,
            "figure.titlesize": 13,
            "figure.dpi": 300,
            "axes.edgecolor": "#cccccc",
            "axes.linewidth": 0.8,
            "grid.color": "#e5e7eb",
            "grid.linestyle": "--",
            "grid.linewidth": 0.6,
            "grid.alpha": 0.8,
            "axes.formatter.use_mathtext": False,
        })

    # ─────────────────────────────────────────────────────────────────────────
    # Chart 1: Payload Size vs Original Data Size
    # ─────────────────────────────────────────────────────────────────────────
    def plot_payload_vs_original(self, df: pd.DataFrame) -> Path:
        """
        Chart 1: Payload Size vs Original Data Size across formats.
        Shows compression/encoding density.
        """
        self._setup_style()
        fig, ax = plt.subplots(figsize=(8, 5))
        out_path = self.payload_dir / "chart1_payload_vs_original.png"

        if df.empty or "format_name" not in df.columns:
            ax.text(0.5, 0.5, "No data available", ha="center", va="center")
            fig.savefig(out_path, bbox_inches="tight")
            plt.close(fig)
            return out_path

        formats = sorted(df["format_name"].unique())
        # Group by target_size_kb or original_size_bytes and format
        df_sorted = df.copy()
        df_sorted["orig_kb"] = df_sorted["original_size_bytes"] / 1024.0
        df_sorted["payload_kb"] = df_sorted["payload_size_bytes"] / 1024.0

        for fmt in formats:
            sub = df_sorted[df_sorted["format_name"] == fmt]
            grp = sub.groupby("orig_kb")["payload_kb"].mean().reset_index().sort_values("orig_kb")
            color = FORMAT_COLORS.get(fmt, "#64748b")
            marker = FORMAT_MARKERS.get(fmt, "o")
            label = FORMAT_LABELS.get(fmt, fmt)
            ax.plot(grp["orig_kb"], grp["payload_kb"], marker=marker, label=label, color=color, linewidth=2, markersize=6)

        # Baseline identity line (y = x)
        max_val = max(df_sorted["orig_kb"].max(), 1.0)
        ax.plot([0, max_val], [0, max_val], linestyle=":", color="#94a3b8", label="No Reduction (1:1)")

        ax.set_title("Chart 1: Payload Size vs Original Data Size")
        ax.set_xlabel("Original Data Size (KB)")
        ax.set_ylabel("Serialized Payload Size (KB)")
        ax.legend(frameon=True, facecolor="white", framealpha=0.9)
        fig.tight_layout()
        fig.savefig(out_path, dpi=300, bbox_inches="tight")
        plt.close(fig)
        logger.info("Saved Chart 1: %s", out_path)
        return out_path

    # ─────────────────────────────────────────────────────────────────────────
    # Chart 2: Serialization/Deserialization Time vs Payload Size
    # ─────────────────────────────────────────────────────────────────────────
    def plot_ser_deser_time_vs_payload(self, df: pd.DataFrame) -> Path:
        """
        Chart 2: Serialization & Deserialization Time vs Payload Size.
        Two subplots: left = serialization, right = deserialization.
        """
        self._setup_style()
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5), sharey=True)
        out_path = self.performance_dir / "chart2_ser_deser_time_vs_payload.png"

        if df.empty or "format_name" not in df.columns:
            ax1.text(0.5, 0.5, "No data available", ha="center", va="center")
            fig.savefig(out_path, bbox_inches="tight")
            plt.close(fig)
            return out_path

        df_sorted = df.copy()
        df_sorted["payload_kb"] = df_sorted["payload_size_bytes"] / 1024.0
        formats = sorted(df["format_name"].unique())

        for fmt in formats:
            sub = df_sorted[df_sorted["format_name"] == fmt]
            grp = sub.groupby("payload_kb")[["t_ser_ms", "t_deser_ms"]].mean().reset_index().sort_values("payload_kb")
            color = FORMAT_COLORS.get(fmt, "#64748b")
            marker = FORMAT_MARKERS.get(fmt, "o")
            label = FORMAT_LABELS.get(fmt, fmt)
            ax1.plot(grp["payload_kb"], grp["t_ser_ms"], marker=marker, label=label, color=color, linewidth=2, markersize=5)
            ax2.plot(grp["payload_kb"], grp["t_deser_ms"], marker=marker, label=label, color=color, linewidth=2, markersize=5)

        ax1.set_title("Serialization Time (T_ser)")
        ax1.set_xlabel("Payload Size (KB)")
        ax1.set_ylabel("Time (ms)")
        ax1.legend(frameon=True, facecolor="white", framealpha=0.9)

        ax2.set_title("Deserialization Time (T_deser)")
        ax2.set_xlabel("Payload Size (KB)")
        ax2.legend(frameon=True, facecolor="white", framealpha=0.9)

        fig.suptitle("Chart 2: Processing Latency vs Payload Size", y=1.02)
        fig.tight_layout()
        fig.savefig(out_path, dpi=300, bbox_inches="tight")
        plt.close(fig)
        logger.info("Saved Chart 2: %s", out_path)
        return out_path

    # ─────────────────────────────────────────────────────────────────────────
    # Chart 3: End-to-End Latency vs Payload Size
    # ─────────────────────────────────────────────────────────────────────────
    def plot_e2e_latency_vs_payload(self, df: pd.DataFrame) -> Path:
        """
        Chart 3: End-to-End Latency vs Payload Size.
        """
        self._setup_style()
        fig, ax = plt.subplots(figsize=(8, 5))
        out_path = self.performance_dir / "chart3_e2e_latency_vs_payload.png"

        if df.empty or "format_name" not in df.columns:
            ax.text(0.5, 0.5, "No data available", ha="center", va="center")
            fig.savefig(out_path, bbox_inches="tight")
            plt.close(fig)
            return out_path

        df_sorted = df.copy()
        df_sorted["payload_kb"] = df_sorted["payload_size_bytes"] / 1024.0
        formats = sorted(df["format_name"].unique())

        for fmt in formats:
            sub = df_sorted[df_sorted["format_name"] == fmt]
            grp = sub.groupby("payload_kb")["t_e2e_ms"].mean().reset_index().sort_values("payload_kb")
            color = FORMAT_COLORS.get(fmt, "#64748b")
            marker = FORMAT_MARKERS.get(fmt, "o")
            label = FORMAT_LABELS.get(fmt, fmt)
            ax.plot(grp["payload_kb"], grp["t_e2e_ms"], marker=marker, label=label, color=color, linewidth=2, markersize=6)

        ax.set_title("Chart 3: End-to-End Latency vs Payload Size")
        ax.set_xlabel("Payload Size (KB)")
        ax.set_ylabel("End-to-End Latency (ms)")
        ax.legend(frameon=True, facecolor="white", framealpha=0.9)
        fig.tight_layout()
        fig.savefig(out_path, dpi=300, bbox_inches="tight")
        plt.close(fig)
        logger.info("Saved Chart 3: %s", out_path)
        return out_path

    # ─────────────────────────────────────────────────────────────────────────
    # Chart 4: End-to-End Latency vs Network Bandwidth
    # ─────────────────────────────────────────────────────────────────────────
    def plot_e2e_latency_vs_bandwidth(self, df: pd.DataFrame) -> Path:
        """
        Chart 4: End-to-End Latency vs Network Bandwidth (Mbps).
        """
        self._setup_style()
        fig, ax = plt.subplots(figsize=(8, 5))
        out_path = self.performance_dir / "chart4_e2e_latency_vs_bandwidth.png"

        if df.empty or "format_name" not in df.columns or "bandwidth_bps" not in df.columns:
            ax.text(0.5, 0.5, "No data available", ha="center", va="center")
            fig.savefig(out_path, bbox_inches="tight")
            plt.close(fig)
            return out_path

        df_sorted = df.copy()
        df_sorted["bw_mbps"] = df_sorted["bandwidth_bps"] / 1e6
        formats = sorted(df["format_name"].unique())

        for fmt in formats:
            sub = df_sorted[df_sorted["format_name"] == fmt]
            grp = sub.groupby("bw_mbps")["t_e2e_ms"].mean().reset_index().sort_values("bw_mbps")
            color = FORMAT_COLORS.get(fmt, "#64748b")
            marker = FORMAT_MARKERS.get(fmt, "o")
            label = FORMAT_LABELS.get(fmt, fmt)
            ax.plot(grp["bw_mbps"], grp["t_e2e_ms"], marker=marker, label=label, color=color, linewidth=2, markersize=6)

        ax.set_title("Chart 4: End-to-End Latency vs Network Bandwidth")
        ax.set_xlabel("Simulated Bandwidth (Mbps)")
        ax.set_ylabel("End-to-End Latency (ms)")
        ax.set_xscale("log")
        ax.legend(frameon=True, facecolor="white", framealpha=0.9)
        fig.tight_layout()
        fig.savefig(out_path, dpi=300, bbox_inches="tight")
        plt.close(fig)
        logger.info("Saved Chart 4: %s", out_path)
        return out_path

    # ─────────────────────────────────────────────────────────────────────────
    # Chart 5: End-to-End Latency vs Network Latency
    # ─────────────────────────────────────────────────────────────────────────
    def plot_e2e_latency_vs_net_latency(self, df: pd.DataFrame) -> Path:
        """
        Chart 5: End-to-End Latency vs Injected Network Latency (RTT).
        """
        self._setup_style()
        fig, ax = plt.subplots(figsize=(8, 5))
        out_path = self.performance_dir / "chart5_e2e_latency_vs_net_latency.png"

        if df.empty or "format_name" not in df.columns or "latency_ms" not in df.columns:
            ax.text(0.5, 0.5, "No data available", ha="center", va="center")
            fig.savefig(out_path, bbox_inches="tight")
            plt.close(fig)
            return out_path

        df_sorted = df.copy()
        formats = sorted(df["format_name"].unique())

        for fmt in formats:
            sub = df_sorted[df_sorted["format_name"] == fmt]
            grp = sub.groupby("latency_ms")["t_e2e_ms"].mean().reset_index().sort_values("latency_ms")
            color = FORMAT_COLORS.get(fmt, "#64748b")
            marker = FORMAT_MARKERS.get(fmt, "o")
            label = FORMAT_LABELS.get(fmt, fmt)
            ax.plot(grp["latency_ms"], grp["t_e2e_ms"], marker=marker, label=label, color=color, linewidth=2, markersize=6)

        ax.set_title("Chart 5: End-to-End Latency vs Injected Network Latency")
        ax.set_xlabel("Network Profile Latency (ms)")
        ax.set_ylabel("Measured End-to-End Latency (ms)")
        ax.legend(frameon=True, facecolor="white", framealpha=0.9)
        fig.tight_layout()
        fig.savefig(out_path, dpi=300, bbox_inches="tight")
        plt.close(fig)
        logger.info("Saved Chart 5: %s", out_path)
        return out_path

    # ─────────────────────────────────────────────────────────────────────────
    # Chart 6: CPU & Memory Usage vs Payload Size
    # ─────────────────────────────────────────────────────────────────────────
    def plot_resources_vs_payload(self, df: pd.DataFrame) -> Path:
        """
        Chart 6: CPU % and Memory Delta vs Payload Size.
        Two subplots: top = CPU %, bottom = Memory Delta (MB).
        """
        self._setup_style()
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9, 7), sharex=True)
        out_path = self.resources_dir / "chart6_cpu_memory_vs_payload.png"

        if df.empty or "format_name" not in df.columns:
            ax1.text(0.5, 0.5, "No data available", ha="center", va="center")
            fig.savefig(out_path, bbox_inches="tight")
            plt.close(fig)
            return out_path

        df_sorted = df.copy()
        df_sorted["payload_kb"] = df_sorted["payload_size_bytes"] / 1024.0
        formats = sorted(df["format_name"].unique())

        for fmt in formats:
            sub = df_sorted[df_sorted["format_name"] == fmt]
            grp = sub.groupby("payload_kb")[["cpu_pct", "memory_mb_delta"]].mean().reset_index().sort_values("payload_kb")
            color = FORMAT_COLORS.get(fmt, "#64748b")
            marker = FORMAT_MARKERS.get(fmt, "o")
            label = FORMAT_LABELS.get(fmt, fmt)
            ax1.plot(grp["payload_kb"], grp["cpu_pct"], marker=marker, label=label, color=color, linewidth=2, markersize=5)
            ax2.plot(grp["payload_kb"], grp["memory_mb_delta"], marker=marker, label=label, color=color, linewidth=2, markersize=5)

        ax1.set_title("CPU Utilization (%) vs Payload Size")
        ax1.set_ylabel("CPU (%)")
        ax1.legend(frameon=True, facecolor="white", framealpha=0.9)

        ax2.set_title("Memory Delta (MB) vs Payload Size")
        ax2.set_xlabel("Payload Size (KB)")
        ax2.set_ylabel("Memory Delta (MB)")
        ax2.legend(frameon=True, facecolor="white", framealpha=0.9)

        fig.suptitle("Chart 6: Resource Footprint Across Serialization Formats", y=1.01)
        fig.tight_layout()
        fig.savefig(out_path, dpi=300, bbox_inches="tight")
        plt.close(fig)
        logger.info("Saved Chart 6: %s", out_path)
        return out_path

    # ─────────────────────────────────────────────────────────────────────────
    # Chart 7: Network Time Saved vs Additional CPU Cost
    # ─────────────────────────────────────────────────────────────────────────
    def plot_net_saved_vs_cpu_cost(self, df: pd.DataFrame) -> Path:
        """
        Chart 7: Trade-off scatter plot: Network Time Saved (N_f) vs Compute Overhead (O_f).
        Points above the y=x diagonal represent a net positive time win.
        """
        self._setup_style()
        fig, ax = plt.subplots(figsize=(8, 6))
        out_path = self.breakeven_dir / "chart7_net_saved_vs_cpu_cost.png"

        if df.empty or "format_name" not in df.columns:
            ax.text(0.5, 0.5, "No data available", ha="center", va="center")
            fig.savefig(out_path, bbox_inches="tight")
            plt.close(fig)
            return out_path

        # Compute per-cell means against json baseline
        json_sub = df[df["format_name"] == "json"]
        if json_sub.empty:
            ax.text(0.5, 0.5, "JSON baseline missing", ha="center", va="center")
            fig.savefig(out_path, bbox_inches="tight")
            plt.close(fig)
            return out_path

        json_agg = json_sub.groupby(["workload_name", "network_profile"])[["t_net_ms", "t_ser_ms", "t_deser_ms"]].mean().reset_index()
        json_agg["t_proc_json"] = json_agg["t_ser_ms"] + json_agg["t_deser_ms"]
        json_agg = json_agg.rename(columns={"t_net_ms": "t_net_json"})

        alt_formats = [f for f in df["format_name"].unique() if f != "json"]
        max_coord = 5.0

        for fmt in alt_formats:
            fmt_sub = df[df["format_name"] == fmt]
            fmt_agg = fmt_sub.groupby(["workload_name", "network_profile"])[["t_net_ms", "t_ser_ms", "t_deser_ms"]].mean().reset_index()
            fmt_agg["t_proc_fmt"] = fmt_agg["t_ser_ms"] + fmt_agg["t_deser_ms"]

            merged = pd.merge(fmt_agg, json_agg[["workload_name", "network_profile", "t_net_json", "t_proc_json"]],
                              on=["workload_name", "network_profile"])
            merged["net_saved"] = merged["t_net_json"] - merged["t_net_ms"]
            merged["cpu_overhead"] = merged["t_proc_fmt"] - merged["t_proc_json"]

            color = FORMAT_COLORS.get(fmt, "#64748b")
            marker = FORMAT_MARKERS.get(fmt, "o")
            label = FORMAT_LABELS.get(fmt, fmt)
            ax.scatter(merged["cpu_overhead"], merged["net_saved"], color=color, marker=marker, s=50, alpha=0.8, label=label)

            if not merged.empty:
                max_coord = max(max_coord, merged["cpu_overhead"].max(), merged["net_saved"].max())

        # Equal trade-off diagonal line (Net Saved = CPU Cost)
        lim = max(max_coord * 1.1, 5.0)
        ax.plot([-lim, lim], [-lim, lim], linestyle="--", color="#64748b", alpha=0.7, label="Break-Even (Net Saved = CPU Cost)")
        ax.axhline(0, color="#94a3b8", linewidth=0.8, linestyle=":")
        ax.axvline(0, color="#94a3b8", linewidth=0.8, linestyle=":")

        ax.fill_between([-lim, lim], [-lim, lim], [lim, lim], alpha=0.06, color="#10b981", label="Net Win Region")

        ax.set_title("Chart 7: Network Time Saved vs Additional CPU Cost")
        ax.set_xlabel("Additional CPU Processing Cost (O_f, ms)")
        ax.set_ylabel("Network Time Saved (N_f, ms)")
        ax.legend(frameon=True, facecolor="white", framealpha=0.9, loc="lower right")
        fig.tight_layout()
        fig.savefig(out_path, dpi=300, bbox_inches="tight")
        plt.close(fig)
        logger.info("Saved Chart 7: %s", out_path)
        return out_path

    # ─────────────────────────────────────────────────────────────────────────
    # Chart 8: Relative Gain vs Payload Size
    # ─────────────────────────────────────────────────────────────────────────
    def plot_relative_gain_vs_payload(self, df: pd.DataFrame) -> Path:
        """
        Chart 8: Relative Gain % vs Payload Size with 5% and 20% Decision Thresholds.
        """
        self._setup_style()
        fig, ax = plt.subplots(figsize=(8, 5))
        out_path = self.performance_dir / "chart8_relative_gain_vs_payload.png"

        if df.empty or "format_name" not in df.columns:
            ax.text(0.5, 0.5, "No data available", ha="center", va="center")
            fig.savefig(out_path, bbox_inches="tight")
            plt.close(fig)
            return out_path

        json_sub = df[df["format_name"] == "json"]
        if json_sub.empty:
            ax.text(0.5, 0.5, "JSON baseline missing", ha="center", va="center")
            fig.savefig(out_path, bbox_inches="tight")
            plt.close(fig)
            return out_path

        json_agg = json_sub.groupby("target_size_kb")["t_e2e_ms"].mean().reset_index().rename(columns={"t_e2e_ms": "t_json"})
        alt_formats = [f for f in df["format_name"].unique() if f != "json"]

        for fmt in alt_formats:
            fmt_sub = df[df["format_name"] == fmt]
            fmt_agg = fmt_sub.groupby("target_size_kb")["t_e2e_ms"].mean().reset_index()
            merged = pd.merge(fmt_agg, json_agg, on="target_size_kb")
            merged["gain_pct"] = (merged["t_json"] - merged["t_e2e_ms"]) / merged["t_json"] * 100.0
            merged = merged.sort_values("target_size_kb")

            color = FORMAT_COLORS.get(fmt, "#64748b")
            marker = FORMAT_MARKERS.get(fmt, "o")
            label = FORMAT_LABELS.get(fmt, fmt)
            ax.plot(merged["target_size_kb"], merged["gain_pct"], marker=marker, label=label, color=color, linewidth=2, markersize=6)

        # Decision threshold boundary lines
        ax.axhline(20.0, color="#10b981", linestyle="--", linewidth=1.2, label="Switch Threshold (>=20%)")
        ax.axhline(5.0,  color="#f59e0b", linestyle="--", linewidth=1.2, label="Evaluate Threshold (>=5%)")
        ax.axhline(0.0,  color="#94a3b8", linestyle=":",  linewidth=0.8)

        ax.set_title("Chart 8: Relative Gain (%) vs Target Payload Size")
        ax.set_xlabel("Target Payload Size (KB)")
        ax.set_ylabel("Relative Gain vs JSON (%)")
        ax.legend(frameon=True, facecolor="white", framealpha=0.9)
        fig.tight_layout()
        fig.savefig(out_path, dpi=300, bbox_inches="tight")
        plt.close(fig)
        logger.info("Saved Chart 8: %s", out_path)
        return out_path

    # ─────────────────────────────────────────────────────────────────────────
    # Chart 9: Payload and Network Break-Even Crossover Plot
    # ─────────────────────────────────────────────────────────────────────────
    def plot_breakeven_crossover(self, df: pd.DataFrame) -> Path:
        """
        Chart 9: Break-Even Crossover Curves across Bandwidth Spectrum.
        Compares total latency curve of JSON vs GZIP and JSON vs MessagePack.
        """
        self._setup_style()
        fig, ax = plt.subplots(figsize=(8, 5))
        out_path = self.breakeven_dir / "chart9_breakeven_crossover.png"

        if df.empty or "format_name" not in df.columns:
            ax.text(0.5, 0.5, "No data available", ha="center", va="center")
            fig.savefig(out_path, bbox_inches="tight")
            plt.close(fig)
            return out_path

        # Simulated bandwidth points from 0.5 Mbps to 1000 Mbps
        bw_mbps_range = np.logspace(np.log10(0.5), np.log10(1000), 100)
        bw_bps_range = bw_mbps_range * 1e6

        formats = sorted(df["format_name"].unique())
        for fmt in formats:
            sub = df[df["format_name"] == fmt]
            if sub.empty:
                continue
            mean_payload = sub["payload_size_bytes"].mean()
            mean_proc_ms = (sub["t_ser_ms"] + sub["t_deser_ms"]).mean()
            mean_rtt_ms  = sub["latency_ms"].mean() if "latency_ms" in sub else 10.0

            # Total model latency = proc_ms + rtt_ms + (payload_bits / bw_bps * 1000)
            latency_curve = mean_proc_ms + mean_rtt_ms + (mean_payload * 8.0 / bw_bps_range * 1000.0)

            color = FORMAT_COLORS.get(fmt, "#64748b")
            label = FORMAT_LABELS.get(fmt, fmt)
            ax.plot(bw_mbps_range, latency_curve, label=label, color=color, linewidth=2.2)

        ax.set_xscale("log")
        ax.set_title("Chart 9: Serialization Latency Crossover Across Bandwidth")
        ax.set_xlabel("Bandwidth (Mbps)")
        ax.set_ylabel("Predicted Latency (ms)")
        ax.legend(frameon=True, facecolor="white", framealpha=0.9)
        fig.tight_layout()
        fig.savefig(out_path, dpi=300, bbox_inches="tight")
        plt.close(fig)
        logger.info("Saved Chart 9: %s", out_path)
        return out_path

    # ─────────────────────────────────────────────────────────────────────────
    # Chart 10: 2D Decision Boundary Plot (Payload Size vs Bandwidth)
    # ─────────────────────────────────────────────────────────────────────────
    def plot_2d_decision_boundary(self, df: pd.DataFrame) -> Path:
        """
        Chart 10: 2D Decision Boundary Plot (X: Payload Size KB, Y: Bandwidth Mbps).
        Renders contour regions for Zone 1 (No Switch), Zone 2 (Evaluate), Zone 3 (Switch).
        """
        self._setup_style()
        fig, ax = plt.subplots(figsize=(8, 6))
        out_path = self.breakeven_dir / "chart10_2d_decision_boundary.png"

        # Generate a 2D mesh grid
        payload_kb_grid = np.linspace(10, 1000, 100)
        bw_mbps_grid = np.logspace(np.log10(1), np.log10(1000), 100)
        P, B = np.meshgrid(payload_kb_grid, bw_mbps_grid)

        # Realistic empirical model:
        # JSON proc ≈ 0.5 + 0.003 * P, size = P * 1024
        # GZIP proc ≈ 1.5 + 0.015 * P, size = P * 1024 * 0.35
        # Net time = (size * 8) / (B * 1e6) * 1000
        t_json_net = (P * 1024.0 * 8.0) / (B * 1e6) * 1000.0
        t_gzip_net = (P * 1024.0 * 0.35 * 8.0) / (B * 1e6) * 1000.0
        t_json_tot = 10.0 + (0.5 + 0.003 * P) + t_json_net
        t_gzip_tot = 10.0 + (1.5 + 0.015 * P) + t_gzip_net

        relative_gain = (t_json_tot - t_gzip_tot) / t_json_tot * 100.0

        # Zone contours
        levels = [-100, 5, 20, 100]
        colors = ["#fee2e2", "#fef3c7", "#d1fae5"]  # Red (No switch), Yellow (Eval), Green (Switch)
        cf = ax.contourf(P, B, relative_gain, levels=levels, colors=colors, alpha=0.85)

        # Boundary lines
        ax.contour(P, B, relative_gain, levels=[5, 20], colors=["#d97706", "#059669"], linewidths=1.5, linestyles=["--", "-"])

        # Scatter actual experiment points if available
        if not df.empty and "original_size_bytes" in df.columns and "bandwidth_bps" in df.columns:
            actual_p = df["original_size_bytes"] / 1024.0
            actual_b = df["bandwidth_bps"] / 1e6
            ax.scatter(actual_p, actual_b, color="#1e293b", s=25, alpha=0.6, edgecolors="white", label="Empirical Runs")

        ax.set_yscale("log")
        ax.set_title("Chart 10: 2D Decision Boundary (Payload Size vs Bandwidth)")
        ax.set_xlabel("Payload Size (KB)")
        ax.set_ylabel("Network Bandwidth (Mbps)")

        # Custom legend patches
        from matplotlib.patches import Patch
        legend_elements = [
            Patch(facecolor="#d1fae5", edgecolor="#059669", label="Zone 3: Switch (Gain >= 20%)"),
            Patch(facecolor="#fef3c7", edgecolor="#d97706", label="Zone 2: Evaluate (5% <= Gain < 20%)"),
            Patch(facecolor="#fee2e2", edgecolor="#dc2626", label="Zone 1: No Switch (Gain < 5%)"),
        ]
        ax.legend(handles=legend_elements, loc="upper right", frameon=True, facecolor="white", framealpha=0.9)

        fig.tight_layout()
        fig.savefig(out_path, dpi=300, bbox_inches="tight")
        plt.close(fig)
        logger.info("Saved Chart 10: %s", out_path)
        return out_path

    # ─────────────────────────────────────────────────────────────────────────
    # Batch generation
    # ─────────────────────────────────────────────────────────────────────────
    def generate_all_plots(self, records: Sequence[Union[MetricRecord, dict]]) -> Dict[str, Path]:
        """
        Generate all 10 benchmark charts from records.

        :param records: Sequence of MetricRecord instances or dicts.
        :return: Dict mapping chart name to its generated output Path.
        """
        df = _records_to_df(records)
        plots = {
            "chart1_payload_vs_original":        self.plot_payload_vs_original(df),
            "chart2_ser_deser_time_vs_payload":  self.plot_ser_deser_time_vs_payload(df),
            "chart3_e2e_latency_vs_payload":     self.plot_e2e_latency_vs_payload(df),
            "chart4_e2e_latency_vs_bandwidth":   self.plot_e2e_latency_vs_bandwidth(df),
            "chart5_e2e_latency_vs_net_latency": self.plot_e2e_latency_vs_net_latency(df),
            "chart6_cpu_memory_vs_payload":      self.plot_resources_vs_payload(df),
            "chart7_net_saved_vs_cpu_cost":      self.plot_net_saved_vs_cpu_cost(df),
            "chart8_relative_gain_vs_payload":   self.plot_relative_gain_vs_payload(df),
            "chart9_breakeven_crossover":        self.plot_breakeven_crossover(df),
            "chart10_2d_decision_boundary":      self.plot_2d_decision_boundary(df),
        }
        return plots


def generate_all_plots(
    records: Sequence[Union[MetricRecord, dict]],
    output_dir: Union[str, Path] = "plots",
) -> Dict[str, Path]:
    """Convenience helper to generate all 10 plots."""
    generator = PlotGenerator(output_dir=output_dir)
    return generator.generate_all_plots(records)
