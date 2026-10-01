"""
Shared pytest fixtures for the Sterilization Benchmark test suite.

Provides:
  - sample_data: Standard test payload dict.
  - all_serializers: Parametrized fixture over all 3 formats.
  - live_server: A real BenchmarkServer running on a free port (session-scoped).
  - live_client: A BenchmarkClient pointed at the live_server.
"""

import socket
import time
import pytest
import pytest_asyncio

from src.serialization import JSONSerializer, GzipJSONSerializer, MessagePackSerializer
from src.api.server import BenchmarkServer
from src.api.client import BenchmarkClient


def _find_free_port() -> int:
    """Return an available TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ─────────────────────────────────────────────────────────────────────────────
# Data fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def sample_data():
    return {
        "id": 1,
        "name": "benchmark_test",
        "values": [1.1, 2.2, 3.3],
        "nested": {"a": True, "b": None, "c": "hello"},
        "count": 42,
    }


@pytest.fixture(scope="session")
def large_data():
    """~50KB flat dict for throughput tests."""
    from src.data.generator import generate_flat_data
    return generate_flat_data(target_size_kb=50.0, redundancy="medium", seed=1)


# ─────────────────────────────────────────────────────────────────────────────
# Serializer fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def json_ser():
    return JSONSerializer()


@pytest.fixture(scope="session")
def gzip_ser():
    return GzipJSONSerializer()


@pytest.fixture(scope="session")
def msgpack_ser():
    return MessagePackSerializer()


@pytest.fixture(
    scope="session",
    params=[
        pytest.param(JSONSerializer(),        id="json"),
        pytest.param(GzipJSONSerializer(),    id="json_gzip"),
        pytest.param(MessagePackSerializer(), id="messagepack"),
    ],
)
def any_serializer(request):
    """Parametrized fixture providing each serializer in turn."""
    return request.param


# ─────────────────────────────────────────────────────────────────────────────
# Live server fixture (session-scoped — starts once, shared across all tests)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def live_server():
    """
    Start a real BenchmarkServer on a free port.
    Shared across the entire test session (started once, stopped after all tests).
    """
    port = _find_free_port()
    server = BenchmarkServer(host="127.0.0.1", port=port, log_level="error")
    server.start(wait_for_ready_sec=3.0)

    # Extra safety: wait until port is actually accepting connections
    deadline = time.time() + 5.0
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                break
        except OSError:
            time.sleep(0.05)

    yield server
    server.stop()


@pytest.fixture(scope="session")
def live_base_url(live_server) -> str:
    return live_server.base_url


@pytest.fixture
def live_client(live_base_url) -> BenchmarkClient:
    """Return a BenchmarkClient pointed at the live server."""
    return BenchmarkClient(base_url=live_base_url, timeout_sec=15.0)
