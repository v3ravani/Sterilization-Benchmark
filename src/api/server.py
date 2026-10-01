"""
FastAPI application entry point for the benchmark server.

Exposes the benchmark API with:
  - GET  /health   — liveness check
  - POST /data     — binary payload ingestion with timing metrics

Run standalone:
    python -m uvicorn src.api.server:app --host 127.0.0.1 --port 8765 --reload

Or via the benchmark runner programmatically using run_server().
"""

import asyncio
import threading
import time
from typing import Optional

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import router

# ─────────────────────────────────────────────────────────────────────────────
# Custom Swagger UI Documentation Template (Clean White Mode Theme)
# ─────────────────────────────────────────────────────────────────────────────

SWAGGER_DOCS_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Serialization Benchmark | API Documentation</title>
  <meta name="description" content="Interactive API documentation and endpoint harness for the Serialization Benchmark suite.">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css">
  <style>
    :root {
      --bg-page: #f8fafc;
      --bg-card: #ffffff;
      --border-color: #e2e8f0;
      --border-hover: #cbd5e1;
      --text-primary: #0f172a;
      --text-secondary: #475569;
      --text-muted: #64748b;
      --color-primary: #0f172a;
      --color-primary-hover: #1e293b;
      --font-sans: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      --font-mono: 'JetBrains Mono', monospace;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    html, body {
      background-color: var(--bg-page);
      color: var(--text-primary);
      font-family: var(--font-sans);
      min-height: 100vh;
      -webkit-font-smoothing: antialiased;
    }
    body {
      padding: 24px;
    }
    @media (max-width: 768px) {
      body { padding: 12px; }
    }
    .docs-container {
      max-width: 1360px;
      margin: 0 auto;
      width: 100%;
    }
    .header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 12px;
      margin-bottom: 24px;
      padding-bottom: 18px;
      border-bottom: 1px solid var(--border-color);
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .brand-logo {
      width: 36px;
      height: 36px;
      border-radius: 6px;
      background: var(--color-primary);
      color: #ffffff;
      display: flex;
      align-items: center;
      justify-content: center;
      flex-shrink: 0;
    }
    .brand-title {
      font-size: 18px;
      font-weight: 700;
      letter-spacing: -0.3px;
      color: var(--text-primary);
    }
    .brand-subtitle {
      font-size: 13px;
      color: var(--text-muted);
    }
    .header-actions {
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: 12px;
    }
    .server-status {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 6px 12px;
      background: #f1f5f9;
      border: 1px solid var(--border-color);
      border-radius: 4px;
      font-size: 12px;
      font-weight: 500;
      color: var(--text-secondary);
      white-space: nowrap;
    }
    .status-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background-color: #16a34a;
      flex-shrink: 0;
    }
    .btn {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 7px 14px;
      font-size: 13px;
      font-weight: 500;
      border-radius: 6px;
      text-decoration: none;
      cursor: pointer;
      transition: all 0.12s ease;
      white-space: nowrap;
    }
    .btn-primary {
      background: var(--color-primary);
      color: #ffffff;
      border: 1px solid var(--color-primary);
    }
    .btn-primary:hover {
      background: var(--color-primary-hover);
    }

    /* Swagger UI Restyling to match dashboard */
    .swagger-ui {
      font-family: var(--font-sans) !important;
      color: var(--text-primary) !important;
    }
    .swagger-ui .topbar {
      display: none !important;
    }
    .swagger-ui .wrapper {
      padding: 0 !important;
      max-width: 100% !important;
    }
    .swagger-ui .info {
      margin: 0 0 20px 0 !important;
      background: #ffffff;
      border: 1px solid var(--border-color);
      border-radius: 8px;
      padding: 20px 24px !important;
      box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    }
    .swagger-ui .info .title {
      font-size: 20px !important;
      font-weight: 700 !important;
      color: var(--text-primary) !important;
      letter-spacing: -0.3px;
    }
    .swagger-ui .info p {
      font-size: 13px !important;
      color: var(--text-secondary) !important;
      line-height: 1.5 !important;
      margin-top: 6px !important;
    }
    .swagger-ui .filter .operation-filter-input {
      border: 1px solid var(--border-color) !important;
      border-radius: 6px !important;
      padding: 8px 14px !important;
      font-family: var(--font-sans) !important;
      font-size: 13px !important;
      background: #ffffff !important;
      margin: 12px 0 20px 0 !important;
      width: 100% !important;
      box-shadow: none !important;
      outline: none;
    }
    .swagger-ui .filter .operation-filter-input:focus {
      border-color: var(--color-primary) !important;
    }
    .swagger-ui .opblock-tag {
      font-size: 15px !important;
      font-weight: 700 !important;
      color: var(--text-primary) !important;
      border-bottom: 1px solid var(--border-color) !important;
      padding: 12px 0 !important;
      margin: 20px 0 10px 0 !important;
    }
    .swagger-ui .opblock {
      border-radius: 8px !important;
      box-shadow: 0 1px 2px rgba(0,0,0,0.03) !important;
      margin: 0 0 12px 0 !important;
      border: 1px solid var(--border-color) !important;
      background: #ffffff !important;
      overflow: hidden;
    }
    .swagger-ui .opblock .opblock-summary {
      padding: 10px 16px !important;
      background: #ffffff !important;
      border-bottom: 1px solid transparent;
    }
    .swagger-ui .opblock.is-open .opblock-summary {
      border-bottom-color: var(--border-color) !important;
    }
    .swagger-ui .opblock.opblock-get {
      border-color: #e2e8f0 !important;
    }
    .swagger-ui .opblock.opblock-get .opblock-summary-method {
      background: #2563eb !important;
      border-radius: 4px !important;
      font-weight: 600 !important;
      font-size: 11.5px !important;
      padding: 3px 8px !important;
      min-width: 65px;
      text-align: center;
    }
    .swagger-ui .opblock.opblock-post {
      border-color: #e2e8f0 !important;
    }
    .swagger-ui .opblock.opblock-post .opblock-summary-method {
      background: #0f172a !important;
      border-radius: 4px !important;
      font-weight: 600 !important;
      font-size: 11.5px !important;
      padding: 3px 8px !important;
      min-width: 65px;
      text-align: center;
    }
    .swagger-ui .opblock-summary-path {
      font-family: var(--font-mono) !important;
      font-size: 13px !important;
      font-weight: 600 !important;
      color: var(--text-primary) !important;
    }
    .swagger-ui .opblock-summary-description {
      font-size: 12px !important;
      color: var(--text-muted) !important;
    }
    .swagger-ui .opblock-body {
      background: #fafafa !important;
      padding: 16px 20px !important;
    }
    .swagger-ui .opblock-section-header {
      background: #f1f5f9 !important;
      padding: 8px 12px !important;
      border-radius: 4px;
    }
    .swagger-ui .opblock-section-header h4 {
      font-size: 12px !important;
      font-weight: 600 !important;
      color: var(--text-secondary) !important;
    }
    .swagger-ui .btn.execute {
      background-color: var(--color-primary) !important;
      border-color: var(--color-primary) !important;
      color: #ffffff !important;
      border-radius: 6px !important;
      font-weight: 600 !important;
      font-size: 13px !important;
      padding: 8px 24px !important;
      box-shadow: none !important;
      transition: background 0.12s ease !important;
    }
    .swagger-ui .btn.execute:hover {
      background-color: var(--color-primary-hover) !important;
    }
    .swagger-ui .btn.cancel {
      border-radius: 6px !important;
      font-weight: 500 !important;
    }
    .swagger-ui .btn.try-out__btn {
      border-radius: 4px !important;
      font-size: 11.5px !important;
      padding: 4px 12px !important;
      border: 1px solid var(--border-color) !important;
      background: #ffffff !important;
      color: var(--text-secondary) !important;
    }
    .swagger-ui select, .swagger-ui input[type=text], .swagger-ui textarea {
      font-family: var(--font-mono) !important;
      font-size: 12px !important;
      border: 1px solid var(--border-color) !important;
      border-radius: 4px !important;
      background: #ffffff !important;
      color: var(--text-primary) !important;
    }
    .swagger-ui .responses-inner {
      padding: 14px !important;
      background: #ffffff !important;
      border: 1px solid var(--border-color) !important;
      border-radius: 6px !important;
      margin-top: 12px !important;
    }
    .swagger-ui .highlight-code, .swagger-ui .microlight {
      font-family: var(--font-mono) !important;
      font-size: 11.5px !important;
      border-radius: 6px !important;
    }
    .swagger-ui .model-box {
      font-family: var(--font-mono) !important;
      font-size: 11.5px !important;
      background: #ffffff !important;
      border: 1px solid var(--border-color) !important;
      border-radius: 6px !important;
      padding: 12px !important;
    }
  </style>
</head>
<body>
  <div class="docs-container">
    <header class="header">
      <div class="brand">
        <div class="brand-logo">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline>
          </svg>
        </div>
        <div class="brand-text">
          <h1 class="brand-title">Serialization Benchmark</h1>
          <p class="brand-subtitle">Automated Evaluation, Break-Even Modeling & Research Suite</p>
        </div>
      </div>
      <div class="header-actions">
        <div class="server-status">
          <span class="status-dot"></span>
          <span class="status-label">Connected (FastAPI :8765)</span>
        </div>
        <a href="/dashboard/" class="btn btn-primary" id="btn-back-dashboard">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="19" y1="12" x2="5" y2="12"></line>
            <polyline points="12 19 5 12 12 5"></polyline>
          </svg>
          <span>Back to Dashboard</span>
        </a>
      </div>
    </header>

    <div id="swagger-ui"></div>

    <footer class="app-footer" style="width: 100%; margin-top: 40px; padding-top: 18px; padding-bottom: 24px; border-top: 1px solid var(--border-color); display: flex; justify-content: center; align-items: center; text-align: center;">
      <p style="font-size: 11px; font-weight: 500; color: var(--text-muted); letter-spacing: 0.3px; margin: 0; text-align: center;">Built by Prithvi Kharje &amp; Viraj Ravani</p>
    </footer>
  </div>

  <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-standalone-preset.js"></script>
  <script>
    window.ui = SwaggerUIBundle({
      url: '/openapi.json',
      dom_id: '#swagger-ui',
      deepLinking: true,
      presets: [
        SwaggerUIBundle.presets.apis,
        SwaggerUIStandalonePreset
      ],
      plugins: [
        SwaggerUIBundle.plugins.DownloadUrl
      ],
      layout: "BaseLayout",
      docExpansion: "list",
      defaultModelsExpandDepth: 1,
      defaultModelExpandDepth: 1,
      displayRequestDuration: true,
      tryItOutEnabled: true,
      filter: true
    });
  </script>
</body>
</html>
"""

def create_app() -> FastAPI:
    """
    Create and configure the FastAPI benchmark application.

    Returns a configured FastAPI instance with all routes registered.
    """
    app = FastAPI(
        title="Serialization Benchmark API",
        description=(
            "Lightweight HTTP transport harness for end-to-end serialization "
            "benchmarking across JSON, JSON+GZIP, and MessagePack formats."
        ),
        version="1.0.0",
        docs_url=None,
        redoc_url=None,
    )

    # Allow all origins in benchmark context (loopback only)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    # Register benchmark routes
    app.include_router(router)

    # Stage 10: Mount static dashboard and artifacts
    from pathlib import Path
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import RedirectResponse, HTMLResponse

    dashboard_dir = Path("dashboard")
    dashboard_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/dashboard", StaticFiles(directory=str(dashboard_dir), html=True), name="dashboard")

    plots_dir = Path("plots")
    plots_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/plots", StaticFiles(directory=str(plots_dir)), name="plots")

    results_dir = Path("results")
    results_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/results", StaticFiles(directory=str(results_dir)), name="results")

    @app.get("/", include_in_schema=False)
    async def redirect_to_dashboard():
        return RedirectResponse(url="/dashboard/")

    @app.get("/style.css", include_in_schema=False)
    async def serve_root_style():
        from fastapi.responses import FileResponse
        return FileResponse("dashboard/style.css", media_type="text/css")

    @app.get("/docs", include_in_schema=False)
    async def custom_swagger_docs():
        from fastapi.responses import FileResponse
        docs_file = Path("dashboard/docs.html")
        if docs_file.exists():
            return FileResponse(str(docs_file), media_type="text/html")
        return HTMLResponse(content=SWAGGER_DOCS_HTML)

    return app


# Module-level app instance (used by uvicorn and tests)
app = create_app()


# ─────────────────────────────────────────────────────────────────────────────
# Programmatic server lifecycle
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


class BenchmarkServer:
    """
    Manages the uvicorn server lifecycle for programmatic use.

    Runs the FastAPI server in a background thread so the benchmark
    runner can start/stop it without blocking the main event loop.

    Usage:
        server = BenchmarkServer()
        server.start()
        # ... run benchmark ...
        server.stop()

    Or as context manager:
        with BenchmarkServer() as server:
            client.post(server.base_url + "/data", ...)
    """

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        log_level: str = "error",
    ):
        self.host      = host
        self.port      = port
        self.log_level = log_level
        self._server: Optional[uvicorn.Server] = None
        self._thread:  Optional[threading.Thread] = None

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def start(self, wait_for_ready_sec: float = 2.0) -> None:
        """
        Start the server in a background daemon thread.

        :param wait_for_ready_sec: Seconds to wait for server to become ready.
        """
        config = uvicorn.Config(
            app=app,
            host=self.host,
            port=self.port,
            log_level=self.log_level,
            loop="asyncio",
        )
        self._server = uvicorn.Server(config=config)

        self._thread = threading.Thread(
            target=self._server.run,
            daemon=True,
            name="benchmark-server",
        )
        self._thread.start()

        # Wait briefly for server to be ready
        deadline = time.time() + wait_for_ready_sec
        while time.time() < deadline:
            if self._server.started:
                return
            time.sleep(0.05)

    def stop(self) -> None:
        """Gracefully stop the server."""
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=5.0)
        self._server = None
        self._thread = None

    @property
    def is_running(self) -> bool:
        return self._server is not None and self._server.started

    def __enter__(self) -> "BenchmarkServer":
        self.start()
        return self

    def __exit__(self, *args) -> None:
        self.stop()
