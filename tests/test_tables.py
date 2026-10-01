"""
Tests for Stage 9: Automated Benchmark Tables Generator (src/analysis/tables.py).
"""

import pytest
from pathlib import Path

from src.analysis.tables import TableGenerator, generate_all_tables
from src.metrics.collector import MetricRecord


@pytest.fixture
def sample_records():
    records = []
    formats = [
        ("json", 0.5, 0.5, 15.0, 10000, 10000, 0.0),
        ("json_gzip", 2.0, 1.0, 6.0, 10000, 3500, 65.0),
        ("messagepack", 0.8, 0.6, 13.0, 10000, 8000, 20.0),
    ]
    for w_name in ["flat_small_low", "nested_medium_medium"]:
        for p_name in ["FAST", "SLOW"]:
            for fmt, ser, deser, net, orig_b, pay_b, red_pct in formats:
                for rep in range(3):
                    records.append(MetricRecord(
                        experiment_id="test_exp",
                        run_index=rep,
                        workload_name=w_name,
                        data_structure="flat" if "flat" in w_name else "nested",
                        target_size_kb=10.0 if "small" in w_name else 100.0,
                        redundancy="medium",
                        format_name=fmt,
                        network_profile=p_name,
                        original_size_bytes=orig_b,
                        payload_size_bytes=pay_b,
                        json_baseline_bytes=orig_b,
                        t_ser_ms=ser,
                        t_net_ms=net,
                        t_deser_ms=deser,
                        t_comp_ms=0.5 if fmt == "json_gzip" else 0.0,
                        t_decomp_ms=0.2 if fmt == "json_gzip" else 0.0,
                        t_e2e_ms=ser + deser + net,
                        t_processing_ms=ser + deser,
                        compression_ratio=pay_b / orig_b if orig_b > 0 else 1.0,
                        payload_reduction_pct=red_pct,
                        peak_memory_mb=0.8,
                        ser_cpu_pct=4.0,
                        deser_cpu_pct=1.0,
                        valid=True,
                    ))
    return records


class TestTableGenerator:
    """Validate all 7 tables are generated in both .md and .csv format."""

    def test_generate_all_tables(self, tmp_path, sample_records):
        out_dir = tmp_path / "tables"
        tables = generate_all_tables(sample_records, output_dir=out_dir)

        assert len(tables) == 7
        for table_key, files in tables.items():
            csv_path = files["csv"]
            md_path  = files["md"]

            assert csv_path.exists(), f"CSV missing for {table_key}"
            assert md_path.exists(),  f"Markdown missing for {table_key}"

            assert csv_path.stat().st_size > 20
            assert md_path.stat().st_size > 20

            # Content checks
            csv_text = csv_path.read_text(encoding="utf-8")
            md_text  = md_path.read_text(encoding="utf-8")

            assert "\n" in csv_text
            assert "|" in md_text

    def test_table_empty_records(self, tmp_path):
        out_dir = tmp_path / "tables_empty"
        tables = generate_all_tables([], output_dir=out_dir)

        assert len(tables) == 7
        for table_key, files in tables.items():
            assert files["csv"].exists()
            assert files["md"].exists()
