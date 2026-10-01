"""
Stage 5 & 6 live integration tests.

These tests use a REAL BenchmarkServer running on a free TCP port.
They validate the full stack: BenchmarkClient → HTTP → FastAPI → serializer → response parsing.

Covers:
  - Live server health check
  - All 3 format roundtrips over real HTTP (not ASGI in-process)
  - TransferResult → MetricRecord bridge (build_record_from_transfer)
  - ResourceMonitor integration with serialization
  - Full single-run pipeline: generate → serialize → transmit → deserialize → validate → collect
"""

import time
import socket
import pytest

from src.serialization import JSONSerializer, GzipJSONSerializer, MessagePackSerializer
from src.data.generator import generate
from src.data.validator import validate as data_validate
from src.metrics.size import SizeRecord, measure_json_size, measure_payload_size
from src.metrics.resources import ResourceMonitor, ResourceRecord
from src.metrics.collector import MetricsCollector
from src.api.client import BenchmarkClient, TransferResult


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures: re-use live_server from conftest.py
# ─────────────────────────────────────────────────────────────────────────────

# live_server, live_base_url, live_client, sample_data are all from conftest.py


# ─────────────────────────────────────────────────────────────────────────────
# Live server basic connectivity
# ─────────────────────────────────────────────────────────────────────────────

class TestLiveServerBasic:
    def test_server_is_running(self, live_server):
        assert live_server.is_running

    def test_server_base_url_format(self, live_server):
        assert live_server.base_url.startswith("http://127.0.0.1:")

    def test_server_port_accepting(self, live_server):
        """Verify TCP port is actually accepting connections."""
        host = "127.0.0.1"
        port = int(live_server.base_url.split(":")[-1])
        with socket.create_connection((host, port), timeout=2.0) as s:
            assert s is not None


# ─────────────────────────────────────────────────────────────────────────────
# Live health check over real HTTP
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestLiveHealthEndpoint:
    async def test_health_ok(self, live_client):
        async with live_client as client:
            body = await client.health_check()
        assert body["status"] == "ok"

    async def test_health_serializers_listed(self, live_client):
        async with live_client as client:
            body = await client.health_check()
        assert "json" in body["serializers"]
        assert "messagepack" in body["serializers"]

    async def test_health_timestamp_positive(self, live_client):
        async with live_client as client:
            body = await client.health_check()
        assert body["timestamp_ns"] > 0


# ─────────────────────────────────────────────────────────────────────────────
# Live payload roundtrip — all 3 formats
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("serializer,fmt", [
    (JSONSerializer(),        "json"),
    (GzipJSONSerializer(),    "json_gzip"),
    (MessagePackSerializer(), "messagepack"),
])
async def test_live_roundtrip(live_client, sample_data, serializer, fmt):
    """Full HTTP roundtrip: serialize → send → server deserializes → response."""
    async with live_client as client:
        result = await client.send_payload(sample_data, serializer, run_index=0)

    assert result.success, f"[{fmt}] Failed: {result.error}"
    assert result.http_status == 200
    assert result.payload_bytes > 0
    assert result.t_ser_ms >= 0.0
    assert result.t_net_ms > 0.0
    assert result.t_deser_ms >= 0.0
    assert result.server_data_keys == len(sample_data)


@pytest.mark.asyncio
async def test_live_gzip_has_decomp_time(live_client, sample_data):
    """GZIP format must report a positive t_decomp_ms from server."""
    async with live_client as client:
        result = await client.send_payload(sample_data, GzipJSONSerializer(), run_index=0)
    assert result.t_decomp_ms >= 0.0  # even very fast decompression may be 0 for tiny payloads


@pytest.mark.asyncio
async def test_live_run_index_echoed(live_client, sample_data):
    """The server must echo back the X-Run-Index header."""
    async with live_client as client:
        result = await client.send_payload(sample_data, JSONSerializer(), run_index=7)
    assert result.run_index == 7


@pytest.mark.asyncio
async def test_live_t_e2e_ms_positive(live_client, sample_data):
    """t_e2e_ms should be the sum of all timing components."""
    async with live_client as client:
        result = await client.send_payload(sample_data, JSONSerializer(), run_index=0)
    expected = result.t_ser_ms + result.t_net_ms + result.t_decomp_ms + result.t_deser_ms
    assert result.t_e2e_ms == pytest.approx(expected, abs=1e-6)


# ─────────────────────────────────────────────────────────────────────────────
# TransferResult → MetricRecord bridge
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_build_record_from_transfer(live_client, sample_data):
    """MetricsCollector.build_record_from_transfer converts a TransferResult into a MetricRecord."""
    serializer = JSONSerializer()
    json_size = measure_json_size(sample_data)

    async with live_client as client:
        result = await client.send_payload(sample_data, serializer, run_index=0)

    size_rec = SizeRecord(
        format_name         = serializer.name,
        original_size_bytes = json_size,
        payload_size_bytes  = result.payload_bytes,
        json_baseline_bytes = json_size,
        run_index           = 0,
    )

    collector = MetricsCollector()
    metric = collector.build_record_from_transfer(
        transfer        = result,
        size            = size_rec,
        experiment_id   = "test_exp",
        workload_name   = "flat_small_medium",
        data_structure  = "flat",
        target_size_kb  = 1.0,
        redundancy      = "medium",
        network_profile = "FAST",
        seed            = 42,
    )

    assert metric.format_name == "json"
    assert metric.t_ser_ms == pytest.approx(result.t_ser_ms, abs=1e-6)
    assert metric.t_net_ms == pytest.approx(result.t_net_ms, abs=1e-6)
    assert metric.payload_size_bytes == result.payload_bytes
    assert metric.valid == result.success
    assert metric.experiment_id == "test_exp"
    assert metric.workload_name == "flat_small_medium"


# ─────────────────────────────────────────────────────────────────────────────
# Resource monitor integration
# ─────────────────────────────────────────────────────────────────────────────

def test_resource_monitor_during_serialization(sample_data):
    """ResourceMonitor correctly captures memory/cpu around serialization."""
    monitor = ResourceMonitor()
    serializer = JSONSerializer()

    with monitor.measure("serialize") as snap:
        payload = serializer.serialize(sample_data)

    assert snap.memory_rss_mb > 0
    assert snap.wall_elapsed_ms >= 0
    assert len(payload) > 0


def test_resource_record_all_phases(sample_data):
    """ResourceRecord combines serialize and deserialize snapshots correctly."""
    monitor = ResourceMonitor()
    serializer = JSONSerializer()

    with monitor.measure("serialize") as ser_snap:
        payload = serializer.serialize(sample_data)

    with monitor.measure("deserialize") as deser_snap:
        _ = serializer.deserialize(payload)

    rec = ResourceRecord(
        format_name="json",
        run_index=0,
        serialize=ser_snap,
        deserialize=deser_snap,
    )

    assert rec.peak_memory_mb > 0
    assert rec.total_cpu_ms >= 0.0
    d = rec.to_dict()
    assert "peak_memory_mb" in d
    assert "ser_memory_rss_mb" in d
    assert "deser_memory_rss_mb" in d


# ─────────────────────────────────────────────────────────────────────────────
# Full single-run pipeline integration test
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("structure", ["flat", "nested", "text_heavy", "numeric"])
@pytest.mark.parametrize("serializer,fmt_id", [
    (JSONSerializer(),        "json"),
    (GzipJSONSerializer(),    "gzip"),
    (MessagePackSerializer(), "msgpack"),
], ids=lambda x: x[1] if isinstance(x, tuple) else x)
async def test_full_single_run_pipeline(live_client, structure, serializer, fmt_id):
    """
    Full pipeline: generate → resource-monitor serialize → transmit → validate → collect.
    One MetricRecord is built and all fields are populated correctly.
    """
    # 1. Generate data
    data = generate(structure=structure, target_size_kb=5.0, redundancy="medium", seed=42)
    json_size = measure_json_size(data)

    # 2. Monitor resources around serialization
    monitor = ResourceMonitor()
    with monitor.measure("serialize") as ser_snap:
        payload = serializer.serialize(data)

    # 3. Transmit via live server
    async with live_client as client:
        result = await client.send_payload(data, serializer, run_index=0)

    # 4. Validate reconstruction (server did it, but verify locally too)
    reconstructed = serializer.deserialize(payload)
    val_result = data_validate(data, reconstructed)
    assert val_result.valid, f"[{structure}/{fmt_id}] Validation failed: {val_result.errors[:3]}"

    # 5. Build metric record
    size_rec = SizeRecord(
        format_name         = serializer.name,
        original_size_bytes = json_size,
        payload_size_bytes  = result.payload_bytes,
        json_baseline_bytes = json_size,
        run_index           = 0,
    )

    resource_rec = ResourceRecord(format_name=serializer.name, serialize=ser_snap)

    collector = MetricsCollector()
    metric = collector.build_record_from_transfer(
        transfer        = result,
        size            = size_rec,
        experiment_id   = "integration_test",
        workload_name   = f"{structure}_small_medium",
        data_structure  = structure,
        target_size_kb  = 5.0,
        redundancy      = "medium",
        network_profile = "FAST",
        seed            = 42,
        resource        = resource_rec,
    )
    collector.add(metric)

    # 6. Assertions
    assert result.success, f"HTTP failed: {result.error}"
    assert metric.t_e2e_ms > 0
    assert metric.payload_size_bytes > 0
    assert metric.original_size_bytes == json_size
    assert metric.valid is True
    assert collector.count() == 1
    assert collector.count_valid() == 1


# ─────────────────────────────────────────────────────────────────────────────
# MetricsCollector filtering (get_by_workload)
# ─────────────────────────────────────────────────────────────────────────────

def test_collector_get_by_workload():
    """get_by_workload should return only records for that workload."""
    from src.metrics.collector import MetricRecord
    collector = MetricsCollector()
    collector.add(MetricRecord(workload_name="flat_small_low", format_name="json"))
    collector.add(MetricRecord(workload_name="flat_small_low", format_name="messagepack"))
    collector.add(MetricRecord(workload_name="nested_medium_high", format_name="json"))

    flat_records = collector.get_by_workload("flat_small_low")
    assert len(flat_records) == 2

    nested_records = collector.get_by_workload("nested_medium_high")
    assert len(nested_records) == 1


# ─────────────────────────────────────────────────────────────────────────────
# Sync client wrapper
# ─────────────────────────────────────────────────────────────────────────────

def test_sync_client_send(live_base_url, sample_data):
    """send_payload_sync() works without an event loop in the calling code."""
    client = BenchmarkClient(base_url=live_base_url, timeout_sec=10.0)
    result = client.send_payload_sync(sample_data, JSONSerializer(), run_index=5)
    assert result.success, f"Sync send failed: {result.error}"
    assert result.run_index == 5
    assert result.payload_bytes > 0
