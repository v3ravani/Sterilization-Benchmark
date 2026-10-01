"""
Tests for Stage 5 (HTTP API) and Stage 6 (Metrics Engine).

Stage 5 tests (API):
  - FastAPI server: /health response, /data deserialization for all 3 formats.
  - BenchmarkClient: TransferResult fields, timing, payload bytes.
  - End-to-end: client → server roundtrip for all serializers.

Stage 6 tests (Metrics):
  - PrecisionTimer: context manager, start/stop, elapsed units, history.
  - LatencyRecord: all fields, t_e2e_ms, t_processing_ms, to_dict.
  - LatencyCollector: add, get_by_format, valid filtering, to_dicts.
  - SizeRecord: compression_ratio, payload_reduction, bytes_saved.
  - SizeCollector: add, get_by_format, averages.
  - ResourceSnapshot: all derived properties.
  - ResourceMonitor: context manager captures memory/cpu.
  - ResourceRecord: peak_memory, total_cpu.
  - MetricRecord: all fields, to_dict.
  - MetricsCollector: build_record, add, filter helpers.
"""

import asyncio
import time
import pytest
import pytest_asyncio

# ── Stage 6: Benchmark timer ──────────────────────────────────────────────────
from src.benchmark.timer import PrecisionTimer, TimingRecord, time_call

# ── Stage 6: Metrics modules ──────────────────────────────────────────────────
from src.metrics.latency import LatencyRecord, LatencyCollector
from src.metrics.size import SizeRecord, SizeCollector, measure_json_size, measure_payload_size
from src.metrics.resources import ResourceSnapshot, ResourceRecord, ResourceMonitor
from src.metrics.collector import MetricRecord, MetricsCollector

# ── Stage 5: API modules ──────────────────────────────────────────────────────
from src.api.server import app, BenchmarkServer
from src.api.client import BenchmarkClient, TransferResult
from src.serialization import JSONSerializer, GzipJSONSerializer, MessagePackSerializer

from httpx import AsyncClient, ASGITransport


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_data():
    return {
        "id": 1,
        "name": "benchmark_test",
        "values": [1.1, 2.2, 3.3],
        "nested": {"a": True, "b": None, "c": "hello"},
        "count": 42,
    }


@pytest.fixture
def json_ser():
    return JSONSerializer()


@pytest.fixture
def gzip_ser():
    return GzipJSONSerializer()


@pytest.fixture
def msgpack_ser():
    return MessagePackSerializer()


@pytest.fixture
def asgi_client():
    """In-process HTTPX test client using ASGI transport — no server needed."""
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 6: PrecisionTimer
# ─────────────────────────────────────────────────────────────────────────────

class TestPrecisionTimer:
    def test_measure_returns_record(self):
        timer = PrecisionTimer()
        with timer.measure("test") as t:
            time.sleep(0.001)
        assert t.elapsed_ms >= 0.5

    def test_measure_label(self):
        timer = PrecisionTimer()
        with timer.measure("serialize") as t:
            pass
        assert t.label == "serialize"

    def test_elapsed_ns_positive(self):
        timer = PrecisionTimer()
        with timer.measure() as t:
            time.sleep(0.001)
        assert t.elapsed_ns > 0

    def test_elapsed_ms_unit(self):
        timer = PrecisionTimer()
        with timer.measure() as t:
            time.sleep(0.01)
        assert t.elapsed_ms >= 5.0  # at least 5ms for 10ms sleep

    def test_elapsed_sec_small(self):
        timer = PrecisionTimer()
        with timer.measure() as t:
            pass
        assert t.elapsed_sec < 1.0

    def test_start_stop_ns(self):
        timer = PrecisionTimer()
        timer.start()
        time.sleep(0.001)
        ns = timer.stop_ns()
        assert ns > 100_000  # > 0.1ms

    def test_start_stop_ms(self):
        timer = PrecisionTimer()
        timer.start()
        time.sleep(0.005)
        ms = timer.stop_ms()
        assert ms >= 2.0

    def test_stop_without_start_raises(self):
        timer = PrecisionTimer()
        with pytest.raises(RuntimeError, match="not started"):
            timer.stop_ns()

    def test_history_accumulates(self):
        timer = PrecisionTimer()
        with timer.measure("a"):
            pass
        with timer.measure("b"):
            pass
        assert len(timer.history) == 2
        assert timer.history[0].label == "a"
        assert timer.history[1].label == "b"

    def test_clear_history(self):
        timer = PrecisionTimer()
        with timer.measure():
            pass
        timer.clear_history()
        assert len(timer.history) == 0

    def test_now_ns_increases(self):
        t1 = PrecisionTimer.now_ns()
        time.sleep(0.001)
        t2 = PrecisionTimer.now_ns()
        assert t2 > t1

    def test_time_call_returns_result_and_ms(self):
        result, ms = time_call(lambda: 42)
        assert result == 42
        assert isinstance(ms, float)
        assert ms >= 0.0

    def test_timing_record_repr(self):
        t = TimingRecord(start_ns=0, end_ns=1_000_000, label="ser")
        assert "1.0000ms" in repr(t) or "ms" in repr(t)


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 6: LatencyRecord & LatencyCollector
# ─────────────────────────────────────────────────────────────────────────────

class TestLatencyRecord:
    def test_t_e2e_ms_sum(self):
        r = LatencyRecord(
            format_name="json",
            t_ser_ms=1.0, t_comp_ms=0.5, t_net_ms=10.0,
            t_decomp_ms=0.3, t_deser_ms=0.8,
        )
        assert r.t_e2e_ms == pytest.approx(12.6, abs=1e-6)

    def test_t_processing_excludes_net(self):
        r = LatencyRecord("json", t_ser_ms=1.0, t_comp_ms=0.0, t_net_ms=10.0,
                          t_decomp_ms=0.0, t_deser_ms=0.5)
        assert r.t_processing_ms == pytest.approx(1.5, abs=1e-6)

    def test_to_dict_has_all_keys(self):
        r = LatencyRecord("json", run_index=3)
        d = r.to_dict()
        assert "format" in d
        assert "t_e2e_ms" in d
        assert "run_index" in d
        assert d["run_index"] == 3

    def test_repr_contains_format(self):
        r = LatencyRecord("messagepack")
        assert "messagepack" in repr(r)

    def test_valid_default_true(self):
        r = LatencyRecord("json")
        assert r.valid is True


class TestLatencyCollector:
    def test_add_and_count(self):
        c = LatencyCollector()
        c.add(LatencyRecord("json"))
        c.add(LatencyRecord("messagepack"))
        assert c.count() == 2

    def test_get_by_format(self):
        c = LatencyCollector()
        c.add(LatencyRecord("json"))
        c.add(LatencyRecord("json"))
        c.add(LatencyRecord("messagepack"))
        assert len(c.get_by_format("json")) == 2
        assert len(c.get_by_format("messagepack")) == 1

    def test_get_valid_only(self):
        c = LatencyCollector()
        c.add(LatencyRecord("json", valid=True))
        c.add(LatencyRecord("json", valid=False))
        assert len(c.get_valid_only()) == 1

    def test_e2e_ms_list(self):
        c = LatencyCollector()
        c.add(LatencyRecord("json", t_ser_ms=5.0, t_net_ms=10.0, t_deser_ms=2.0))
        vals = c.e2e_ms_list("json")
        assert len(vals) == 1
        assert vals[0] > 0

    def test_clear(self):
        c = LatencyCollector()
        c.add(LatencyRecord("json"))
        c.clear()
        assert c.count() == 0

    def test_to_dicts(self):
        c = LatencyCollector()
        c.add(LatencyRecord("json"))
        dicts = c.to_dicts()
        assert isinstance(dicts, list)
        assert isinstance(dicts[0], dict)


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 6: SizeRecord & SizeCollector
# ─────────────────────────────────────────────────────────────────────────────

class TestSizeRecord:
    def test_compression_ratio_gzip(self):
        r = SizeRecord("json_gzip", original_size_bytes=1000, payload_size_bytes=400, json_baseline_bytes=1000)
        assert r.compression_ratio == pytest.approx(0.4)

    def test_payload_reduction(self):
        r = SizeRecord("messagepack", original_size_bytes=1000, payload_size_bytes=700, json_baseline_bytes=1000)
        assert r.payload_reduction == pytest.approx(0.3)

    def test_payload_reduction_pct(self):
        r = SizeRecord("messagepack", original_size_bytes=1000, payload_size_bytes=700, json_baseline_bytes=1000)
        assert r.payload_reduction_pct == pytest.approx(30.0)

    def test_bytes_saved(self):
        r = SizeRecord("json_gzip", original_size_bytes=1000, payload_size_bytes=400, json_baseline_bytes=1000)
        assert r.bytes_saved == 600

    def test_overhead_bytes_when_larger(self):
        r = SizeRecord("json", original_size_bytes=1000, payload_size_bytes=1100, json_baseline_bytes=1000)
        assert r.overhead_bytes == 100

    def test_compression_ratio_one_for_json(self):
        r = SizeRecord("json", original_size_bytes=1000, payload_size_bytes=1000, json_baseline_bytes=1000)
        assert r.compression_ratio == pytest.approx(1.0)

    def test_zero_baseline_returns_one(self):
        r = SizeRecord("json", original_size_bytes=0, payload_size_bytes=0, json_baseline_bytes=0)
        assert r.compression_ratio == 1.0

    def test_to_dict_has_all_keys(self):
        r = SizeRecord("json", 1000, 1000, 1000)
        d = r.to_dict()
        assert "payload_size_bytes" in d
        assert "compression_ratio" in d
        assert "payload_reduction_pct" in d

    def test_measure_json_size(self):
        data = {"a": 1, "b": "hello"}
        size = measure_json_size(data)
        assert size > 0
        assert isinstance(size, int)

    def test_measure_payload_size(self):
        assert measure_payload_size(b"hello") == 5


class TestSizeCollector:
    def test_add_and_get_by_format(self):
        c = SizeCollector()
        c.add(SizeRecord("json", 1000, 1000, 1000))
        c.add(SizeRecord("json_gzip", 1000, 400, 1000))
        assert len(c.get_by_format("json")) == 1
        assert len(c.get_by_format("json_gzip")) == 1

    def test_average_payload_size(self):
        c = SizeCollector()
        c.add(SizeRecord("json", 1000, 800, 1000))
        c.add(SizeRecord("json", 1000, 600, 1000))
        avg = c.average_payload_size("json")
        assert avg == pytest.approx(700.0)

    def test_average_compression_ratio(self):
        c = SizeCollector()
        c.add(SizeRecord("json_gzip", 1000, 400, 1000))
        c.add(SizeRecord("json_gzip", 1000, 600, 1000))
        avg = c.average_compression_ratio("json_gzip")
        assert avg == pytest.approx(0.5)


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 6: ResourceSnapshot & ResourceMonitor
# ─────────────────────────────────────────────────────────────────────────────

class TestResourceSnapshot:
    def test_memory_rss_mb_conversion(self):
        s = ResourceSnapshot(memory_end_bytes=50 * 1024 * 1024)
        assert s.memory_rss_mb == pytest.approx(50.0)

    def test_memory_delta_bytes(self):
        s = ResourceSnapshot(memory_start_bytes=100, memory_end_bytes=200)
        assert s.memory_delta_bytes == 100

    def test_memory_delta_mb(self):
        s = ResourceSnapshot(
            memory_start_bytes=10 * 1024 * 1024,
            memory_end_bytes=20 * 1024 * 1024,
        )
        assert s.memory_delta_mb == pytest.approx(10.0)

    def test_cpu_delta_ms(self):
        s = ResourceSnapshot(cpu_start_ms=100.0, cpu_end_ms=110.0)
        assert s.cpu_delta_ms == pytest.approx(10.0)

    def test_wall_elapsed_ms(self):
        s = ResourceSnapshot(wall_start_ns=0, wall_end_ns=10_000_000)
        assert s.wall_elapsed_ms == pytest.approx(10.0)

    def test_cpu_utilization_pct_capped(self):
        # If CPU time > wall time, cap at 100%
        s = ResourceSnapshot(
            cpu_start_ms=0.0, cpu_end_ms=200.0,
            wall_start_ns=0, wall_end_ns=100_000_000,
        )
        assert s.cpu_utilization_pct == pytest.approx(100.0)

    def test_zero_wall_returns_zero_util(self):
        s = ResourceSnapshot(wall_start_ns=0, wall_end_ns=0)
        assert s.cpu_utilization_pct == 0.0

    def test_to_dict_has_all_keys(self):
        s = ResourceSnapshot()
        d = s.to_dict()
        assert "memory_rss_mb" in d
        assert "cpu_delta_ms" in d
        assert "cpu_utilization_pct" in d


class TestResourceMonitor:
    def test_context_manager_populates_snapshot(self):
        monitor = ResourceMonitor()
        with monitor.measure("serialize") as snap:
            _ = [i ** 2 for i in range(10000)]
        assert snap.memory_rss_mb > 0
        assert snap.wall_elapsed_ms >= 0

    def test_phase_label_set(self):
        monitor = ResourceMonitor()
        with monitor.measure("test_phase") as snap:
            pass
        assert snap.phase == "test_phase"

    def test_current_memory_mb_positive(self):
        monitor = ResourceMonitor()
        assert monitor.current_memory_mb() > 0

    def test_wall_end_after_start(self):
        monitor = ResourceMonitor()
        with monitor.measure() as snap:
            time.sleep(0.001)
        assert snap.wall_end_ns > snap.wall_start_ns


class TestResourceRecord:
    def test_peak_memory_across_phases(self):
        snap_a = ResourceSnapshot(memory_end_bytes=100 * 1024 * 1024)
        snap_b = ResourceSnapshot(memory_end_bytes=200 * 1024 * 1024)
        rec = ResourceRecord("json", serialize=snap_a, deserialize=snap_b)
        assert rec.peak_memory_mb == pytest.approx(200.0)

    def test_total_cpu_sum(self):
        snap_a = ResourceSnapshot(cpu_start_ms=0.0, cpu_end_ms=5.0)
        snap_b = ResourceSnapshot(cpu_start_ms=0.0, cpu_end_ms=3.0)
        rec = ResourceRecord("json", serialize=snap_a, deserialize=snap_b)
        assert rec.total_cpu_ms == pytest.approx(8.0)

    def test_no_phases_zero_peak(self):
        rec = ResourceRecord("json")
        assert rec.peak_memory_mb == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 6: MetricRecord & MetricsCollector
# ─────────────────────────────────────────────────────────────────────────────

class TestMetricRecord:
    def test_default_valid_true(self):
        r = MetricRecord()
        assert r.valid is True

    def test_to_dict_all_fields(self):
        r = MetricRecord(format_name="json", t_e2e_ms=15.0, payload_size_bytes=1024)
        d = r.to_dict()
        assert d["format_name"] == "json"
        assert d["t_e2e_ms"] == 15.0
        assert d["payload_size_bytes"] == 1024

    def test_repr_contains_format(self):
        r = MetricRecord(format_name="messagepack")
        assert "messagepack" in repr(r)


class TestMetricsCollector:
    def _make_latency(self, fmt="json", run=0):
        return LatencyRecord(fmt, t_ser_ms=1.0, t_net_ms=10.0, t_deser_ms=0.5, run_index=run)

    def _make_size(self, fmt="json"):
        return SizeRecord(fmt, 1000, 1000, 1000)

    def test_build_record_returns_metric_record(self):
        c = MetricsCollector()
        rec = c.build_record(
            experiment_id="exp_001", workload_name="flat_small_low",
            data_structure="flat", target_size_kb=10.0, redundancy="low",
            network_profile="FAST", run_index=0, seed=42,
            latency=self._make_latency(), size=self._make_size(),
        )
        assert isinstance(rec, MetricRecord)
        assert rec.format_name == "json"

    def test_build_record_latency_fields(self):
        c = MetricsCollector()
        lat = LatencyRecord("json", t_ser_ms=2.0, t_net_ms=8.0, t_deser_ms=1.0)
        rec = c.build_record(
            experiment_id="e", workload_name="w", data_structure="flat",
            target_size_kb=10.0, redundancy="low", network_profile="FAST",
            run_index=0, seed=42, latency=lat, size=self._make_size(),
        )
        assert rec.t_ser_ms == pytest.approx(2.0)
        assert rec.t_net_ms == pytest.approx(8.0)
        assert rec.t_e2e_ms == pytest.approx(11.0)

    def test_build_record_size_fields(self):
        c = MetricsCollector()
        s = SizeRecord("json_gzip", 1000, 400, 1000)
        rec = c.build_record(
            experiment_id="e", workload_name="w", data_structure="flat",
            target_size_kb=10.0, redundancy="low", network_profile="FAST",
            run_index=0, seed=42, latency=self._make_latency("json_gzip"),
            size=s,
        )
        assert rec.compression_ratio == pytest.approx(0.4)
        assert rec.payload_reduction_pct == pytest.approx(60.0)

    def test_add_and_filter(self):
        c = MetricsCollector()
        for fmt in ["json", "json", "messagepack"]:
            lat = self._make_latency(fmt)
            rec = c.build_record("e", "w", "flat", 10.0, "low", "FAST", 0, 42,
                                 lat, self._make_size(fmt))
            c.add(rec)
        assert c.count() == 3
        assert len(c.get_by_format("json")) == 2
        assert len(c.get_by_format("messagepack")) == 1

    def test_get_valid(self):
        c = MetricsCollector()
        c.add(MetricRecord(valid=True))
        c.add(MetricRecord(valid=False))
        assert c.count_valid() == 1

    def test_to_dicts(self):
        c = MetricsCollector()
        c.add(MetricRecord(format_name="json"))
        dicts = c.to_dicts()
        assert isinstance(dicts[0], dict)


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 5: FastAPI routes (using ASGI transport — no live server needed)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestHealthEndpoint:
    async def test_health_returns_200(self, asgi_client):
        resp = await asgi_client.get("/health")
        assert resp.status_code == 200

    async def test_health_status_ok(self, asgi_client):
        resp = await asgi_client.get("/health")
        body = resp.json()
        assert body["status"] == "ok"

    async def test_health_has_serializers(self, asgi_client):
        resp = await asgi_client.get("/health")
        body = resp.json()
        assert "serializers" in body
        assert "json" in body["serializers"]

    async def test_health_has_timestamp(self, asgi_client):
        resp = await asgi_client.get("/health")
        body = resp.json()
        assert "timestamp_ns" in body
        assert body["timestamp_ns"] > 0


@pytest.mark.asyncio
class TestDataEndpointJSON:
    async def test_json_post_returns_200(self, asgi_client, sample_data, json_ser):
        payload = json_ser.serialize(sample_data)
        resp = await asgi_client.post(
            "/data",
            content=payload,
            headers={"X-Serializer-Format": "json"},
        )
        assert resp.status_code == 200

    async def test_json_response_status_ok(self, asgi_client, sample_data, json_ser):
        payload = json_ser.serialize(sample_data)
        body = (await asgi_client.post("/data", content=payload,
                headers={"X-Serializer-Format": "json"})).json()
        assert body["status"] == "ok"

    async def test_json_payload_bytes_reported(self, asgi_client, sample_data, json_ser):
        payload = json_ser.serialize(sample_data)
        body = (await asgi_client.post("/data", content=payload,
                headers={"X-Serializer-Format": "json"})).json()
        assert body["payload_bytes"] == len(payload)

    async def test_json_t_deser_ms_positive(self, asgi_client, sample_data, json_ser):
        payload = json_ser.serialize(sample_data)
        body = (await asgi_client.post("/data", content=payload,
                headers={"X-Serializer-Format": "json"})).json()
        assert body["t_deser_ms"] >= 0.0

    async def test_json_data_keys_correct(self, asgi_client, sample_data, json_ser):
        payload = json_ser.serialize(sample_data)
        body = (await asgi_client.post("/data", content=payload,
                headers={"X-Serializer-Format": "json"})).json()
        assert body["data_keys"] == len(sample_data)


@pytest.mark.asyncio
class TestDataEndpointGzip:
    async def test_gzip_post_returns_200(self, asgi_client, sample_data, gzip_ser):
        payload = gzip_ser.serialize(sample_data)
        resp = await asgi_client.post(
            "/data",
            content=payload,
            headers={"X-Serializer-Format": "json_gzip"},
        )
        assert resp.status_code == 200

    async def test_gzip_t_decomp_ms_positive(self, asgi_client, sample_data, gzip_ser):
        payload = gzip_ser.serialize(sample_data)
        body = (await asgi_client.post("/data", content=payload,
                headers={"X-Serializer-Format": "json_gzip"})).json()
        assert body["t_decomp_ms"] >= 0.0

    async def test_gzip_data_keys_correct(self, asgi_client, sample_data, gzip_ser):
        payload = gzip_ser.serialize(sample_data)
        body = (await asgi_client.post("/data", content=payload,
                headers={"X-Serializer-Format": "json_gzip"})).json()
        assert body["data_keys"] == len(sample_data)


@pytest.mark.asyncio
class TestDataEndpointMessagePack:
    async def test_msgpack_post_returns_200(self, asgi_client, sample_data, msgpack_ser):
        payload = msgpack_ser.serialize(sample_data)
        resp = await asgi_client.post(
            "/data",
            content=payload,
            headers={"X-Serializer-Format": "messagepack"},
        )
        assert resp.status_code == 200

    async def test_msgpack_data_keys_correct(self, asgi_client, sample_data, msgpack_ser):
        payload = msgpack_ser.serialize(sample_data)
        body = (await asgi_client.post("/data", content=payload,
                headers={"X-Serializer-Format": "messagepack"})).json()
        assert body["data_keys"] == len(sample_data)


@pytest.mark.asyncio
class TestDataEndpointErrors:
    async def test_unknown_format_returns_400(self, asgi_client, json_ser, sample_data):
        payload = json_ser.serialize(sample_data)
        resp = await asgi_client.post(
            "/data",
            content=payload,
            headers={"X-Serializer-Format": "protobuf"},
        )
        assert resp.status_code == 400

    async def test_missing_format_header_returns_422(self, asgi_client, sample_data):
        resp = await asgi_client.post("/data", content=b"data")
        assert resp.status_code == 422

    async def test_empty_body_returns_400(self, asgi_client):
        resp = await asgi_client.post(
            "/data",
            content=b"",
            headers={"X-Serializer-Format": "json"},
        )
        assert resp.status_code == 400


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 5: BenchmarkClient (using ASGI transport)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestBenchmarkClientTransfer:
    @pytest.mark.parametrize("serializer", [
        JSONSerializer(),
        GzipJSONSerializer(),
        MessagePackSerializer(),
    ], ids=["json", "json_gzip", "messagepack"])
    async def test_send_payload_succeeds(self, sample_data, serializer):
        """Full roundtrip via ASGI transport for all 3 formats."""
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            timeout=10.0,
        ) as http_client:
            # Manually wire BenchmarkClient internals to use ASGI transport
            from src.api.client import BenchmarkClient
            client = BenchmarkClient.__new__(BenchmarkClient)
            client.base_url = "http://test"
            client.timeout_sec = 10.0
            client._client = http_client
            client._timer = None

            result = await client.send_payload(sample_data, serializer, run_index=1)

        assert result.success, f"Transfer failed: {result.error}"
        assert result.t_ser_ms >= 0.0
        assert result.payload_bytes > 0
        assert result.server_data_keys == len(sample_data)
        assert result.run_index == 1

    async def test_transfer_result_repr(self, sample_data, json_ser):
        r = TransferResult(format_name="json", success=True)
        assert "json" in repr(r)


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 7: ExperimentConfig & ExperimentMatrix
# ─────────────────────────────────────────────────────────────────────────────

from src.benchmark.experiment import (
    ExperimentConfig,
    ExperimentMatrix,
    MatrixCell,
    AnalysisThresholds,
    load_experiment_config,
    build_matrix,
    quick_config,
)
from src.benchmark.runner import BenchmarkRunner, RunSummary
from src.benchmark.result_writer import ResultWriter
from src.data.workloads import WORKLOADS

import tempfile
from pathlib import Path


class TestExperimentConfig:
    def test_load_from_yaml(self):
        config = load_experiment_config("config/experiment.yaml")
        assert config.name != ""
        assert config.repetitions >= 1
        assert config.warmup_runs >= 0

    def test_serializer_names_populated(self):
        config = load_experiment_config("config/experiment.yaml")
        assert "json" in config.serializer_names
        assert "json_gzip" in config.serializer_names
        assert "messagepack" in config.serializer_names

    def test_network_profiles_populated(self):
        config = load_experiment_config("config/experiment.yaml")
        assert len(config.network_profile_names) >= 1

    def test_thresholds_loaded(self):
        config = load_experiment_config("config/experiment.yaml")
        assert 0.0 < config.thresholds.no_switch < config.thresholds.switch <= 1.0

    def test_experiment_id_generated(self):
        config = load_experiment_config("config/experiment.yaml")
        assert len(config.experiment_id) > 0

    def test_total_iterations_per_cell(self):
        config = load_experiment_config("config/experiment.yaml")
        assert config.total_iterations_per_cell == config.warmup_runs + config.repetitions

    def test_invalid_repetitions_raises(self):
        with pytest.raises(ValueError):
            ExperimentConfig(
                name="x", version="1", experiment_id="abc",
                repetitions=0, warmup_runs=1,
                workload_names=[], serializer_names=[], network_profile_names=[],
                gzip_compression_level=6, thresholds=AnalysisThresholds(),
            )

    def test_quick_config_is_subset(self):
        config = quick_config(repetitions=2, warmup_runs=1)
        assert config.repetitions == 2
        assert config.warmup_runs == 1
        assert len(config.workload_names) <= 3


class TestExperimentMatrix:
    def test_matrix_cell_count(self):
        config = quick_config(repetitions=3, warmup_runs=1)
        matrix = build_matrix(config)
        expected_cells = (
            len(config.workload_names)
            * len(config.serializer_names)
            * len(config.network_profile_names)
        )
        assert len(matrix.cells) == expected_cells

    def test_total_runs_formula(self):
        config = quick_config(repetitions=5, warmup_runs=2)
        matrix = build_matrix(config)
        assert matrix.total_runs == len(matrix.cells) * 5

    def test_cell_has_correct_types(self):
        config = quick_config()
        matrix = build_matrix(config)
        cell   = matrix.cells[0]
        assert isinstance(cell.workload.name, str)
        assert isinstance(cell.format_name, str)
        assert isinstance(cell.profile_name, str)

    def test_cell_indices_sequential(self):
        config = quick_config()
        matrix = build_matrix(config)
        for i, cell in enumerate(matrix.cells):
            assert cell.cell_index == i

    def test_all_formats_covered(self):
        config = quick_config()
        matrix = build_matrix(config)
        found_formats = {cell.format_name for cell in matrix.cells}
        assert found_formats == set(config.serializer_names)

    def test_all_profiles_covered(self):
        config = quick_config()
        matrix = build_matrix(config)
        found_profiles = {cell.profile_name for cell in matrix.cells}
        assert found_profiles == set(config.network_profile_names)

    def test_repr_contains_cell_count(self):
        config = quick_config()
        matrix = build_matrix(config)
        assert str(len(matrix.cells)) in repr(matrix)

    def test_unknown_workload_raises(self):
        config = ExperimentConfig(
            name="test", version="1", experiment_id="abc",
            repetitions=1, warmup_runs=0,
            workload_names=["nonexistent_workload"],
            serializer_names=["json"],
            network_profile_names=["FAST"],
            gzip_compression_level=6,
            thresholds=AnalysisThresholds(),
        )
        with pytest.raises(KeyError):
            build_matrix(config)


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 7: BenchmarkRunner
# ─────────────────────────────────────────────────────────────────────────────

class _NoOpWriter:
    """Result writer that discards all output (for runner tests)."""
    def write_csv(self, *a, **kw):  return Path("/dev/null")
    def write_json(self, *a, **kw): return Path("/dev/null")
    def write_run_summary(self, *a, **kw): return Path("/dev/null")


class TestBenchmarkRunner:
    def _make_runner(self):
        config = quick_config(repetitions=3, warmup_runs=1)
        return BenchmarkRunner(config=config, output_dir="data/results", writer=_NoOpWriter())

    def test_run_single_returns_records(self):
        runner  = self._make_runner()
        records = runner.run_single(
            workload_name="flat_small_low",
            format_name="json",
            profile_name="FAST",
            repetitions=3,
            warmup_runs=1,
        )
        assert len(records) == 3

    def test_run_single_record_fields(self):
        runner  = self._make_runner()
        records = runner.run_single("flat_small_low", "json", "FAST", 2, 1)
        r = records[0]
        assert r.format_name     == "json"
        assert r.network_profile == "FAST"
        assert r.workload_name   == "flat_small_low"
        assert r.t_ser_ms        >= 0.0
        assert r.t_net_ms        >= 0.0
        assert r.t_deser_ms      >= 0.0

    def test_run_single_valid_flag(self):
        runner  = self._make_runner()
        records = runner.run_single("flat_small_low", "json", "FAST", 2, 0)
        assert all(r.valid for r in records), "All records should be valid"

    def test_warmup_not_in_results(self):
        """run_single with warmup=2, reps=3 should return exactly 3 records."""
        runner  = self._make_runner()
        records = runner.run_single("flat_small_low", "json", "FAST", 3, 2)
        assert len(records) == 3

    def test_run_index_sequential(self):
        runner  = self._make_runner()
        records = runner.run_single("flat_small_low", "json", "FAST", 3, 0)
        run_indices = [r.run_index for r in records]
        assert sorted(run_indices) == [0, 1, 2]

    def test_payload_size_positive(self):
        runner  = self._make_runner()
        records = runner.run_single("flat_small_low", "json", "FAST", 2, 0)
        for r in records:
            assert r.payload_size_bytes > 0

    def test_json_baseline_bytes_positive(self):
        runner  = self._make_runner()
        records = runner.run_single("flat_small_low", "json", "FAST", 2, 0)
        for r in records:
            assert r.json_baseline_bytes > 0

    def test_gzip_payload_smaller_than_json_for_high_redundancy(self):
        runner = self._make_runner()
        j_recs = runner.run_single("text_medium_high", "json",     "FAST", 3, 0)
        g_recs = runner.run_single("text_medium_high", "json_gzip","FAST", 3, 0)
        j_mean = sum(r.payload_size_bytes for r in j_recs) / len(j_recs)
        g_mean = sum(r.payload_size_bytes for r in g_recs) / len(g_recs)
        assert g_mean < j_mean, "GZIP should produce smaller payloads for high-redundancy data"

    def test_mp_payload_smaller_than_json(self):
        runner = self._make_runner()
        j_recs = runner.run_single("flat_small_low", "json",       "FAST", 3, 0)
        m_recs = runner.run_single("flat_small_low", "messagepack", "FAST", 3, 0)
        j_mean = sum(r.payload_size_bytes for r in j_recs) / len(j_recs)
        m_mean = sum(r.payload_size_bytes for r in m_recs) / len(m_recs)
        assert m_mean < j_mean, "MessagePack should produce smaller payloads than JSON"

    def test_run_experiment_summary(self):
        config = quick_config(repetitions=2, warmup_runs=0)
        # Use only one workload, one format, one profile for speed
        config.__dict__["workload_names"]        = ["flat_small_low"]
        config.__dict__["serializer_names"]      = ["json"]
        config.__dict__["network_profile_names"] = ["FAST"]

        matrix  = build_matrix(config)
        runner  = BenchmarkRunner(config=config, output_dir="data/results", writer=_NoOpWriter())
        summary = runner.run_experiment(matrix)

        assert isinstance(summary, RunSummary)
        assert summary.total_runs == 2
        assert summary.valid_runs == 2
        assert summary.failed_runs == 0

    def test_run_summary_repr(self):
        config  = quick_config(repetitions=1, warmup_runs=0)
        config.__dict__["workload_names"]        = ["flat_small_low"]
        config.__dict__["serializer_names"]      = ["json"]
        config.__dict__["network_profile_names"] = ["FAST"]
        matrix  = build_matrix(config)
        runner  = BenchmarkRunner(config=config, output_dir="data/results", writer=_NoOpWriter())
        summary = runner.run_experiment(matrix)
        assert "RunSummary" in repr(summary)

    def test_concurrent_execution_multi_workers(self):
        config  = quick_config(repetitions=2, warmup_runs=1)
        config.__dict__["workload_names"]        = ["flat_small_low", "nested_small_medium"]
        config.__dict__["serializer_names"]      = ["json", "messagepack"]
        config.__dict__["network_profile_names"] = ["FAST"]
        matrix  = build_matrix(config)
        runner  = BenchmarkRunner(config=config, output_dir="data/results", writer=_NoOpWriter(), max_workers=4)
        summary = runner.run_experiment(matrix)
        assert summary.total_runs == 8
        assert summary.valid_runs == 8
        assert summary.failed_runs == 0

    def test_dataset_cache_reuse(self):
        config  = quick_config(repetitions=1, warmup_runs=0)
        config.__dict__["workload_names"]        = ["nested_small_medium"]
        config.__dict__["serializer_names"]      = ["json", "json_gzip", "messagepack"]
        config.__dict__["network_profile_names"] = ["FAST"]
        matrix  = build_matrix(config)
        runner  = BenchmarkRunner(config=config, output_dir="data/results", writer=_NoOpWriter(), max_workers=1)
        summary = runner.run_experiment(matrix)
        assert summary.valid_runs == 3
        # Ensure only 1 dataset was generated and cached for the workload
        assert len(runner._dataset_cache) == 1


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 7: ResultWriter
# ─────────────────────────────────────────────────────────────────────────────

class TestResultWriter:
    def _make_records(self, n: int = 3) -> list:
        from src.metrics.collector import MetricRecord
        return [
            MetricRecord(
                experiment_id="test_exp",
                workload_name="flat_small_low",
                format_name="json",
                run_index=i,
                t_ser_ms=0.5,
                t_net_ms=10.0,
                t_deser_ms=0.3,
                t_e2e_ms=10.8,
                t_processing_ms=0.8,
                payload_size_bytes=1000,
                json_baseline_bytes=1000,
                valid=True,
            )
            for i in range(n)
        ]

    def test_write_csv_creates_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = ResultWriter(tmpdir)
            records = self._make_records(3)
            path = writer.write_csv(records, "exp001", filename="test.csv")
            assert path.exists()

    def test_write_csv_has_header(self):
        import csv as _csv
        with tempfile.TemporaryDirectory() as tmpdir:
            writer  = ResultWriter(tmpdir)
            records = self._make_records(2)
            path    = writer.write_csv(records, "exp001", filename="test.csv")
            with open(path) as fh:
                reader = _csv.DictReader(fh)
                rows   = list(reader)
            assert len(rows) == 2
            assert "format_name" in reader.fieldnames
            assert "t_e2e_ms"    in reader.fieldnames

    def test_write_csv_column_values(self):
        import csv as _csv
        with tempfile.TemporaryDirectory() as tmpdir:
            writer  = ResultWriter(tmpdir)
            records = self._make_records(1)
            path    = writer.write_csv(records, "exp001", filename="test.csv")
            with open(path) as fh:
                row = list(_csv.DictReader(fh))[0]
            assert row["format_name"] == "json"
            assert float(row["t_e2e_ms"]) == pytest.approx(10.8)

    def test_write_jsonl_creates_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            writer  = ResultWriter(tmpdir)
            records = self._make_records(3)
            path    = writer.write_json(records, "exp001", filename="test.jsonl")
            assert path.exists()

    def test_write_jsonl_line_count(self):
        import json as _json
        with tempfile.TemporaryDirectory() as tmpdir:
            writer  = ResultWriter(tmpdir)
            records = self._make_records(4)
            path    = writer.write_json(records, "exp001", filename="test.jsonl")
            lines   = [l for l in path.read_text().splitlines() if l.strip()]
            assert len(lines) == 4

    def test_write_jsonl_valid_json(self):
        import json as _json
        with tempfile.TemporaryDirectory() as tmpdir:
            writer  = ResultWriter(tmpdir)
            records = self._make_records(2)
            path    = writer.write_json(records, "exp001", filename="test.jsonl")
            for line in path.read_text().splitlines():
                obj = _json.loads(line)
                assert "format_name" in obj

    def test_immutability_raises_on_overwrite_csv(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            writer  = ResultWriter(tmpdir)
            records = self._make_records(1)
            writer.write_csv(records, "exp001", filename="test.csv")
            with pytest.raises(FileExistsError):
                writer.write_csv(records, "exp001", filename="test.csv")

    def test_immutability_raises_on_overwrite_jsonl(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            writer  = ResultWriter(tmpdir)
            records = self._make_records(1)
            writer.write_json(records, "exp001", filename="test.jsonl")
            with pytest.raises(FileExistsError):
                writer.write_json(records, "exp001", filename="test.jsonl")

    def test_empty_records_writes_header_only_csv(self):
        import csv as _csv
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = ResultWriter(tmpdir)
            path   = writer.write_csv([], "exp001", filename="empty.csv")
            with open(path) as fh:
                rows = list(_csv.DictReader(fh))
            assert rows == []

    def test_raw_dir_created_automatically(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = ResultWriter(Path(tmpdir) / "new_output_dir")
            assert writer.raw_dir.exists()

    def test_list_result_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            writer  = ResultWriter(tmpdir)
            records = self._make_records(1)
            writer.write_csv(records,  "exp001", filename="a.csv")
            writer.write_json(records, "exp001", filename="b.jsonl")
            files = writer.list_result_files()
            assert len(files) == 2
