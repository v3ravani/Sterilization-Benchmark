"""
Tests for Stage 9: Automated Plotting System (src/analysis/plots.py).
"""

import pytest
from pathlib import Path

from src.analysis.plots import PlotGenerator, generate_all_plots
from src.metrics.collector import MetricRecord


@pytest.fixture
def sample_metric_records():
    """Build a realistic set of MetricRecords across 3 formats and 2 profiles."""
    records = []
    formats = [
        ("json", 1.0, 1.0, 20.0, 10000, 10000, 0.0),
        ("json_gzip", 3.0, 2.0, 12.0, 10000, 4000, 60.0),
        ("messagepack", 1.2, 0.9, 18.0, 10000, 8500, 15.0),
    ]
    profiles = [
        ("FAST", 1e9, 0.5),
        ("SLOW", 10e6, 50.0),
    ]

    run_idx = 0
    for w_name, orig_kb in [("flat_small_low", 10), ("nested_medium_medium", 100)]:
        for p_name, bw, lat in profiles:
            for fmt_name, t_ser, t_deser, t_net, orig_b, pay_b, red_pct in formats:
                for rep in range(2):
                    t_decomp = 0.5 if fmt_name == "json_gzip" else 0.0
                    t_comp   = 1.0 if fmt_name == "json_gzip" else 0.0
                    records.append(MetricRecord(
                        experiment_id="test_exp",
                        run_index=run_idx,
                        workload_name=w_name,
                        data_structure="flat" if "flat" in w_name else "nested",
                        target_size_kb=float(orig_kb),
                        redundancy="medium",
                        format_name=fmt_name,
                        network_profile=p_name,
                        original_size_bytes=orig_b,
                        payload_size_bytes=pay_b,
                        json_baseline_bytes=orig_b,
                        t_ser_ms=t_ser,
                        t_net_ms=t_net,
                        t_deser_ms=t_deser,
                        t_comp_ms=t_comp,
                        t_decomp_ms=t_decomp,
                        t_e2e_ms=t_ser + t_net + t_deser + t_comp + t_decomp,
                        t_processing_ms=t_ser + t_deser + t_comp + t_decomp,
                        compression_ratio=pay_b / orig_b if orig_b > 0 else 1.0,
                        payload_reduction_pct=red_pct,
                        peak_memory_mb=1.2,
                        ser_cpu_pct=5.5,
                        deser_cpu_pct=2.0,
                        valid=True,
                    ))
                    run_idx += 1
    return records


class TestPlotGenerator:
    """Test individual plot generators and batch generation."""

    def test_generate_all_plots(self, tmp_path, sample_metric_records):
        out_dir = tmp_path / "plots"
        plots = generate_all_plots(sample_metric_records, output_dir=out_dir)

        assert len(plots) == 10
        for chart_name, path in plots.items():
            assert path.exists(), f"Plot {chart_name} does not exist at {path}"
            assert path.stat().st_size > 500, f"Plot {chart_name} appears empty"
            assert path.suffix == ".png"

    def test_plot_with_empty_records(self, tmp_path):
        out_dir = tmp_path / "plots_empty"
        generator = PlotGenerator(output_dir=out_dir)
        plots = generator.generate_all_plots([])

        assert len(plots) == 10
        for chart_name, path in plots.items():
            assert path.exists()
            assert path.stat().st_size > 0

    def test_plot_categories(self, tmp_path, sample_metric_records):
        out_dir = tmp_path / "plots_cat"
        generator = PlotGenerator(output_dir=out_dir)

        p1 = generator.plot_payload_vs_original(generator._records_to_df(sample_metric_records) if hasattr(generator, '_records_to_df') else None or __import__('src.analysis.plots', fromlist=['_records_to_df'])._records_to_df(sample_metric_records))
        assert "payload" in str(p1.parent)

        p2 = generator.plot_e2e_latency_vs_payload(__import__('src.analysis.plots', fromlist=['_records_to_df'])._records_to_df(sample_metric_records))
        assert "performance" in str(p2.parent)

        p6 = generator.plot_resources_vs_payload(__import__('src.analysis.plots', fromlist=['_records_to_df'])._records_to_df(sample_metric_records))
        assert "resources" in str(p6.parent)

        p10 = generator.plot_2d_decision_boundary(__import__('src.analysis.plots', fromlist=['_records_to_df'])._records_to_df(sample_metric_records))
        assert "breakeven" in str(p10.parent)
