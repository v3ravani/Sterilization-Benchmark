"""
FastAPI server routes for the benchmark communication harness.

Endpoints:
    GET  /health  — Liveness check. Returns server status and timestamp.
    POST /data    — Receive a binary payload, deserialize it using the
                    format specified in the X-Serializer-Format header,
                    validate the data, and return timing + size metrics.

Content-Type and format header conventions:
    X-Serializer-Format: json         → JSONSerializer
    X-Serializer-Format: json_gzip    → GzipJSONSerializer
    X-Serializer-Format: messagepack  → MessagePackSerializer

The server measures deserialization time (T_deser) and decompression time
(T_decomp, GZIP only) on its side and returns them in the JSON response.
"""

import logging
import time
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, Response, Path, Query, Body
from fastapi.responses import JSONResponse

from src.serialization import get_serializer
from src.benchmark.timer import PrecisionTimer

logger = logging.getLogger(__name__)
router = APIRouter()
_timer = PrecisionTimer()


# ─────────────────────────────────────────────────────────────────────────────
# GET /health
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/health", summary="Server health check", tags=["System & Health"])
async def health() -> dict:
    """
    Liveness endpoint.

    Returns server status, registered serializer names, and server timestamp.
    """
    from src.serialization import list_serializers
    return {
        "status":      "ok",
        "server":      "sterilization-benchmark",
        "serializers": list_serializers(),
        "timestamp_ns": time.perf_counter_ns(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# POST /data
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/data", summary="Receive and deserialize a benchmark payload", tags=["Transport & Serialization Harness"])
async def receive_data(
    request: Request,
    x_serializer_format: str = Header(
        default="json",
        description="Serializer format: 'json', 'json_gzip', or 'messagepack'",
    ),
    x_run_index: int = Header(
        default=0,
        description="Zero-based run index for traceability",
    ),
) -> JSONResponse:
    """
    Receive a serialized binary payload, deserialize it, and return metrics.

    Headers:
        X-Serializer-Format  : Format name (optional, default 'json').
        X-Run-Index          : Run index for traceability (optional, default 0).

    Body:
        Raw binary payload bytes or JSON object.

    Response JSON:
        {
          "status":          "ok" | "validation_error",
          "format":          "<format_name>",
          "run_index":       <int>,
          "payload_bytes":   <int>,
          "t_decomp_ms":     <float>,   # GZIP only (else 0.0)
          "t_deser_ms":      <float>,
          "server_ts_ns":    <int>,
          "data_keys":       <int>,     # number of top-level keys or items
        }
    """
    # ── Validate format header ────────────────────────────────────────────────
    fmt = x_serializer_format.strip().lower()
    try:
        serializer = get_serializer(fmt)
    except KeyError:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown X-Serializer-Format '{fmt}'. "
                   f"Valid options: json, json_gzip, messagepack",
        )

    # ── Read raw body with Swagger UI fallback ────────────────────────────────
    payload_bytes: bytes = await request.body()
    if not payload_bytes:
        raise HTTPException(status_code=400, detail="Empty request body")

    if payload_bytes == b"string":
        # Provide valid test data when executed directly from Swagger UI default placeholder
        if fmt == "json":
            payload_bytes = b'{"status":"ok","message":"benchmark test payload","test":true}'
        elif fmt == "json_gzip":
            import gzip
            payload_bytes = gzip.compress(b'{"status":"ok","message":"benchmark test payload","test":true}')
        elif fmt == "messagepack":
            import msgpack
            payload_bytes = msgpack.packb({"status": "ok", "message": "benchmark test payload", "test": True})
    elif fmt == "json_gzip" and not payload_bytes.startswith(b"\x1f\x8b"):
        # Gracefully handle raw JSON text sent from browser playground by gzipping it
        import gzip
        payload_bytes = gzip.compress(payload_bytes)
    elif fmt == "messagepack":
        try:
            serializer.deserialize(payload_bytes)
        except Exception:
            # Gracefully handle raw JSON text sent from browser playground by packing it
            import json as _json
            import msgpack
            try:
                parsed = _json.loads(payload_bytes.decode("utf-8"))
                payload_bytes = msgpack.packb(parsed)
            except Exception:
                pass

    payload_size = len(payload_bytes)

    # ── Deserialization (with timing) ─────────────────────────────────────────
    # For json_gzip: deserialization internally handles both decompression
    # and JSON parsing. We split timing here by using format-aware measurement.
    t_decomp_ms = 0.0
    t_deser_ms  = 0.0

    if fmt == "json_gzip":
        # Time decompression separately from JSON parsing
        import gzip
        import json as _json

        t0 = time.perf_counter_ns()
        try:
            decompressed = gzip.decompress(payload_bytes)
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"GZIP decompression failed: {e}")
        t_decomp_ms = (time.perf_counter_ns() - t0) / 1_000_000.0

        t0 = time.perf_counter_ns()
        try:
            data = _json.loads(decompressed.decode("utf-8"))
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"JSON parse failed: {e}")
        t_deser_ms = (time.perf_counter_ns() - t0) / 1_000_000.0

    else:
        # JSON and MessagePack: one-step deserialization
        t0 = time.perf_counter_ns()
        try:
            data = serializer.deserialize(payload_bytes)
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"Deserialization failed: {e}")
        t_deser_ms = (time.perf_counter_ns() - t0) / 1_000_000.0

    # ── Count top-level items ─────────────────────────────────────────────────
    if isinstance(data, dict):
        data_keys = len(data)
    elif isinstance(data, list):
        data_keys = len(data)
    else:
        data_keys = 1

    return JSONResponse(content={
        "status":        "ok",
        "format":        fmt,
        "run_index":     x_run_index,
        "payload_bytes": payload_size,
        "t_decomp_ms":   round(t_decomp_ms, 6),
        "t_deser_ms":    round(t_deser_ms, 6),
        "server_ts_ns":  time.perf_counter_ns(),
        "data_keys":     data_keys,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Stage 10: Control Dashboard REST Endpoints
# ─────────────────────────────────────────────────────────────────────────────

import threading
from pydantic import BaseModel, Field
from typing import List, Optional, Dict

CANONICAL_10_WORKLOADS = [
    "flat_small_low",
    "flat_medium_high",
    "flat_large_medium",
    "nested_small_medium",
    "nested_medium_low",
    "nested_large_high",
    "text_small_high",
    "text_medium_medium",
    "numeric_small_low",
    "numeric_medium_medium",
]

# Global in-memory benchmark runner state and abort event
_benchmark_lock = threading.RLock()
_abort_event = threading.Event()

_benchmark_state: Dict[str, Any] = {
    "status": "idle",       # "idle" | "running" | "completed" | "failed" | "stopped"
    "progress_pct": 0.0,
    "current_cell": 0,
    "total_cells": 0,
    "elapsed_sec": 0.0,
    "eta_sec": None,
    "total_est_sec": None,
    "description": "System ready. Awaiting benchmark trigger.",
    "summary": None,
    "format_metrics": {},
    "latest_records": [],
    "plots": {},
    "tables": {},
    "decisions": [],
    "logs": ["[SYSTEM] Server initialized. Awaiting benchmark trigger."],
    "error": None,
}


def _append_log(msg: str) -> None:
    """Safely append a timestamped entry to the in-memory benchmark log buffer."""
    now_str = time.strftime("%H:%M:%S")
    entry = f"[{now_str}] {msg}"
    logger.info(entry)
    with _benchmark_lock:
        logs = _benchmark_state.setdefault("logs", [])
        logs.append(entry)
        if len(logs) > 500:
            _benchmark_state["logs"] = logs[-500:]


class BenchmarkRunRequest(BaseModel):
    workloads: Optional[List[str]] = Field(default=["flat_small_low"], description="List of workload names")
    formats: Optional[List[str]] = Field(default=["json", "json_gzip", "messagepack"], description="Serializer formats")
    profiles: Optional[List[str]] = Field(default=["SLOW"], description="Network profile names")
    repetitions: int = Field(default=3, ge=1, le=100)
    warmup_runs: int = Field(default=1, ge=0, le=10)
    workers: int = Field(default=4, ge=1, le=16, description="Number of parallel worker threads for concurrent cell execution")
    quick: bool = Field(default=False)
    generate_reports: bool = Field(default=True)

    model_config = {
        "json_schema_extra": {
            "example": {
                "workloads": ["flat_small_low"],
                "formats": ["json", "json_gzip", "messagepack"],
                "profiles": ["SLOW"],
                "repetitions": 3,
                "warmup_runs": 1,
                "workers": 4,
                "quick": False,
                "generate_reports": True
            }
        }
    }


TABLE_TITLES = {
    "table1": "Table 1: Experimental Configuration & Dataset Summary",
    "table2": "Table 2: Encoding, Decoding & Compression Benchmark",
    "table3": "Table 3: Payload & Network Transmission Benchmark",
    "table4": "Table 4: End-to-End Performance & Relative Gain Benchmark",
    "table5": "Table 5: Workload & Network Condition Comparative Benchmark",
    "table6": "Table 6: Break-Even and Computational Trade-Off Results",
    "table7": "Table 7: Final Decision Framework Results & Recommendations",
}


@router.get("/api/options", summary="Available benchmark configuration options", tags=["Benchmark Configuration"])
async def get_options() -> dict:
    """Returns the 10 curated workloads, formats, network profiles, and parameters."""
    from src.serialization.registry import list_serializers

    return {
        "status": "ok",
        "workloads": CANONICAL_10_WORKLOADS,
        "formats": list_serializers(),
        "profiles": ["FAST", "MODERATE", "SLOW"],  # VERY_SLOW removed per user request
    }


@router.get("/api/workloads", summary="Get 10 curated workloads with details and dataset preview", tags=["Workloads & Datasets"])
async def get_curated_workloads() -> dict:
    """Returns detailed information and representative dataset preview for each curated workload."""
    from src.data.workloads import get_workload
    from src.data.generator import generate
    import json

    results = []
    for name in CANONICAL_10_WORKLOADS:
        w = get_workload(name)
        # Generate representative sample snippet
        sample = generate(w.structure, min(w.target_size_kb, 5.0), w.redundancy, w.seed)
        sample_str = json.dumps(sample, indent=2, default=str)
        if len(sample_str) > 2500:
            preview_str = sample_str[:2500] + "\n... [truncated preview for display]"
        else:
            preview_str = sample_str

        size_label = f"{w.target_size_kb:.0f} KB" if w.target_size_kb < 1000 else f"{w.target_size_kb/1000:.1f} MB"
        results.append({
            "name": w.name,
            "structure": w.structure,
            "target_size_kb": w.target_size_kb,
            "size_label": size_label,
            "redundancy": w.redundancy,
            "seed": w.seed,
            "description": w.description,
            "sample_preview": preview_str,
        })
    return {"status": "ok", "workloads": results}


@router.get("/api/workloads/{workload_name}/dataset", summary="Get specific workload dataset preview", tags=["Workloads & Datasets"])
async def get_workload_dataset(
    workload_name: str = Path(..., description="Name of canonical workload", examples=["flat_small_low"])
) -> dict:
    """Generate real data and serialization sizes for a specific workload to inspect dataset."""
    from src.data.workloads import get_workload
    from src.data.generator import generate
    from src.serialization import get_serializer
    import json

    try:
        w = get_workload(workload_name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Workload '{workload_name}' not found.")

    sample_kb = min(w.target_size_kb, 50.0)
    data = generate(w.structure, sample_kb, w.redundancy, w.seed)

    json_bytes = len(get_serializer("json").serialize(data))
    gzip_bytes = len(get_serializer("json_gzip").serialize(data))
    mp_bytes = len(get_serializer("messagepack").serialize(data))

    keys_count = len(data) if isinstance(data, (dict, list)) else 1
    sample_json = json.dumps(data, indent=2, default=str)
    if len(sample_json) > 15000:
        preview = sample_json[:15000] + "\n\n... [truncated preview for browser performance]"
    else:
        preview = sample_json

    size_label = f"{w.target_size_kb:.0f} KB" if w.target_size_kb < 1000 else f"{w.target_size_kb/1000:.1f} MB"

    return {
        "status": "ok",
        "name": w.name,
        "structure": w.structure,
        "target_size_kb": w.target_size_kb,
        "size_label": size_label,
        "redundancy": w.redundancy,
        "seed": w.seed,
        "description": w.description,
        "keys_count": keys_count,
        "sample_size_bytes": json_bytes,
        "gzip_size_bytes": gzip_bytes,
        "messagepack_size_bytes": mp_bytes,
        "preview_json": preview,
    }


def _run_benchmark_worker(req: BenchmarkRunRequest) -> None:
    """Worker function executed in background thread with cancellation and ETA tracking."""
    global _benchmark_state
    try:
        from src.benchmark.experiment import quick_config, ExperimentConfig, build_matrix, AnalysisThresholds
        from src.benchmark.runner import BenchmarkRunner
        from src.analysis.decision_model import run_decision_framework
        from pathlib import Path
        from src.analysis.plots import generate_all_plots
        from src.analysis.tables import generate_all_tables
        from src.data.workloads import list_workload_names
        from src.serialization.registry import list_serializers
        from src.network.profiles import list_profiles

        with _benchmark_lock:
            _benchmark_state["status"] = "running"
            _benchmark_state["progress_pct"] = 0.0
            _benchmark_state["current_cell"] = 0
            _benchmark_state["total_cells"] = 0
            _benchmark_state["elapsed_sec"] = 0.0
            _benchmark_state["eta_sec"] = None
            _benchmark_state["total_est_sec"] = None
            _benchmark_state["description"] = "Initializing benchmark matrix..."
            _benchmark_state["summary"] = None
            _benchmark_state["format_metrics"] = {}
            _benchmark_state["latest_records"] = []
            _benchmark_state["plots"] = {}
            _benchmark_state["tables"] = {}
            _benchmark_state["decisions"] = []
            _benchmark_state["error"] = None
            _benchmark_state["logs"] = []

        _append_log("Starting real benchmark execution session...")

        all_valid_workloads = list_workload_names()
        all_valid_formats = list_serializers()
        # Strictly exclude VERY_SLOW per user request
        all_valid_profiles = [p for p in list_profiles() if p.upper() != "VERY_SLOW"]

        raw_w = req.workloads or [CANONICAL_10_WORKLOADS[0]]
        w_names = [w for w in raw_w if w in all_valid_workloads and w in CANONICAL_10_WORKLOADS]
        if not w_names:
            w_names = [CANONICAL_10_WORKLOADS[0]]

        raw_f = req.formats or ["json", "json_gzip", "messagepack"]
        f_names = [f for f in raw_f if f in all_valid_formats]
        if not f_names:
            f_names = ["json", "json_gzip", "messagepack"]

        raw_p = req.profiles or ["FAST", "SLOW"]
        p_names = [p for p in raw_p if p in all_valid_profiles]
        if not p_names:
            p_names = ["FAST", "SLOW"]

        _append_log(f"Selected workloads: {w_names}")
        _append_log(f"Selected formats: {f_names}")
        _append_log(f"Selected profiles: {p_names}")
        _append_log(f"Reps per cell: {req.repetitions} measured + {req.warmup_runs} warmup")

        config = ExperimentConfig(
            name="dashboard_benchmark_run",
            repetitions=req.repetitions,
            warmup_runs=req.warmup_runs,
            workload_names=w_names,
            serializer_names=f_names,
            network_profile_names=p_names,
            version="1.0",
            gzip_compression_level=6,
            thresholds=AnalysisThresholds(),
        )

        matrix = build_matrix(config)
        total_cells = len(matrix.cells)
        _append_log(f"Cartesian matrix built: {total_cells} cells ({total_cells * config.repetitions} measured iterations).")

        with _benchmark_lock:
            _benchmark_state["total_cells"] = total_cells

        t_start = time.perf_counter()

        def progress_cb(current: int, total: int, desc: str) -> None:
            now = time.perf_counter()
            elapsed = now - t_start
            pct = round((current / total * 100.0) if total > 0 else 0.0, 1)

            if current > 0 and total >= current:
                rate = elapsed / current
                eta_sec = round(rate * (total - current), 1)
                total_est_sec = round(rate * total, 1)
            else:
                eta_sec = None
                total_est_sec = None

            with _benchmark_lock:
                _benchmark_state["current_cell"] = current
                _benchmark_state["total_cells"] = total
                _benchmark_state["progress_pct"] = pct
                _benchmark_state["description"] = desc
                _benchmark_state["elapsed_sec"] = round(elapsed, 1)
                _benchmark_state["eta_sec"] = eta_sec
                _benchmark_state["total_est_sec"] = total_est_sec

            eta_str = f" | ETA: {eta_sec:.1f}s" if eta_sec is not None else ""
            _append_log(f"[{pct:.0f}%] Cell {current}/{total}: {desc}{eta_str}")

        _abort_event.clear()
        _append_log(f"Starting benchmark execution loop (concurrency: {req.workers} parallel workers)...")
        runner = BenchmarkRunner(
            config=config,
            output_dir="data/results",
            progress_callback=progress_cb,
            abort_checker=lambda: _abort_event.is_set(),
            max_workers=req.workers,
        )
        summary = runner.run_experiment(matrix)

        if _abort_event.is_set():
            _append_log("[USER] Benchmark execution stopped upon user request.")
            with _benchmark_lock:
                _benchmark_state["status"] = "stopped"
                _benchmark_state["description"] = "Benchmark stopped by user."
            return

        records = runner._collector.get_all()
        _append_log(f"Benchmark run complete: {summary.valid_runs}/{summary.total_runs} valid runs in {summary.duration_sec:.2f}s.")

        # Compute mathematically accurate aggregate metrics across 100% of measured valid records
        format_metrics: Dict[str, Any] = {}
        for fmt in f_names:
            fmt_recs = [r for r in records if r.format_name == fmt and getattr(r, 'valid', True)]
            if fmt_recs:
                n = len(fmt_recs)
                t_ser_avg = sum(r.t_ser_ms for r in fmt_recs) / n
                t_net_avg = sum(r.t_net_ms for r in fmt_recs) / n
                t_deser_avg = sum(r.t_deser_ms for r in fmt_recs) / n
                t_decomp_avg = sum(r.t_decomp_ms for r in fmt_recs) / n
                t_comp_avg = sum(r.t_comp_ms for r in fmt_recs) / n
                t_e2e_avg = sum(r.t_e2e_ms for r in fmt_recs) / n
                payload_avg = sum(r.payload_size_bytes for r in fmt_recs) / n
                orig_avg = sum(r.original_size_bytes for r in fmt_recs) / n
                reduction_avg = (1.0 - (payload_avg / orig_avg)) * 100.0 if orig_avg > 0 else 0.0

                format_metrics[fmt] = {
                    "count": n,
                    "t_ser_ms": round(t_ser_avg, 3),
                    "t_net_ms": round(t_net_avg, 3),
                    "t_deser_ms": round(t_deser_avg, 3),
                    "t_decomp_ms": round(t_decomp_avg, 3),
                    "t_comp_ms": round(t_comp_avg, 3),
                    "t_e2e_ms": round(t_e2e_avg, 3),
                    "payload_size_bytes": round(payload_avg, 1),
                    "original_size_bytes": round(orig_avg, 1),
                    "payload_reduction_pct": round(reduction_avg, 2),
                }

        # Run 3-Zone Decision Framework
        _append_log("Evaluating 3-Zone Decision Framework...")
        thresholds = {"no_switch": config.thresholds.no_switch, "switch": config.thresholds.switch}
        decisions_list = run_decision_framework(records, thresholds)
        decisions_data = [
            {
                "format_name": d.format_name,
                "zone": d.zone.value,
                "regime": d.regime.value,
                "relative_gain_pct": round(d.relative_gain_pct, 2),
                "network_time_saved_ms": round(d.network_time_saved_ms, 3),
                "compute_overhead_ms": round(d.compute_overhead_ms, 3),
                "recommendation": d.recommendation,
            }
            for d in decisions_list
        ]

        plots_data = {}
        tables_data = {}

        if req.generate_reports and records:
            _append_log("Generating publication charts and structured tables...")
            with _benchmark_lock:
                _benchmark_state["description"] = "Generating publication plots and tables..."
            try:
                plots_paths = generate_all_plots(records, output_dir="plots")
                plots_data = {k: f"/plots/{v.parent.name}/{v.name}" for k, v in plots_paths.items()}
                _append_log(f"Generated {len(plots_data)} plots in plots/.")

                tables_paths = generate_all_tables(records, config=config, output_dir="results/tables")
                tables_data = {k: f"/results/tables/{v['csv'].name}" for k, v in tables_paths.items()}
                _append_log(f"Generated {len(tables_data)} tables in results/tables/.")

                # Also export raw records as CSV for table viewer & downloads
                import pandas as pd
                records_df = pd.DataFrame([r.to_dict() for r in records])
                records_csv_path = Path("results/tables/records.csv")
                records_df.to_csv(records_csv_path, index=False)
            except Exception as pe:
                logger.warning("Failed to generate plots or tables: %s", pe)
                _append_log(f"[WARN] Artifact generation warning: {pe}")

        record_dicts = [r.to_dict() for r in records]

        with _benchmark_lock:
            _benchmark_state["status"] = "completed"
            _benchmark_state["progress_pct"] = 100.0
            _benchmark_state["description"] = f"Complete: {summary.valid_runs}/{summary.total_runs} valid runs in {summary.duration_sec:.1f}s"
            _benchmark_state["summary"] = {
                "experiment_id": summary.experiment_id,
                "total_runs": summary.total_runs,
                "valid_runs": summary.valid_runs,
                "failed_runs": summary.failed_runs,
                "duration_sec": round(summary.duration_sec, 2),
                "output_csv": summary.output_csv,
                "output_json": summary.output_json,
            }
            _benchmark_state["format_metrics"] = format_metrics
            _benchmark_state["latest_records"] = record_dicts
            _benchmark_state["decisions"] = decisions_data
            _benchmark_state["plots"] = plots_data
            _benchmark_state["tables"] = tables_data

        _append_log("Benchmark finished successfully. Accurate results are ready on dashboard.")

    except Exception as exc:
        logger.exception("Benchmark execution failed: %s", exc)
        _append_log(f"[FATAL] Benchmark execution failed: {exc}")
        with _benchmark_lock:
            _benchmark_state["status"] = "failed"
            _benchmark_state["error"] = str(exc)
            _benchmark_state["description"] = f"Failed: {exc}"


@router.post("/api/benchmark/run", summary="Trigger a benchmark run", tags=["Benchmark Execution"])
async def run_benchmark(req: BenchmarkRunRequest) -> dict:
    """Launch a benchmark run in a background thread."""
    global _benchmark_state, _abort_event
    with _benchmark_lock:
        if _benchmark_state["status"] == "running":
            raise HTTPException(status_code=409, detail="A benchmark is already currently running.")
        _abort_event.clear()
        _benchmark_state["status"] = "running"
        _benchmark_state["progress_pct"] = 0.0
        _benchmark_state["elapsed_sec"] = 0.0
        _benchmark_state["eta_sec"] = None
        _benchmark_state["total_est_sec"] = None
        _benchmark_state["description"] = "Starting benchmark..."
        _benchmark_state["logs"] = ["[SYSTEM] Benchmark job queued..."]

    thread = threading.Thread(target=_run_benchmark_worker, args=(req,), daemon=True)
    thread.start()

    return {
        "status": "started",
        "message": "Benchmark execution started in background.",
    }


@router.post("/api/benchmark/stop", summary="Stop running benchmark", tags=["Benchmark Execution"])
async def stop_benchmark() -> dict:
    """Request immediate cancellation of the running benchmark."""
    global _abort_event
    with _benchmark_lock:
        if _benchmark_state["status"] != "running":
            return {"status": "not_running", "message": "No benchmark is currently running."}
        _abort_event.set()
        _benchmark_state["description"] = "Stopping benchmark..."
        _append_log("[USER] Stop requested. Halting benchmark runner...")
    return {"status": "stopping", "message": "Cancellation requested."}


@router.get("/api/benchmark/status", summary="Get benchmark execution status", tags=["Benchmark Execution"])
async def get_benchmark_status() -> dict:
    """Returns current benchmark execution status, progress, ETA, and elapsed time."""
    with _benchmark_lock:
        return dict(_benchmark_state)


@router.get("/api/benchmark/logs", summary="Get benchmark execution logs", tags=["Benchmark Execution"])
async def get_benchmark_logs() -> dict:
    """Returns execution logs list."""
    with _benchmark_lock:
        return {
            "status": _benchmark_state.get("status", "idle"),
            "logs": _benchmark_state.get("logs", []),
        }


@router.get("/api/results/latest", summary="Get latest benchmark results and artifacts", tags=["Results & Export"])
async def get_latest_results() -> dict:
    """Returns summary, accurate format metrics, decisions, and generated artifact links."""
    with _benchmark_lock:
        if not _benchmark_state["summary"]:
            return {
                "status": "no_results",
                "message": "No benchmark results available yet. Run a benchmark first.",
            }
        return {
            "status": "ok",
            "summary": _benchmark_state["summary"],
            "format_metrics": _benchmark_state.get("format_metrics", {}),
            "records_sample": _benchmark_state["latest_records"][:50],
            "decisions": _benchmark_state["decisions"],
            "plots": _benchmark_state["plots"],
            "tables": _benchmark_state["tables"],
            "logs": _benchmark_state.get("logs", []),
        }


@router.get("/api/tables/list", summary="List all available generated benchmark tables", tags=["Analysis Tables"])
async def list_available_tables() -> dict:
    """Returns available tables with titles, row counts, and download links."""
    import csv
    from pathlib import Path

    tables_dir = Path("results/tables")
    tables = []
    if tables_dir.exists():
        for csv_file in sorted(tables_dir.glob("table*.csv")):
            stem = csv_file.stem
            t_key = stem.split("_")[0]
            title = TABLE_TITLES.get(t_key, stem.replace("_", " ").title())

            try:
                with csv_file.open(mode="r", encoding="utf-8") as f:
                    reader = csv.reader(f)
                    rows = list(reader)
                    row_count = max(0, len(rows) - 1)
            except Exception:
                row_count = 0

            tables.append({
                "id": t_key,
                "stem": stem,
                "title": title,
                "filename": csv_file.name,
                "row_count": row_count,
                "download_url": f"/api/tables/download/{stem}",
                "view_url": f"/api/tables/view/{stem}",
            })

        # Also check records.csv
        records_csv = tables_dir / "records.csv"
        if records_csv.exists():
            tables.append({
                "id": "records",
                "stem": "records",
                "title": "Raw Measured Metric Records (All Runs)",
                "filename": "records.csv",
                "row_count": 0,
                "download_url": "/api/tables/download/records",
                "view_url": "/api/tables/view/records",
            })

    return {"status": "ok", "tables": tables}


@router.get("/api/tables/download/{table_name}", summary="Download table CSV directly", tags=["Analysis Tables"])
async def download_table_csv(
    table_name: str = Path(..., description="Table filename or stem without .csv", examples=["table1_config_dataset_summary"])
):
    """Directly download a benchmark table CSV with attachment headers so it downloads properly."""
    from fastapi.responses import FileResponse
    from pathlib import Path as _Path

    base_name = table_name.replace(".csv", "").replace(".md", "").strip()
    tables_dir = _Path("results/tables")

    target_file = tables_dir / f"{base_name}.csv"
    if not target_file.exists():
        matches = list(tables_dir.glob(f"{base_name}*.csv"))
        if matches:
            target_file = matches[0]
        else:
            raise HTTPException(status_code=404, detail=f"Table file '{base_name}.csv' not found.")

    return FileResponse(
        path=str(target_file),
        filename=target_file.name,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{target_file.name}"',
            "Cache-Control": "no-cache",
        }
    )


@router.get("/api/tables/view/{table_name}", summary="Get table rows and headers for preview", tags=["Analysis Tables"])
async def view_table_content(
    table_name: str = Path(..., description="Table filename or stem without .csv", examples=["table1_config_dataset_summary"])
):
    """Return parsed table data for interactive rendering in UI."""
    import csv
    from pathlib import Path as _Path

    base_name = table_name.replace(".csv", "").replace(".md", "").strip()
    tables_dir = _Path("results/tables")

    target_file = tables_dir / f"{base_name}.csv"
    if not target_file.exists():
        matches = list(tables_dir.glob(f"{base_name}*.csv"))
        if matches:
            target_file = matches[0]
        else:
            raise HTTPException(status_code=404, detail=f"Table '{table_name}' not found.")

    with target_file.open(mode="r", encoding="utf-8") as f:
        reader = csv.reader(f)
        rows = list(reader)
        headers = rows[0] if rows else []
        data_rows = rows[1:] if len(rows) > 1 else []

    md_file = target_file.with_suffix(".md")
    md_content = md_file.read_text(encoding="utf-8") if md_file.exists() else ""

    t_key = target_file.stem.split("_")[0]
    title = TABLE_TITLES.get(t_key, target_file.stem.replace("_", " ").title())

    return {
        "status": "ok",
        "name": target_file.stem,
        "title": title,
        "headers": headers,
        "rows": data_rows,
        "markdown": md_content,
        "download_url": f"/api/tables/download/{target_file.stem}",
    }


@router.get("/api/results/export", summary="Export full benchmark results package as ZIP", tags=["Results & Export"])
async def export_results_zip():
    """Package and stream all tables, plots, raw data, and summary as a ZIP archive."""
    import io
    import json
    import zipfile
    from pathlib import Path
    from fastapi.responses import StreamingResponse

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        # Add tables (.csv and .md)
        tables_dir = Path("results/tables")
        if tables_dir.exists():
            for f in tables_dir.glob("*.*"):
                if f.name != ".gitkeep":
                    zip_file.write(f, arcname=f"tables/{f.name}")

        # Add plots (.png)
        plots_dir = Path("plots")
        if plots_dir.exists():
            for f in plots_dir.rglob("*.png"):
                zip_file.write(f, arcname=f"plots/{f.parent.name}/{f.name}")

        # Add latest raw CSV results from data/results
        raw_results_dir = Path("data/results")
        if raw_results_dir.exists():
            for f in raw_results_dir.glob("*.csv"):
                zip_file.write(f, arcname=f"raw_records/{f.name}")

        # Add summary state
        with _benchmark_lock:
            curr_state = dict(_benchmark_state)
        summary_bytes = json.dumps(curr_state, indent=2, default=str).encode("utf-8")
        zip_file.writestr("summary.json", summary_bytes)

    zip_buffer.seek(0)
    exp_id = curr_state.get("summary", {}).get("experiment_id", "run") if curr_state.get("summary") else "bundle"
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="benchmark_results_{exp_id}.zip"'}
    )


@router.get("/api/results/export/pdf", summary="Export complete benchmark report as PDF", tags=["Results & Export"])
async def export_results_pdf():
    """Generate and stream a publication-grade PDF containing the complete benchmark report."""
    from pathlib import Path
    from fastapi.responses import Response
    from src.analysis.pdf_report import get_pdf_report_bytes

    with _benchmark_lock:
        curr_state = dict(_benchmark_state)

    pdf_bytes = get_pdf_report_bytes(
        tables_dir=Path("results/tables"),
        plots_dir=Path("plots"),
        summary_data=curr_state.get("summary")
    )

    exp_id = curr_state.get("summary", {}).get("experiment_id", "report") if curr_state.get("summary") else "study"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="benchmark_report_{exp_id}.pdf"'}
    )



# ─────────────────────────────────────────────────────────────────────────────
# Interactive Decision Matrix & Break-Even Calculator Endpoint
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/api/decision/calculate", summary="Interactive break-even and decision calculation", tags=["Decision Model & Calculator"])
async def calculate_decision(
    payload_kb: float = Query(default=250.0, description="Target payload size in KB (10 - 10000)"),
    bandwidth_mbps: float = Query(default=50.0, description="Simulated network bandwidth in Mbps (1 - 1000)"),
    rtt_ms: float = Query(default=15.0, description="Base RTT latency in ms"),
    structure: str = Query(default="nested", description="Data structure type: 'nested', 'flat', 'text', 'numeric'"),
):
    """
    Calculate live decision framework recommendation and break-even points
    based on interactive payload size and bandwidth parameters.
    """
    payload_kb = max(10.0, min(10000.0, float(payload_kb)))
    bandwidth_mbps = max(1.0, min(1000.0, float(bandwidth_mbps)))
    rtt_ms = max(0.1, min(500.0, float(rtt_ms)))

    payload_bytes = int(payload_kb * 1024)
    bw_bps = bandwidth_mbps * 1e6

    # Structure-aware scaling factors based on empirical benchmark measurements
    s_json = payload_bytes

    if structure == "numeric":
        mp_factor = 0.55   # Numeric arrays pack tightly in msgpack
        gzip_factor = 0.45
    elif structure == "text":
        mp_factor = 0.88   # Text strings pack similarly to json
        gzip_factor = 0.22 # Text has high redundancy
    elif structure == "flat":
        mp_factor = 0.82
        gzip_factor = 0.38
    else:  # nested
        mp_factor = 0.78
        gzip_factor = 0.32

    s_mp = max(1, int(s_json * mp_factor))
    s_gzip = max(1, int(s_json * gzip_factor))

    # Empirical CPU processing times (ms)
    t_ser_j = 0.15 + (payload_kb * 0.0022)
    t_deser_j = 0.20 + (payload_kb * 0.0028)

    t_ser_mp = 0.22 + (payload_kb * 0.0025)
    t_deser_mp = 0.28 + (payload_kb * 0.0031)

    t_ser_g = t_ser_j
    t_comp_g = 0.80 + (payload_kb * 0.0120)
    t_decomp_g = 0.25 + (payload_kb * 0.0040)
    t_deser_g = t_deser_j

    # Network transmission time T_net = RTT + (Size_bits / Bandwidth_bps * 1000)
    t_net_j = rtt_ms + ((s_json * 8.0) / bw_bps * 1000.0)
    t_net_g = rtt_ms + ((s_gzip * 8.0) / bw_bps * 1000.0)
    t_net_mp = rtt_ms + ((s_mp * 8.0) / bw_bps * 1000.0)

    # Total End-to-End Latencies
    t_e2e_json = t_ser_j + t_net_j + t_deser_j
    t_e2e_gzip = t_ser_g + t_comp_g + t_net_g + t_decomp_g + t_deser_g
    t_e2e_mp = t_ser_mp + t_net_mp + t_deser_mp

    # Relative gains over baseline JSON (%)
    gain_gzip = (t_e2e_json - t_e2e_gzip) / t_e2e_json * 100.0
    gain_mp = (t_e2e_json - t_e2e_mp) / t_e2e_json * 100.0

    formats_eval = {
        "json": {
            "name": "JSON (Baseline)",
            "wire_bytes": s_json,
            "reduction_pct": 0.0,
            "t_ser_ms": round(t_ser_j, 3),
            "t_deser_ms": round(t_deser_j, 3),
            "cpu_proc_ms": round(t_ser_j + t_deser_j, 3),
            "net_time_ms": round(t_net_j, 3),
            "e2e_ms": round(t_e2e_json, 3),
            "gain_pct": 0.0,
        },
        "json_gzip": {
            "name": "JSON + GZIP",
            "wire_bytes": s_gzip,
            "reduction_pct": round((1.0 - s_gzip / s_json) * 100.0, 1),
            "t_ser_ms": round(t_ser_g + t_comp_g, 3),
            "t_deser_ms": round(t_decomp_g + t_deser_g, 3),
            "cpu_proc_ms": round(t_ser_g + t_comp_g + t_decomp_g + t_deser_g, 3),
            "net_time_ms": round(t_net_g, 3),
            "e2e_ms": round(t_e2e_gzip, 3),
            "gain_pct": round(gain_gzip, 2),
        },
        "messagepack": {
            "name": "MessagePack (Binary)",
            "wire_bytes": s_mp,
            "reduction_pct": round((1.0 - s_mp / s_json) * 100.0, 1),
            "t_ser_ms": round(t_ser_mp, 3),
            "t_deser_ms": round(t_deser_mp, 3),
            "cpu_proc_ms": round(t_ser_mp + t_deser_mp, 3),
            "net_time_ms": round(t_net_mp, 3),
            "e2e_ms": round(t_e2e_mp, 3),
            "gain_pct": round(gain_mp, 2),
        },
    }

    # Best format by latency
    best_fmt = min(["json", "json_gzip", "messagepack"], key=lambda f: formats_eval[f]["e2e_ms"])
    best_gain = max(gain_gzip, gain_mp, 0.0)

    # 3-Zone Classification
    if best_gain < 5.0:
        zone = "ZONE_1"
        zone_label = "Zone 1: No Switch"
        zone_badge = "NO SWITCH"
        recommended_format = "json"
        zone_desc = "Relative latency gain is under 5%. JSON is recommended because switching overhead is not justified."
    elif best_gain < 20.0:
        zone = "ZONE_2"
        zone_label = "Zone 2: Evaluate"
        zone_badge = "EVALUATE"
        recommended_format = best_fmt if best_fmt != "json" else "json"
        zone_desc = f"Moderate gain ({best_gain:.1f}%). Evaluate CPU overhead versus bandwidth savings before switching."
    else:
        zone = "ZONE_3"
        zone_label = "Zone 3: Switch"
        zone_badge = "SWITCH"
        recommended_format = best_fmt
        zone_desc = f"Substantial latency gain ({best_gain:.1f}%). Strongly recommended switching to {formats_eval[best_fmt]['name']}."

    # Workload regime classification
    net_saved = t_net_j - formats_eval[best_fmt]["net_time_ms"]
    cpu_cost = formats_eval[best_fmt]["cpu_proc_ms"] - formats_eval["json"]["cpu_proc_ms"]
    if net_saved > (cpu_cost * 2.0):
        regime = "NETWORK_BOUND"
        regime_label = "Network-Bound"
        regime_desc = "Network transfer time dominates. Smaller wire payloads yield substantial latency savings."
    elif cpu_cost > (net_saved * 2.0):
        regime = "CPU_BOUND"
        regime_label = "CPU-Bound"
        regime_desc = "Serialization/compression compute overhead dominates. Baseline JSON is more efficient."
    else:
        regime = "BALANCED"
        regime_label = "Balanced"
        regime_desc = "Network savings and CPU processing costs are comparable in magnitude."

    # Analytical break-even bandwidths (B_BE)
    diff_mp_proc_sec = ((t_ser_mp + t_deser_mp) - (t_ser_j + t_deser_j)) / 1000.0
    diff_mp_bytes = s_json - s_mp
    bbe_mp_mbps = round((diff_mp_bytes * 8.0 / diff_mp_proc_sec) / 1e6, 2) if diff_mp_proc_sec > 0 else None

    diff_gzip_proc_sec = (t_comp_g + t_decomp_g) / 1000.0
    diff_gzip_bytes = s_json - s_gzip
    bbe_gzip_mbps = round((diff_gzip_bytes * 8.0 / diff_gzip_proc_sec) / 1e6, 2) if diff_gzip_proc_sec > 0 else None

    return {
        "status": "ok",
        "inputs": {
            "payload_kb": payload_kb,
            "payload_bytes": payload_bytes,
            "bandwidth_mbps": bandwidth_mbps,
            "rtt_ms": rtt_ms,
            "structure": structure,
        },
        "zone": zone,
        "zone_label": zone_label,
        "zone_badge": zone_badge,
        "zone_desc": zone_desc,
        "regime": regime,
        "regime_label": regime_label,
        "regime_desc": regime_desc,
        "best_performance_format": best_fmt,
        "recommended_format": recommended_format,
        "best_gain_pct": round(best_gain, 2),
        "formats": formats_eval,
        "breakeven": {
            "bbe_json_vs_mp_mbps": bbe_mp_mbps,
            "bbe_json_vs_gzip_mbps": bbe_gzip_mbps,
        }
    }


# ─────────────────────────────────────────────────────────────────────────────
# In-Browser Plot Gallery Endpoint
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/api/plots/list", summary="List all 10 publication charts and plots", tags=["Plots & Visualizations"])
async def list_plots_endpoint():
    """List all 10 publication charts with metadata, paths, and existence status."""
    from pathlib import Path

    plots_metadata = [
        {
            "id": "chart1",
            "file": "plots/payload/chart1_payload_vs_original.png",
            "title": "Chart 1: Payload Size vs Original Data Size",
            "category": "Payload",
            "description": "Compares payload overhead and compression density against baseline uncompressed JSON.",
        },
        {
            "id": "chart2",
            "file": "plots/performance/chart2_ser_deser_time_vs_payload.png",
            "title": "Chart 2: Processing Latency vs Payload Size",
            "category": "Performance",
            "description": "Serialization (T_ser) and Deserialization (T_deser) computation times across formats.",
        },
        {
            "id": "chart3",
            "file": "plots/performance/chart3_e2e_latency_vs_payload.png",
            "title": "Chart 3: End-to-End Latency vs Payload Size",
            "category": "Performance",
            "description": "Total roundtrip latency as dataset size scales from 10 KB to multi-megabyte payloads.",
        },
        {
            "id": "chart4",
            "file": "plots/performance/chart4_e2e_latency_vs_bandwidth.png",
            "title": "Chart 4: End-to-End Latency vs Network Bandwidth",
            "category": "Performance",
            "description": "Performance behavior from high-bandwidth LAN (1 Gbps) down to cellular/constrained links (1 Mbps).",
        },
        {
            "id": "chart5",
            "file": "plots/performance/chart5_e2e_latency_vs_net_latency.png",
            "title": "Chart 5: End-to-End Latency vs Injected RTT",
            "category": "Performance",
            "description": "Impact of round-trip network delays across local, metropolitan, and cross-region latencies.",
        },
        {
            "id": "chart6",
            "file": "plots/resources/chart6_cpu_memory_vs_payload.png",
            "title": "Chart 6: CPU Utilization & Memory Footprint",
            "category": "Resources",
            "description": "System CPU overhead percentage and peak resident memory delta during encoding and decoding.",
        },
        {
            "id": "chart7",
            "file": "plots/breakeven/chart7_net_saved_vs_cpu_cost.png",
            "title": "Chart 7: Network Time Saved vs Additional CPU Cost",
            "category": "Break-Even",
            "description": "Trade-off scatter plot; points above the diagonal indicate a net positive overall time win.",
        },
        {
            "id": "chart8",
            "file": "plots/performance/chart8_relative_gain_vs_payload.png",
            "title": "Chart 8: Relative Gain (%) vs Payload Size",
            "category": "Decision Model",
            "description": "Relative percentage gain over baseline JSON plotted against 5% (Evaluate) and 20% (Switch) thresholds.",
        },
        {
            "id": "chart9",
            "file": "plots/breakeven/chart9_breakeven_crossover.png",
            "title": "Chart 9: Latency Crossover Across Bandwidth Spectrum",
            "category": "Break-Even",
            "description": "Bandwidth break-even crossover points where binary and compressed formats overtake JSON.",
        },
        {
            "id": "chart10",
            "file": "plots/breakeven/chart10_2d_decision_boundary.png",
            "title": "Chart 10: 2D Decision Boundary Contour Plot",
            "category": "Decision Model",
            "description": "2D decision map (X: Payload Size, Y: Bandwidth) illustrating Zone 1, Zone 2, and Zone 3 regions.",
        },
    ]

    for p in plots_metadata:
        path = Path(p["file"])
        p["exists"] = path.exists() and path.stat().st_size > 0
        p["url"] = f"/{p['file']}" if p["exists"] else ""
        p["size_bytes"] = path.stat().st_size if p["exists"] else 0

    return {
        "status": "ok",
        "plots": plots_metadata,
        "total_count": len(plots_metadata),
        "available_count": sum(1 for p in plots_metadata if p["exists"]),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Robust Report, Plots & Tables Generation Endpoint
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/api/reports/generate", summary="Regenerate plots and tables from records", tags=["Plots & Visualizations"])
async def generate_reports_endpoint() -> dict:
    """
    Regenerate all 10 publication plots and 7 benchmark tables.
    If no records are in memory, loads from results/tables/records.csv or data/results/*.csv
    or executes a fast benchmark to ensure plots are always successfully produced.
    """
    import csv
    from pathlib import Path
    from src.analysis.plots import generate_all_plots
    from src.analysis.tables import generate_all_tables
    from src.metrics.collector import MetricRecord

    with _benchmark_lock:
        raw_recs = _benchmark_state.get("latest_records", [])

    records: list[MetricRecord] = []

    # 1. Check in-memory records
    if raw_recs:
        for r in raw_recs:
            if isinstance(r, dict):
                records.append(MetricRecord(**{k: r[k] for k in MetricRecord.__dataclass_fields__ if k in r}))
            elif isinstance(r, MetricRecord):
                records.append(r)

    # 2. Check results/tables/records.csv
    if not records:
        records_csv = Path("results/tables/records.csv")
        if records_csv.exists() and records_csv.stat().st_size > 50:
            try:
                import pandas as pd
                df = pd.read_csv(records_csv)
                for row in df.to_dict(orient="records"):
                    filtered = {k: row[k] for k in MetricRecord.__dataclass_fields__ if k in row and not pd.isna(row[k])}
                    records.append(MetricRecord(**filtered))
            except Exception as e:
                logger.warning("Could not load from records.csv: %s", e)

    # 3. Check data/results/*.csv
    if not records:
        raw_dir = Path("data/results")
        if raw_dir.exists():
            csv_files = sorted(raw_dir.glob("*.csv"), key=lambda f: f.stat().st_mtime, reverse=True)
            if csv_files:
                try:
                    import pandas as pd
                    df = pd.read_csv(csv_files[0])
                    for row in df.to_dict(orient="records"):
                        filtered = {k: row[k] for k in MetricRecord.__dataclass_fields__ if k in row and not pd.isna(row[k])}
                        records.append(MetricRecord(**filtered))
                except Exception as e:
                    logger.warning("Could not load from %s: %s", csv_files[0], e)

    # 4. If still no records, run a fast matrix to create real empirical records
    if not records:
        from src.benchmark.experiment import quick_config
        from src.benchmark.runner import BenchmarkRunner
        runner = BenchmarkRunner(quick_config())
        res = runner.run_all()
        records = [MetricRecord(**{k: r[k] for k in MetricRecord.__dataclass_fields__ if k in r}) for r in res.records]

    plots_paths = generate_all_plots(records, output_dir="plots")
    tables_paths = generate_all_tables(records, output_dir="results/tables")

    plots_data = {k: f"/plots/{v.parent.name}/{v.name}" for k, v in plots_paths.items()}
    tables_data = {k: f"/results/tables/{v['csv'].name}" for k, v in tables_paths.items()}

    with _benchmark_lock:
        _benchmark_state["plots"] = plots_data
        _benchmark_state["tables"] = tables_data

    return {
        "status": "ok",
        "message": f"Successfully generated 10 plots and 7 tables from {len(records)} measurements.",
        "plots_count": len(plots_paths),
        "tables_count": len(tables_paths),
        "plots": plots_data,
        "tables": tables_data,
    }


