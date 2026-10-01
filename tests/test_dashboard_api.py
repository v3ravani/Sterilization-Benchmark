"""
Tests for Stage 10: Control Dashboard REST API and Static Serving.
"""

import pytest
from fastapi.testclient import TestClient

from src.api.server import app


@pytest.fixture
def client():
    return TestClient(app)


class TestDashboardAPI:
    """Test dashboard backend control endpoints."""

    def test_get_options(self, client):
        resp = client.get("/api/options")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "workloads" in data
        assert "formats" in data
        assert "profiles" in data
        assert "json" in data["formats"]
        assert "FAST" in data["profiles"]

    def test_get_benchmark_status_idle(self, client):
        resp = client.get("/api/benchmark/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert data["status"] in ["idle", "completed", "running"]

    def test_dashboard_static_page_served(self, client):
        resp = client.get("/dashboard/")
        assert resp.status_code == 200
        assert "Serialization Benchmark" in resp.text
        assert "btn-run-benchmark" in resp.text

    def test_dashboard_root_redirect(self, client):
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code in (301, 302, 307)
        assert "/dashboard" in resp.headers["location"]

    def test_get_latest_results_endpoint(self, client):
        resp = client.get("/api/results/latest")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data

    def test_get_benchmark_logs(self, client):
        resp = client.get("/api/benchmark/logs")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert "logs" in data
        assert isinstance(data["logs"], list)

    def test_run_benchmark_validation(self, client):
        resp = client.post("/api/benchmark/run", json={"quick": True, "repetitions": 1, "warmup_runs": 0})
        assert resp.status_code in (200, 409)

    def test_export_results_zip(self, client):
        resp = client.get("/api/results/export")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/zip"
        assert len(resp.content) > 0

    def test_export_results_pdf(self, client):
        resp = client.get("/api/results/export/pdf")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert resp.content.startswith(b"%PDF")

