"""
HTTPX-based async benchmark client.

Sends serialized payloads to the benchmark FastAPI server and records:
  - Client-side serialization timestamps
  - Network transmission time (T_net) from dispatch to first byte of response
  - Server-reported decompression and deserialization times
  - Total end-to-end measured wall-clock time

Usage (async):
    async with BenchmarkClient(base_url="http://127.0.0.1:8765") as client:
        result = await client.send_payload(
            data       = my_data_object,
            serializer = json_serializer,
            run_index  = 0,
        )
        print(result.t_net_ms)

Or synchronously:
    client = BenchmarkClient()
    result = client.send_payload_sync(data, serializer, run_index=0)
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Optional, Union

import httpx

from src.serialization.base import BaseSerializer
from src.benchmark.timer import PrecisionTimer


# ─────────────────────────────────────────────────────────────────────────────
# Transfer result container
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TransferResult:
    """
    Complete timing and size result for one client→server payload exchange.

    Attributes:
        format_name:      Serializer format used.
        run_index:        Zero-based run index.
        t_ser_ms:         Client-side serialization time.
        t_net_ms:         Network time (client dispatch → response received).
        t_decomp_ms:      Server-reported decompression time (GZIP only).
        t_deser_ms:       Server-reported deserialization time.
        payload_bytes:    Transmitted payload size in bytes.
        http_status:      HTTP response status code.
        success:          True if HTTP 200 and data_keys > 0.
        server_data_keys: Number of top-level keys/items the server decoded.
        error:            Error message if transfer failed.
    """
    format_name:      str
    run_index:        int   = 0
    t_ser_ms:         float = 0.0
    t_net_ms:         float = 0.0
    t_decomp_ms:      float = 0.0
    t_deser_ms:       float = 0.0
    payload_bytes:    int   = 0
    http_status:      int   = 0
    success:          bool  = False
    server_data_keys: int   = 0
    error:            str   = ""

    @property
    def t_e2e_ms(self) -> float:
        """End-to-end client time = ser + net + (decomp + deser from server)."""
        return self.t_ser_ms + self.t_net_ms + self.t_decomp_ms + self.t_deser_ms

    def __repr__(self) -> str:
        return (
            f"TransferResult(format={self.format_name!r}, "
            f"run={self.run_index}, e2e={self.t_e2e_ms:.3f}ms, "
            f"payload={self.payload_bytes}B, ok={self.success})"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Benchmark Client
# ─────────────────────────────────────────────────────────────────────────────

class BenchmarkClient:
    """
    Async HTTPX client for benchmark payload transmission.

    Handles serialization, header construction, timing measurement,
    and server response parsing in one call.
    """

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8765",
        timeout_sec: float = 30.0,
    ):
        self.base_url    = base_url.rstrip("/")
        self.timeout_sec = timeout_sec
        self._client: Optional[httpx.AsyncClient] = None
        self._timer = PrecisionTimer()

    # ── Async context manager ────────────────────────────────────────────────

    async def __aenter__(self) -> "BenchmarkClient":
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout_sec,
        )
        return self

    async def __aexit__(self, *args) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    # ── Health check ─────────────────────────────────────────────────────────

    async def health_check(self) -> dict:
        """
        Perform a GET /health request and return the response body.

        :raises httpx.HTTPError: If the server is unreachable.
        """
        client = self._get_client()
        resp = await client.get("/health")
        resp.raise_for_status()
        return resp.json()

    # ── Payload transmission ──────────────────────────────────────────────────

    async def send_payload(
        self,
        data:       Union[dict, list],
        serializer: BaseSerializer,
        run_index:  int = 0,
    ) -> TransferResult:
        """
        Serialize data and send it to POST /data.

        Measures:
          - T_ser  : client-side serialization time
          - T_net  : wall-clock from request dispatch to full response received
          - T_decomp, T_deser: from server response JSON

        :param data:       Application data object to send.
        :param serializer: Serializer instance to use.
        :param run_index:  Zero-based run index for traceability.
        :return:           Populated TransferResult.
        """
        result = TransferResult(
            format_name=serializer.name,
            run_index=run_index,
        )

        # ── Serialize ────────────────────────────────────────────────────────
        t0 = time.perf_counter_ns()
        try:
            payload = serializer.serialize(data)
        except Exception as e:
            result.error = f"Serialization failed: {e}"
            return result
        result.t_ser_ms     = (time.perf_counter_ns() - t0) / 1_000_000.0
        result.payload_bytes = len(payload)

        # ── Transmit ─────────────────────────────────────────────────────────
        headers = {
            "Content-Type":         "application/octet-stream",
            "X-Serializer-Format":  serializer.name,
            "X-Run-Index":          str(run_index),
        }

        client = self._get_client()
        t0 = time.perf_counter_ns()
        try:
            response = await client.post(
                "/data",
                content=payload,
                headers=headers,
            )
        except Exception as e:
            result.error = f"HTTP request failed: {e}"
            return result
        result.t_net_ms     = (time.perf_counter_ns() - t0) / 1_000_000.0
        result.http_status  = response.status_code

        # ── Parse server response ─────────────────────────────────────────────
        if response.status_code != 200:
            result.error = f"HTTP {response.status_code}: {response.text[:200]}"
            return result

        try:
            body = response.json()
            result.t_decomp_ms      = float(body.get("t_decomp_ms", 0.0))
            result.t_deser_ms       = float(body.get("t_deser_ms", 0.0))
            result.server_data_keys = int(body.get("data_keys", 0))
            result.success          = body.get("status") == "ok"
        except Exception as e:
            result.error = f"Response parse failed: {e}"

        return result

    # ── Synchronous wrapper ───────────────────────────────────────────────────

    def send_payload_sync(
        self,
        data:       Union[dict, list],
        serializer: BaseSerializer,
        run_index:  int = 0,
    ) -> TransferResult:
        """
        Synchronous wrapper around send_payload.

        Creates a temporary event loop for blocking contexts (e.g. tests,
        non-async benchmark runners).

        :param data:       Application data object.
        :param serializer: Serializer to use.
        :param run_index:  Zero-based run index.
        :return:           Populated TransferResult.
        """
        return asyncio.run(self._send_once(data, serializer, run_index))

    async def _send_once(
        self,
        data:       Union[dict, list],
        serializer: BaseSerializer,
        run_index:  int,
    ) -> TransferResult:
        """Internal helper: opens a fresh async client, sends, and closes."""
        async with BenchmarkClient(
            base_url=self.base_url,
            timeout_sec=self.timeout_sec,
        ) as client:
            return await client.send_payload(data, serializer, run_index)

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError(
                "BenchmarkClient must be used as an async context manager "
                "or via send_payload_sync()."
            )
        return self._client
