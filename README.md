# Serialization Benchmark

**Research Study:** When Is Binary Serialization Worth the Trade-Off?  
*An End-to-End Workload- and Network-Aware Empirical Evaluation of JSON, Compressed JSON, and MessagePack Serialization*

**Authors:** Prithvi Kharje & Viraj Ravani  
**Repository:** https://github.com/v3ravani/Sterilization-Benchmark

---

## 1. Project Overview

In modern distributed systems, cloud computing, and microservice architectures, data interchange formats are frequently selected based on convention or developer intuition rather than empirical trade-off analysis. While text JSON provides universal interoperability and effortless debugging, compact binary formats such as MessagePack and stream compression algorithms such as GZIP are often assumed to yield universal speedups.

In reality, end-to-end communication latency is governed by the coupled dynamics of three distinct phases:

```
T_e2e = T_ser + T_net + T_deser
```

Where:
- `T_ser`: CPU time spent serializing (and optionally compressing) the in-memory data structure.
- `T_net`: Physical network transfer time, modeled as `Payload_Bytes / Network_Bandwidth + Round_Trip_Latency`.
- `T_deser`: CPU time spent parsing (and optionally decompressing) the received byte stream back into native data objects.

When network bandwidth is high (e.g., local datacenter networks, Gigabit Ethernet, localhost), `T_net` constitutes a negligible fraction of total latency. In these environments, the CPU overhead introduced by GZIP compression or complex binary packing can exceed any transmission time savings, making alternative formats slower than standard JSON. Conversely, across constrained, mobile, or high-latency WAN networks, significant payload reduction dramatically lowers `T_net`, justifying higher CPU processing costs.

### Core Objectives
1. **Zero-Bias Empirical Evaluation:** Benchmark JSON, JSON + GZIP, and MessagePack across identical in-memory datasets with strict round-trip integrity validation.
2. **Break-Even Bandwidth Modeling:** Derive and validate closed-form mathematical equations for the break-even bandwidth threshold (`B_BE`), defining the exact network throughput below which an alternative format achieves a net latency win.
3. **3-Zone Decision Framework:** Provide engineers and architects with an evidence-based decision matrix categorizing operational scenarios into:
   - **Zone 1 (Relative Gain < 5%):** Negligible advantage; retain standard JSON for readability and tooling compatibility.
   - **Zone 2 (5% <= Relative Gain < 20%):** Context-dependent; trade off CPU utilization against bandwidth costs.
   - **Zone 3 (Relative Gain >= 20%):** Statistically significant advantage; recommend migrating to MessagePack or GZIP.
4. **Reproducible Research Harness:** Provide an interactive web dashboard, background asynchronous execution engine, publication-grade figure generation, and automated PDF/ZIP report exports.

---

## 2. Installation and Quick Start

### Prerequisites
- Python 3.10, 3.11, 3.12, 3.13, or 3.14
- Operating System: Windows 10/11, Linux, or macOS
- Recommended: Modern web browser (Chrome, Edge, Firefox, Safari)

### Step 1: Clone the Repository
```bash
git clone https://github.com/v3ravani/Sterilization-Benchmark.git
cd Sterilization-Benchmark
```

### Step 2: Create and Activate Virtual Environment (Recommended)
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux / macOS
python3 -m venv venv
source venv/bin/activate
```

### Step 3: Install Dependencies
```bash
pip install -r requirements.txt
```

Verify that all required packages are properly installed:
```bash
python -c "import fastapi, uvicorn, httpx, psutil, numpy, pandas, scipy, matplotlib, reportlab, msgpack, yaml; print('Environment verification successful.')"
```

### Step 4: Run the Test Suite
The repository includes a comprehensive test suite covering data generators, serialization formats, network emulation, metric aggregation, analysis models, and REST endpoints:
```bash
pytest
```
*Result: 455 unit and integration tests passing in under 4 seconds.*

---

## 3. Running the Application

The benchmark suite can be executed in two ways: via the **interactive web dashboard** (recommended) or headlessly via the **command-line interface (CLI)**.

### Method A: Start the Interactive Web Dashboard (Backend + Frontend)

The FastAPI server acts as both the REST API backend and the static file server for the web interface.

Start the application server:
```bash
python -m uvicorn src.api.server:app --host 127.0.0.1 --port 8765 --reload
```

Once started:
1. Open your browser and navigate to **`http://127.0.0.1:8765`**.
2. The dashboard interface provides four unified views:
   - **Benchmark Suite & Runner:** Select workload presets, serialization formats, network profiles, repetition counts, and parallel worker threads. View live console logs, progress bars, ETA calculations, latency breakdowns, and publication charts.
   - **Break-Even & Decision Calculator:** Interactive sliders for payload size and bandwidth to evaluate real-time theoretical models and empirical recommendations.
   - **Research Paper Viewer:** Summary of the academic study with direct access to pre-print manuscripts.
   - **Contributors View:** Author credentials and contribution areas.
3. Access interactive Swagger API documentation at **`http://127.0.0.1:8765/docs`**.
4. Access the dedicated offline technical API manual at **`http://127.0.0.1:8765/dashboard/docs.html`**.

### Method B: Headless Execution via Command-Line Interface (CLI)

#### 1. Execute the Full Experimental Matrix
Runs the Cartesian product of configured workloads, formats, and network profiles defined in `config/experiment.yaml`:
```bash
python -m experiments.run_experiment
```

#### 2. Run Single Preset Reproduction
Executes a quick reproduction run with console metric summaries:
```bash
python -m experiments.reproduce --workload nested_small_medium --format json_gzip --profile SLOW --reps 5
```

#### 3. Regenerate Publication Reports, Tables, and Charts
Processes raw benchmark records from `data/results/raw/` into structured CSV tables, Markdown summaries, and Matplotlib figures:
```bash
python -m experiments.generate_reports
```

---

## 4. Repository Structure

```
Sterilization-Benchmark/
|-- config/                          # YAML experiment configuration files
|   |-- experiment.yaml              # Experimental matrix parameters & thresholds
|   `-- network_profiles.yaml        # Network bandwidth and latency profiles
|-- dashboard/                       # Web control dashboard (HTML5, Vanilla CSS, JS)
|   |-- index.html                   # Main single-page application interface
|   |-- docs.html                    # Technical API reference documentation
|   |-- style.css                    # Design system tokens and layout styling
|   `-- script.js                    # Client logic, Chart.js wiring, polling engine
|-- data/                            # Persistent data storage
|   |-- datasets/                    # Canonical pre-generated benchmark datasets
|   `-- results/
|       `-- raw/                     # Immutable raw execution runs (.csv and .jsonl)
|-- docs/                            # Research documentation and methodology notes
|-- experiments/                     # Headless CLI entry points
|   |-- run_experiment.py            # Executes full benchmark matrix
|   |-- reproduce.py                 # Convenience tool for single-cell validation
|   `-- generate_reports.py          # Batch compiler for tables and charts
|-- plots/                           # Generated publication figures (PNG and PDF)
|-- results/                         # Analyzed results
|   |-- tables/                      # Structured CSV tables (Table 1 through Table 7)
|   |-- markdown/                    # Formatted Markdown tables for reports
|   `-- report.pdf                   # Complete compiled research publication report
|-- src/                             # Core Python package source code
|   |-- analysis/                    # Statistical models, decision framework, plotting
|   |   |-- break_even.py            # Closed-form break-even bandwidth calculations
|   |   |-- decision_model.py        # 3-Zone Decision Framework logic
|   |   |-- pdf_report.py            # ReportLab publication PDF report compiler
|   |   |-- plots.py                 # Matplotlib publication chart generators (10 figures)
|   |   |-- statistics.py            # Mean, standard deviation, and CI calculation
|   |   `-- tables.py                # Publication tables generator (Tables 1-7)
|   |-- api/                         # FastAPI application and routing layer
|   |   |-- routes.py                # REST endpoints and background execution worker
|   |   `-- server.py                # Server initialization and static file mounting
|   |-- benchmark/                   # Execution harness and runner
|   |   |-- client.py                # HTTP benchmark client
|   |   |-- experiment.py            # Matrix builder and config schema
|   |   |-- result_writer.py         # Crash-safe CSV/JSONL results streamer
|   |   |-- runner.py                # Multi-threaded benchmark orchestrator & cache
|   |   `-- timer.py                 # Nanosecond precision timer (perf_counter_ns)
|   |-- data/                        # Synthetic data generation and validation
|   |   |-- generator.py             # Optimized batch-estimation synthetic generators
|   |   |-- validator.py             # Strict round-trip structural & byte validator
|   |   `-- workloads.py             # Curated workload presets and catalog
|   |-- metrics/                     # Telemetry records and resource monitors
|   |   |-- collector.py             # Unified MetricRecord aggregator
|   |   |-- latency.py               # LatencyRecord schema
|   |   |-- resources.py             # psutil CPU and memory measurement
|   |   `-- size.py                  # Wire and payload byte measurement
|   |-- network/                     # Network simulation layer
|   |   |-- controller.py            # Windows-compatible rate limiter & latency injector
|   |   `-- profiles.py              # Canonical network profile specifications
|   `-- serialization/               # Interchange format handlers
|       |-- base.py                  # Abstract base serializer interface
|       |-- json_format.py           # Standard JSON serializer
|       |-- json_gzip_format.py      # Compressed JSON + GZIP stream serializer
|       |-- messagepack_format.py    # Binary MessagePack serializer
|       `-- registry.py              # Dynamic format registry
|-- tests/                           # Complete test suite (455 tests)
|   |-- conftest.py                  # Pytest fixtures and mock objects
|   |-- test_dashboard_api.py        # Dashboard REST API integration tests
|   |-- test_data.py                 # Synthetic generator integrity & speed tests
|   |-- test_decision_model.py       # Break-even and decision model tests
|   |-- test_integration.py          # End-to-end benchmark workflow tests
|   |-- test_network.py              # Throttling and latency injection tests
|   |-- test_pipeline.py             # BenchmarkRunner and thread pool tests
|   |-- test_plots.py                # Visualization generator verification
|   |-- test_serialization.py        # Format roundtrip encoding/decoding tests
|   `-- test_tables.py               # Research table output validation
|-- pyproject.toml                   # Project metadata and configuration
|-- requirements.txt                 # Pinned project dependencies
`-- README.md                        # Project documentation
```

---

## 5. Parameter Specifications

### Workload Presets Catalog

The benchmark provides 10 standardized canonical workload presets designed to test different structural shapes, scalar compositions, and entropy characteristics.

| Workload Name | Structure Type | Target Size | Redundancy Level | Description & Practical Analogue |
|---|---|---|---|---|
| `flat_small_low` | Flat Dictionary | 10 KB | Low | Scalar key-value store, IoT device telemetry packet |
| `flat_medium_high` | Flat Dictionary | 500 KB | High | Highly repetitive flat configuration table |
| `flat_large_medium` | Flat Dictionary | 5,000 KB | Medium | Large flat database export or tabular dump |
| `nested_small_medium` | Nested Hierarchy | 10 KB | Medium | Typical REST microservice JSON response (depth=3, breadth=2) |
| `nested_medium_low` | Nested Hierarchy | 500 KB | Low | Complex project organization tree, LDAP directory branch |
| `nested_large_high` | Nested Hierarchy | 5,000 KB | High | Deeply nested enterprise document with repetitive tags |
| `text_small_high` | Text-Heavy Corpus | 10 KB | High | Natural language comments, repeated status message logs |
| `text_medium_medium` | Text-Heavy Corpus | 500 KB | Medium | Blog articles, localized CMS content, document feeds |
| `numeric_small_low` | Numeric Series | 10 KB | Low | Sensor arrays, financial ticker price streams (float64) |
| `numeric_medium_medium` | Numeric Series | 500 KB | Medium | Time-series metrics, numerical simulation feature sets |

### Network Profile Specifications

Network simulation is performed via application-layer token-bucket rate limiting and high-resolution propagation delay injection, requiring no OS kernel drivers or elevated administrative privileges.

| Profile Name | Bandwidth Cap | Injected One-Way Latency | Effective Round-Trip Time | Target Environmental Regime |
|---|---|---|---|---|
| `FAST` | 1,000 Mbps (1 Gbps) | 0.5 ms | 1.0 ms | Intracloud VPC, Localhost, Datacenter rack LAN |
| `MODERATE` | 100 Mbps | 7.5 ms | 15.0 ms | Office Fiber, Enterprise Broadband, Strong 5G / WiFi |
| `SLOW` | 10 Mbps | 25.0 ms | 50.0 ms | Public 4G LTE, Edge device backhaul, Constrained WAN |

### Serialization Format Characteristics

| Format | Format Class | Compression Technique | Schema Requirement | Human Readable | Primary Advantages | Observed Bottlenecks |
|---|---|---|---|---|---|---|
| **JSON** | Text (UTF-8) | None | Schemaless / Dynamic | Yes | Universal compatibility, zero translation overhead, native browser support | Large payload footprint, redundant dictionary keys |
| **JSON + GZIP** | Compressed Stream | Deflate (Level 6) | Schemaless / Dynamic | No (Binary stream) | High compression ratio on repetitive strings (up to 95% reduction) | Heavy CPU compression and decompression latency penalty |
| **MessagePack** | Compact Binary | Native Type Packing | Schemaless / Dynamic | No (Binary stream) | Fast encoding/decoding in C, compact integer/float representation | Modest reduction on string-heavy objects (~15-20%) |

---

## 6. System Architecture and Key Features

### Architecture Overview

```
                      +---------------------------------------+
                      |         Web Browser Frontend          |
                      |  (Dashboard UI / Calculator / Charts) |
                      +-------------------+-------------------+
                                          |
                                HTTP / REST API (Port 8765)
                                          |
                      +-------------------v-------------------+
                      |            FastAPI Server             |
                      |   (Server, Endpoints, Background API) |
                      +-------------------+-------------------+
                                          |
                        Spawns Background Worker Session
                                          |
                      +-------------------v-------------------+
                      |           BenchmarkRunner             |
                      | (Thread Pool Executor: 1 to 16 workers|
                      +----+--------------+---------------+---+
                           |              |               |
              +------------v---+   +------v------+  +-----v--------------+
              | Dataset Cache  |   | Serializers |  | Network Controller |
              | (Shared Seed)  |   | (JSON/GZIP/ |  | (Token Bucket /    |
              |                |   | MessagePack)|  |  Latency Injector) |
              +------------+---+   +------+------+  +-----+--------------+
                           |              |               |
                           +--------------+---------------+
                                          |
                               MetricRecord Aggregator
                                          |
                      +-------------------v-------------------+
                      |      ResultWriter & Analysis Engine   |
                      | - Raw CSV/JSONL Streaming Storage     |
                      | - 10 Matplotlib Publication Charts    |
                      | - 7 Standard Research Tables          |
                      | - ReportLab PDF Report Compilation    |
                      +---------------------------------------+
```

### Key Technical Features

| Feature Component | Implementation Details | Operational Benefit |
|---|---|---|
| **Batch-Estimation Generator** | Replaces incremental `O(N^2)` serialization loops with two-stage sample estimation and bulk array construction. | Reduces generation time for 5 MB nested trees from 161 seconds to 1.6 seconds (100x speedup). |
| **In-Memory Dataset Caching** | Thread-safe dictionary cache keyed by `(structure, size_kb, redundancy, seed)`. | Guarantees all three formats benchmark identical data while avoiding redundant re-generation across formats. |
| **Concurrent Execution Engine** | `ThreadPoolExecutor` orchestration with thread-local `NetworkController` and `PrecisionTimer` instances. | Speeds up execution across matrix cells by parallelizing CPU-bound serialization and network sleep delays. |
| **Interactive Decision Calculator** | Real-time logarithmic slider computation of `T_ser`, `T_net`, and `T_deser` with live break-even calculation. | Enables developers to model custom payload volumes and network tiers before making architectural decisions. |
| **ReportLab PDF Publication Engine** | Full programmatic PDF document builder compiling executive summaries, data tables, and embedded vector charts. | Generates complete, publication-ready research reports directly downloadable from the UI or API. |
| **Dual Export System** | `/api/results/export` delivers a structured ZIP archive containing raw data, Markdown tables, and PNG plots; `/api/results/export/pdf` delivers the PDF report. | Supports reproducible external audits, data science workflows, and executive presentations. |
| **Live Telemetry & Cancellation** | Non-blocking execution state updates with elapsed time, moving-average ETA projection, and user-initiated abort triggers. | Prevents browser freezing and allows safe cancellation of long-running experimental passes. |

---

## 7. Mathematical Formulations

### End-to-End Latency
Total transfer latency for payload size `S` across bandwidth `B` with round-trip latency `RTT`:

```
T_e2e = T_ser + (S / B + RTT / 2) + T_deser
```

### Break-Even Bandwidth
The critical network speed threshold below which format `B` achieves faster overall end-to-end completion than baseline format `A`:

```
B_BE = (S_A - S_B) / (Delta_T_proc)
```

Where:
```
Delta_T_proc = (T_ser_B + T_deser_B) - (T_ser_A + T_deser_A)
```

- When actual bandwidth `B < B_BE`: The transmission time saved (`(S_A - S_B) / B`) exceeds the computational CPU penalty, making the alternative format faster.
- When actual bandwidth `B > B_BE`: The network is sufficiently fast that CPU overhead dominates, making baseline JSON faster.

### Relative Performance Gain
The normalized latency reduction relative to baseline JSON:

```
Relative_Gain = (T_e2e_JSON - T_e2e_Alt) / T_e2e_JSON * 100%
```

---

## 8. Authors and Citation

**Principal Authors:**  
- **Prithvi Kharje**  
- **Viraj Ravani**  

**Research Citation:**
```bibtex
@article{kharje_ravani_2026_serialization,
  title   = {When Is Binary Serialization Worth the Trade-Off? An End-to-End Workload- and Network-Aware Empirical Evaluation of JSON, Compressed JSON, and MessagePack Serialization},
  author  = {Kharje, Prithvi and Ravani, Viraj},
  journal = {Research Benchmark Series in Systems and Data Engineering},
  year    = {2026},
  url     = {https://github.com/v3ravani/Sterilization-Benchmark}
}
```

---

## 9. License

This project is licensed under the MIT License. See the `LICENSE` file for details.
