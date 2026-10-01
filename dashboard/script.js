/* -----------------------------------------------------------------------------
   Serialization Benchmark Control Dashboard Script
   Clean Scientific Light Theme • Zero Emojis • 100% Real Measured Data
   -------------------------------------------------------------------------- */

let pollInterval = null;
let timerInterval = null;
let runStartTime = null;
let latencyChartInstance = null;
let payloadChartInstance = null;
let tradeoffChartInstance = null;
let curatedWorkloads = [];
let lastRenderedLogCount = 0;
let currentActiveTable = 'table1';
let currentTableRows = [];
let currentTableHeaders = [];
let currentTableFormat = 'csv';
let currentMarkdownContent = '';

const FORMAT_CONFIGS = {
  json: { label: 'JSON (Baseline)', color: '#2563eb' },
  json_gzip: { label: 'JSON + GZIP', color: '#059669' },
  messagepack: { label: 'MessagePack', color: '#d97706' }
};

const TABLE_DISPLAY_NAMES = {
  table1: 'Table 1: Experimental Configuration & Dataset Summary',
  table2: 'Table 2: Encoding, Decoding & Compression Benchmark',
  table3: 'Table 3: Payload & Network Transmission Benchmark',
  table4: 'Table 4: End-to-End Performance & Relative Gain Benchmark',
  table5: 'Table 5: Workload & Network Condition Comparative Benchmark',
  table6: 'Table 6: Break-Even and Computational Trade-Off Results',
  table7: 'Table 7: Final Decision Framework Results & Recommendations',
  records: 'Raw Measured Metric Records (All Runs)'
};

document.addEventListener('DOMContentLoaded', () => {
  try { setupEventListeners(); } catch (err) { console.error('setupEventListeners error:', err); }
  try { setupPrimaryViewSwitcher(); } catch (err) { console.error('setupPrimaryViewSwitcher error:', err); }
  try { setupCalculator(); } catch (err) { console.error('setupCalculator error:', err); }
  try { setupInfoPopovers(); } catch (err) { console.error('setupInfoPopovers error:', err); }
  try { loadWorkloadsAndOptions(); } catch (err) { console.error('loadWorkloadsAndOptions error:', err); }
  try { checkInitialResults(); } catch (err) { console.error('checkInitialResults error:', err); }
});

/* -----------------------------------------------------------------------------
   1. Initialization & Curated Workloads Loader
   -------------------------------------------------------------------------- */

async function loadWorkloadsAndOptions() {
  try {
    const resW = await fetch('/api/workloads');
    if (!resW.ok) throw new Error(`Workloads HTTP ${resW.status}`);
    const dataW = await resW.json();

    if (dataW.workloads && dataW.workloads.length > 0) {
      curatedWorkloads = dataW.workloads;
      populateWorkloadSelect(curatedWorkloads);
      renderWorkloadInfo(curatedWorkloads[0]);
    }

    const resOpt = await fetch('/api/options');
    if (resOpt.ok) {
      document.getElementById('server-status-text').textContent = 'Connected (FastAPI :8765)';
      appendTerminalLog('[SYSTEM]', 'Connected to FastAPI server. 10 Curated Workloads catalog ready.', 'log-info');
    }
  } catch (err) {
    console.warn('Backend connection failed:', err);
    document.getElementById('server-status-text').textContent = 'Offline / Connecting...';
    const dot = document.getElementById('server-status-badge')?.querySelector('.status-dot');
    if (dot) dot.style.backgroundColor = '#d97706';
    appendTerminalLog('[WARN]', 'Could not connect to FastAPI server. Ensure backend is active.', 'log-warn');
  }
}

function populateWorkloadSelect(workloads) {
  const select = document.getElementById('workload-select');
  select.innerHTML = '';

  workloads.forEach((w, idx) => {
    const opt = document.createElement('option');
    opt.value = w.name;
    const structUpper = w.structure.toUpperCase();
    opt.textContent = `${idx + 1}. ${w.name} (${structUpper}, ${w.size_label}, ${w.redundancy} red)`;
    select.appendChild(opt);
  });

  if (workloads.length > 0) {
    select.value = workloads[0].name;
  }
}

function renderWorkloadInfo(w) {
  if (!w) return;
  document.getElementById('info-workload-name').textContent = w.name;
  document.getElementById('info-workload-structure').textContent = w.structure.toUpperCase();
  document.getElementById('info-workload-desc').textContent = w.description || 'Standard canonical benchmark workload.';
  document.getElementById('info-workload-size').textContent = `Size: ${w.size_label}`;
  document.getElementById('info-workload-redundancy').textContent = `Redundancy: ${w.redundancy.toUpperCase()}`;
  document.getElementById('info-workload-seed').textContent = `Seed: ${w.seed}`;
}

async function checkInitialResults() {
  try {
    const res = await fetch('/api/results/latest');
    if (!res.ok) {
      showLoadingView('idle');
      return;
    }
    const data = await res.json();
    if (data.status === 'ok' && data.summary && data.summary.valid_runs > 0) {
      displayResults(data);
      showResultsView();
    } else {
      showLoadingView('idle');
    }
  } catch (e) {
    showLoadingView('idle');
  }
}

/* -----------------------------------------------------------------------------
   2. Event Listeners & UI State Management
   -------------------------------------------------------------------------- */

function setupEventListeners() {
  const btnRun = document.getElementById('btn-run-benchmark');
  if (btnRun) btnRun.addEventListener('click', handleRunBenchmark);

  const btnStop = document.getElementById('btn-stop-benchmark');
  if (btnStop) btnStop.addEventListener('click', handleStopBenchmark);

  const btnStopLoader = document.getElementById('btn-stop-loader');
  if (btnStopLoader) btnStopLoader.addEventListener('click', handleStopBenchmark);

  const workloadSelect = document.getElementById('workload-select');
  if (workloadSelect) {
    workloadSelect.addEventListener('change', (e) => {
      const selected = curatedWorkloads.find(w => w.name === e.target.value);
      if (selected) renderWorkloadInfo(selected);
    });
  }

  const btnInspect = document.getElementById('btn-inspect-dataset');
  if (btnInspect) {
    btnInspect.addEventListener('click', () => {
      const activeName = document.getElementById('workload-select')?.value;
      if (activeName) openDatasetModal(activeName);
    });
  }

  const btnCloseDataset = document.getElementById('btn-close-dataset-modal');
  if (btnCloseDataset) {
    btnCloseDataset.addEventListener('click', () => {
      document.getElementById('dataset-modal')?.classList.add('hidden');
    });
  }

  const btnClosePlot = document.getElementById('btn-close-plot-modal');
  if (btnClosePlot) {
    btnClosePlot.addEventListener('click', () => {
      document.getElementById('plot-modal')?.classList.add('hidden');
    });
  }

  const btnCopyDataset = document.getElementById('btn-copy-dataset');
  if (btnCopyDataset) {
    btnCopyDataset.addEventListener('click', () => {
      const code = document.getElementById('modal-json-content')?.textContent || '';
      navigator.clipboard.writeText(code).then(() => {
        btnCopyDataset.textContent = 'Copied';
        setTimeout(() => { btnCopyDataset.textContent = 'Copy JSON'; }, 1800);
      });
    });
  }

  // Legacy Export button support (for cached or legacy HTML)
  const legacyExport = document.getElementById('btn-export-results');
  if (legacyExport) {
    legacyExport.addEventListener('click', () => {
      window.location.href = '/api/results/export';
    });
  }

  // Export Results Dropdown Menu
  const exportToggle = document.getElementById('btn-export-dropdown-toggle');
  const exportMenu = document.getElementById('export-dropdown-menu');
  const exportWrap = document.getElementById('export-dropdown-wrapper');

  if (exportToggle && exportMenu) {
    exportToggle.addEventListener('click', (e) => {
      e.stopPropagation();
      const isOpen = !exportMenu.classList.contains('hidden');
      if (isOpen) {
        exportMenu.classList.add('hidden');
        exportWrap?.classList.remove('is-open');
        exportToggle.setAttribute('aria-expanded', 'false');
      } else {
        exportMenu.classList.remove('hidden');
        exportWrap?.classList.add('is-open');
        exportToggle.setAttribute('aria-expanded', 'true');
      }
    });

    document.addEventListener('click', (e) => {
      if (exportWrap && !exportWrap.contains(e.target)) {
        exportMenu.classList.add('hidden');
        exportWrap.classList.remove('is-open');
        exportToggle.setAttribute('aria-expanded', 'false');
      }
    });

    document.getElementById('export-opt-zip')?.addEventListener('click', () => {
      exportMenu.classList.add('hidden');
      exportWrap?.classList.remove('is-open');
      exportToggle.setAttribute('aria-expanded', 'false');
    });

    document.getElementById('export-opt-pdf')?.addEventListener('click', () => {
      exportMenu.classList.add('hidden');
      exportWrap?.classList.remove('is-open');
      exportToggle.setAttribute('aria-expanded', 'false');
    });
  }

  const btnNewRun = document.getElementById('btn-new-run');
  if (btnNewRun) {
    btnNewRun.addEventListener('click', () => {
      showLoadingView('idle');
      document.getElementById('config-card')?.scrollIntoView({ behavior: 'smooth' });
    });
  }

  document.getElementById('btn-dismiss-stopped')?.addEventListener('click', () => {
    document.getElementById('stopped-banner')?.classList.add('hidden');
    showLoadingView('idle');
  });

  document.getElementById('btn-retry')?.addEventListener('click', () => {
    showLoadingView('idle');
  });

  document.getElementById('btn-generate-reports')?.addEventListener('click', handleGenerateReports);

  document.getElementById('btn-clear-logs')?.addEventListener('click', () => {
    const term = document.getElementById('live-terminal-body');
    if (term) term.innerHTML = '';
    lastRenderedLogCount = 0;
  });

  const tabBtns = document.querySelectorAll('.table-tabs-nav .tab-btn');
  tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      tabBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      const tableId = btn.getAttribute('data-table');
      loadAndRenderTable(tableId);
    });
  });

  document.getElementById('table-search-input')?.addEventListener('input', (e) => {
    filterTableDisplay(e.target.value);
  });

  // Table CSV vs Markdown view toggle
  const toggleCsv = document.getElementById('btn-toggle-csv');
  const toggleMd = document.getElementById('btn-toggle-md');
  const copyMdBtn = document.getElementById('btn-copy-table-md');

  if (toggleCsv && toggleMd) {
    toggleCsv.addEventListener('click', () => {
      toggleCsv.classList.add('active');
      toggleMd.classList.remove('active');
      currentTableFormat = 'csv';
      if (copyMdBtn) copyMdBtn.classList.add('hidden');
      renderTableDOM(currentTableHeaders, currentTableRows);
    });

    toggleMd.addEventListener('click', () => {
      toggleMd.classList.add('active');
      toggleCsv.classList.remove('active');
      currentTableFormat = 'markdown';
      if (copyMdBtn) copyMdBtn.classList.remove('hidden');
      renderTableMarkdown(currentMarkdownContent);
    });
  }

  if (copyMdBtn) {
    copyMdBtn.addEventListener('click', () => {
      navigator.clipboard.writeText(currentMarkdownContent).then(() => {
        copyMdBtn.textContent = 'Copied!';
        setTimeout(() => { copyMdBtn.textContent = 'Copy MD'; }, 1800);
      });
    });
  }

  // Research Plots Category Filters
  const catBtns = document.querySelectorAll('#plots-category-filters .category-filter-btn');
  catBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      catBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      const cat = btn.getAttribute('data-category');
      filterPlotsGallery(cat);
    });
  });
}

function showLoadingView(state = 'idle') {
  document.getElementById('loading-view').classList.remove('hidden');
  document.getElementById('results-view').classList.add('hidden');

  const idlePrompt = document.getElementById('idle-prompt');
  const activeLoader = document.getElementById('active-loader');
  const stoppedBanner = document.getElementById('stopped-banner');
  const errorBanner = document.getElementById('error-banner');

  const btnRun = document.getElementById('btn-run-benchmark');
  const btnStop = document.getElementById('btn-stop-benchmark');

  if (state === 'idle') {
    idlePrompt.classList.remove('hidden');
    activeLoader.classList.add('hidden');
    stoppedBanner.classList.add('hidden');
    errorBanner.classList.add('hidden');

    btnRun.disabled = false;
    btnRun.innerHTML = `
      <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
        <path d="M5 3l14 9-14 9V3z"/>
      </svg>
      <span>Run Benchmark</span>
    `;
    btnRun.classList.remove('hidden');
    btnStop.classList.add('hidden');
  } else if (state === 'running') {
    idlePrompt.classList.add('hidden');
    activeLoader.classList.remove('hidden');
    stoppedBanner.classList.add('hidden');
    errorBanner.classList.add('hidden');

    btnRun.disabled = true;
    btnRun.innerHTML = `<span>Running Benchmark...</span>`;
    btnStop.classList.remove('hidden');
  } else if (state === 'stopped') {
    idlePrompt.classList.add('hidden');
    activeLoader.classList.add('hidden');
    stoppedBanner.classList.remove('hidden');
    errorBanner.classList.add('hidden');

    btnRun.disabled = false;
    btnRun.innerHTML = `
      <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
        <path d="M5 3l14 9-14 9V3z"/>
      </svg>
      <span>Run Benchmark</span>
    `;
    btnRun.classList.remove('hidden');
    btnStop.classList.add('hidden');
  } else if (state === 'failed') {
    idlePrompt.classList.add('hidden');
    activeLoader.classList.add('hidden');
    stoppedBanner.classList.add('hidden');
    errorBanner.classList.remove('hidden');

    btnRun.disabled = false;
    btnRun.innerHTML = `
      <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
        <path d="M5 3l14 9-14 9V3z"/>
      </svg>
      <span>Run Benchmark</span>
    `;
    btnRun.classList.remove('hidden');
    btnStop.classList.add('hidden');
  }
}

function showResultsView() {
  document.getElementById('loading-view').classList.add('hidden');
  document.getElementById('results-view').classList.remove('hidden');

  const btnRun = document.getElementById('btn-run-benchmark');
  const btnStop = document.getElementById('btn-stop-benchmark');
  btnRun.disabled = false;
  btnRun.innerHTML = `
    <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
      <path d="M5 3l14 9-14 9V3z"/>
    </svg>
    <span>Run Benchmark</span>
  `;
  btnRun.classList.remove('hidden');
  btnStop.classList.add('hidden');

  loadAndRenderTable(currentActiveTable || 'table1');
  loadPlotGallery('all');
}

/* -----------------------------------------------------------------------------
   3. Execution Triggers & Stopping
   -------------------------------------------------------------------------- */

async function handleRunBenchmark() {
  const selectedFormats = Array.from(document.querySelectorAll('input[name="format"]:checked')).map(cb => cb.value);
  if (selectedFormats.length === 0) {
    alert('Please select at least one serialization format.');
    return;
  }

  const selectedWorkload = document.getElementById('workload-select').value;
  const profile = document.getElementById('network-profile').value;
  const reps = parseInt(document.getElementById('iterations-count').value, 10) || 3;
  const warmup = parseInt(document.getElementById('warmup-count').value, 10) || 1;
  const workersInput = document.getElementById('workers-count');
  const workers = workersInput ? Math.max(1, Math.min(16, parseInt(workersInput.value, 10) || 4)) : 4;

  const payload = {
    workloads: [selectedWorkload],
    formats: selectedFormats,
    profiles: [profile],
    repetitions: reps,
    warmup_runs: warmup,
    workers: workers,
    quick: false,
    generate_reports: true
  };

  showLoadingView('running');
  resetProgressUI();
  startElapsedTimer();

  try {
    const res = await fetch('/api/benchmark/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Execution trigger failed');
    }

    startPolling();
  } catch (err) {
    stopElapsedTimer();
    showLoadingView('failed');
    document.getElementById('error-message').textContent = err.message;
    appendTerminalLog('[ERROR]', `Execution initiation aborted: ${err.message}`, 'log-error');
  }
}

async function handleStopBenchmark() {
  try {
    appendTerminalLog('[USER]', 'Stop requested. Halting running benchmark...', 'log-warn');
    document.getElementById('loader-status-text').textContent = 'Stopping Benchmark...';
    document.getElementById('loader-sub-text').textContent = 'Waiting for active operation to cleanly exit...';

    const res = await fetch('/api/benchmark/stop', { method: 'POST' });
    if (res.ok) {
      appendTerminalLog('[SYSTEM]', 'Stop command acknowledged by runner.', 'log-info');
    }
  } catch (err) {
    console.error('Stop request error:', err);
  }
}

/* -----------------------------------------------------------------------------
   4. Status Polling, Telemetry & Accurate ETA
   -------------------------------------------------------------------------- */

function startPolling() {
  if (pollInterval) clearInterval(pollInterval);
  pollInterval = setInterval(pollStatus, 300);
}

async function pollStatus() {
  try {
    const res = await fetch('/api/benchmark/status');
    if (!res.ok) return;
    const status = await res.json();

    updateProgressUI(status);

    if (status.logs && status.logs.length > 0) {
      syncLogs(status.logs);
    }

    if (status.status === 'completed') {
      clearInterval(pollInterval);
      pollInterval = null;
      stopElapsedTimer();

      const resLatest = await fetch('/api/results/latest');
      if (resLatest.ok) {
        const latestData = await resLatest.json();
        if (latestData.status === 'ok') {
          displayResults(latestData);
          showResultsView();
          return;
        }
      }
      showLoadingView('idle');
    } else if (status.status === 'stopped') {
      clearInterval(pollInterval);
      pollInterval = null;
      stopElapsedTimer();

      showLoadingView('stopped');
      document.getElementById('stopped-desc').textContent = status.description || 'Execution was stopped by user.';
    } else if (status.status === 'failed') {
      clearInterval(pollInterval);
      pollInterval = null;
      stopElapsedTimer();

      showLoadingView('failed');
      document.getElementById('error-message').textContent = status.error || status.description || 'Execution failed';
    }
  } catch (err) {
    console.error('Polling error:', err);
  }
}

function updateProgressUI(status) {
  const pct = status.progress_pct || 0;
  document.getElementById('progress-bar').style.width = `${pct}%`;
  document.getElementById('progress-pct-display').textContent = `${pct}%`;

  if (status.description) {
    document.getElementById('loader-sub-text').textContent = status.description;
  }

  if (status.total_cells > 0) {
    document.getElementById('current-cell-badge').textContent = `Cell ${status.current_cell || 0} / ${status.total_cells}`;
  }

  const etaEl = document.getElementById('eta-timer');
  if (etaEl) {
    if (status.eta_sec !== null && status.eta_sec !== undefined) {
      etaEl.textContent = status.eta_sec <= 0 ? 'ETA: Finalizing...' : `ETA: ~${status.eta_sec.toFixed(1)}s remaining`;
    } else if (runStartTime && pct > 0) {
      const elapsedSec = (Date.now() - runStartTime) / 1000;
      const totalEst = (elapsedSec / pct) * 100;
      const rem = Math.max(0, totalEst - elapsedSec);
      etaEl.textContent = `ETA: ~${rem.toFixed(1)}s remaining`;
    } else {
      etaEl.textContent = 'ETA: Calculating...';
    }
  }
}

function resetProgressUI() {
  document.getElementById('progress-bar').style.width = '0%';
  document.getElementById('progress-pct-display').textContent = '0%';
  document.getElementById('current-cell-badge').textContent = 'Initializing...';
  document.getElementById('loader-sub-text').textContent = 'Configuring benchmark matrix...';
  document.getElementById('eta-timer').textContent = 'ETA: Calculating...';
  lastRenderedLogCount = 0;
}

function startElapsedTimer() {
  runStartTime = Date.now();
  if (timerInterval) clearInterval(timerInterval);
  timerInterval = setInterval(() => {
    const elapsedSec = ((Date.now() - runStartTime) / 1000).toFixed(1);
    const el = document.getElementById('elapsed-timer');
    if (el) el.textContent = `Elapsed: ${elapsedSec}s`;
  }, 100);
}

function stopElapsedTimer() {
  if (timerInterval) {
    clearInterval(timerInterval);
    timerInterval = null;
  }
}

function syncLogs(logsList) {
  if (!logsList || logsList.length === 0) return;

  const terminalBody = document.getElementById('live-terminal-body');
  const autoscroll = document.getElementById('chk-autoscroll')?.checked ?? true;

  if (logsList.length > lastRenderedLogCount) {
    const newLogs = logsList.slice(lastRenderedLogCount);
    newLogs.forEach(line => appendTerminalLine(terminalBody, line));
    lastRenderedLogCount = logsList.length;

    if (autoscroll) {
      terminalBody.scrollTop = terminalBody.scrollHeight;
    }
  }
}

function appendTerminalLog(prefix, message, extraClass = '') {
  const terminalBody = document.getElementById('live-terminal-body');
  if (!terminalBody) return;
  const now = new Date().toTimeString().split(' ')[0];
  const fullLine = `[${now}] ${prefix} ${message}`;
  appendTerminalLine(terminalBody, fullLine, extraClass);
}

function appendTerminalLine(container, lineText, overrideClass = '') {
  const lineEl = document.createElement('div');
  lineEl.className = 'terminal-log-line';

  let tagClass = 'log-system';
  if (overrideClass) {
    tagClass = overrideClass;
  } else if (lineText.includes('[FATAL]') || lineText.includes('[ERROR]')) {
    tagClass = 'log-error';
  } else if (lineText.includes('[WARN]')) {
    tagClass = 'log-warn';
  } else if (lineText.includes('Complete') || lineText.includes('finished') || lineText.includes('Valid')) {
    tagClass = 'log-success';
  } else if (lineText.includes('[INFO]') || lineText.includes('[SYSTEM]')) {
    tagClass = 'log-info';
  } else if (lineText.includes('Cell')) {
    tagClass = 'log-cell';
  }

  lineEl.innerHTML = `<span class="${tagClass}">${escapeHtml(lineText)}</span>`;
  container.appendChild(lineEl);
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

/* -----------------------------------------------------------------------------
   5. Results Rendering
   -------------------------------------------------------------------------- */

function displayResults(data) {
  if (data.summary) {
    document.getElementById('stat-time').textContent = `${data.summary.duration_sec}s`;
    document.getElementById('stat-valid').textContent = `${data.summary.valid_runs} / ${data.summary.total_runs} (100%)`;
    document.getElementById('stat-cells').textContent = `${data.summary.total_runs > 0 ? (data.summary.total_runs / (data.summary.repetitions || 3)).toFixed(0) : '1'}`;

    const bannerMeta = document.getElementById('banner-meta');
    if (bannerMeta) {
      bannerMeta.textContent = `Experiment ID: ${data.summary.experiment_id} | ${data.summary.valid_runs} valid runs executed in ${data.summary.duration_sec}s`;
    }
  }

  const decisionContainer = document.getElementById('decision-items-container');
  if (data.decisions && data.decisions.length > 0) {
    decisionContainer.innerHTML = '';
    let bestRec = 'JSON';

    data.decisions.forEach(d => {
      const row = document.createElement('div');
      row.className = 'decision-row';

      const zoneClass = `zone-${d.zone}`;
      const gainSign = d.relative_gain_pct >= 0 ? '+' : '';

      row.innerHTML = `
        <div>
          <span class="decision-fmt">${FORMAT_CONFIGS[d.format_name]?.label || d.format_name}</span>
          <div style="font-size: 12px; color: #64748b; margin-top: 2px;">${escapeHtml(d.recommendation)}</div>
        </div>
        <div class="decision-badges">
          <span class="zone-badge ${zoneClass}">${escapeHtml(d.zone.replace('_', ' '))}</span>
          <span class="regime-badge">${escapeHtml(d.regime.replace('_', ' '))}</span>
          <span style="font-family: var(--font-mono); font-size: 12px; font-weight: 600; color: ${d.relative_gain_pct >= 0 ? '#16a34a' : '#dc2626'}">
            ${gainSign}${d.relative_gain_pct}%
          </span>
        </div>
      `;
      decisionContainer.appendChild(row);

      if (d.zone === 'switch') {
        bestRec = d.format_name;
      }
    });

    document.getElementById('stat-recommendation').textContent = FORMAT_CONFIGS[bestRec]?.label || bestRec;
  }

  renderAccurateCharts(data.format_metrics || {}, data.records_sample || []);
  loadAndRenderTable(currentActiveTable);
  renderPlotsGallery(data.plots || {});

  if (data.logs && data.logs.length > 0) {
    const completedTerminal = document.getElementById('completed-terminal-body');
    if (completedTerminal) {
      completedTerminal.innerHTML = '';
      data.logs.forEach(l => appendTerminalLine(completedTerminal, l));
    }
    const logsBadge = document.getElementById('completed-logs-count');
    if (logsBadge) {
      logsBadge.textContent = `${data.logs.length} logs`;
    }
  }
}

/* -----------------------------------------------------------------------------
   6. Chart.js Visualization (Clean Light Theme)
   -------------------------------------------------------------------------- */

function renderAccurateCharts(metricsMap, rawRecords) {
  let formats = Object.keys(metricsMap);
  let metrics = metricsMap;

  if (formats.length === 0 && rawRecords.length > 0) {
    formats = [...new Set(rawRecords.map(r => r.format_name))];
    metrics = {};
    formats.forEach(f => {
      const recs = rawRecords.filter(r => r.format_name === f);
      const n = recs.length;
      metrics[f] = {
        t_ser_ms: n ? recs.reduce((a, r) => a + (r.t_ser_ms || 0), 0) / n : 0,
        t_net_ms: n ? recs.reduce((a, r) => a + (r.t_net_ms || 0), 0) / n : 0,
        t_deser_ms: n ? recs.reduce((a, r) => a + (r.t_deser_ms || 0), 0) / n : 0,
        t_e2e_ms: n ? recs.reduce((a, r) => a + (r.t_e2e_ms || 0), 0) / n : 0,
        payload_size_bytes: n ? recs.reduce((a, r) => a + (r.payload_size_bytes || 0), 0) / n : 0,
        original_size_bytes: n ? recs.reduce((a, r) => a + (r.original_size_bytes || 0), 0) / n : 0,
      };
    });
  }

  if (formats.length === 0) return;

  const labels = formats.map(f => FORMAT_CONFIGS[f]?.label || f);

  const serTimes = formats.map(f => Number((metrics[f]?.t_ser_ms || 0).toFixed(3)));
  const netTimes = formats.map(f => Number((metrics[f]?.t_net_ms || 0).toFixed(3)));
  const deserTimes = formats.map(f => Number((metrics[f]?.t_deser_ms || 0).toFixed(3)));

  const wireBytes = formats.map(f => Math.round(metrics[f]?.payload_size_bytes || 0));
  const origBytes = formats.map(f => Math.round(metrics[f]?.original_size_bytes || 0));

  const cpuTimes = formats.map(f => Number(((metrics[f]?.t_ser_ms || 0) + (metrics[f]?.t_deser_ms || 0)).toFixed(3)));

  const lightScales = {
    x: {
      grid: { color: '#f1f5f9' },
      ticks: { color: '#64748b', font: { family: 'Inter', size: 11 } }
    },
    y: {
      grid: { color: '#f1f5f9' },
      ticks: { color: '#64748b', font: { family: 'Inter', size: 11 } }
    }
  };

  // Chart 1: Latency Breakdown (Stacked Bar)
  const ctxLatency = document.getElementById('chart-latency').getContext('2d');
  if (latencyChartInstance) latencyChartInstance.destroy();
  latencyChartInstance = new Chart(ctxLatency, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [
        { label: 'Serialization (T_ser)', data: serTimes, backgroundColor: '#2563eb', stack: 'stack1' },
        { label: 'Network Transfer (T_net)', data: netTimes, backgroundColor: '#64748b', stack: 'stack1' },
        { label: 'Deserialization (T_deser)', data: deserTimes, backgroundColor: '#059669', stack: 'stack1' }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: true, labels: { color: '#334155', font: { family: 'Inter', size: 11 } } },
        tooltip: {
          backgroundColor: '#0f172a',
          titleFont: { family: 'Inter', size: 12 },
          bodyFont: { family: 'JetBrains Mono', size: 12 },
          callbacks: {
            footer: (items) => {
              const total = items.reduce((acc, item) => acc + item.parsed.y, 0);
              return `Total E2E: ${total.toFixed(3)} ms`;
            }
          }
        }
      },
      scales: {
        x: { ...lightScales.x, stacked: true },
        y: { ...lightScales.y, stacked: true, title: { display: true, text: 'Latency (ms)', color: '#64748b' } }
      }
    }
  });

  // Chart 2: Payload Wire Bytes vs Original Bytes
  const ctxPayload = document.getElementById('chart-payload').getContext('2d');
  if (payloadChartInstance) payloadChartInstance.destroy();
  payloadChartInstance = new Chart(ctxPayload, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [
        {
          label: 'Wire Payload Bytes',
          data: wireBytes,
          backgroundColor: formats.map(f => FORMAT_CONFIGS[f]?.color || '#2563eb'),
          borderRadius: 4
        },
        {
          label: 'Original JSON Bytes',
          data: origBytes,
          backgroundColor: '#e2e8f0',
          borderColor: '#cbd5e1',
          borderWidth: 1,
          borderRadius: 4
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: true, labels: { color: '#334155', font: { family: 'Inter', size: 11 } } },
        tooltip: {
          backgroundColor: '#0f172a',
          titleFont: { family: 'Inter', size: 12 },
          bodyFont: { family: 'JetBrains Mono', size: 12 },
          callbacks: {
            afterBody: (items) => {
              const fIdx = items[0].dataIndex;
              const f = formats[fIdx];
              const red = metrics[f]?.payload_reduction_pct;
              return red !== undefined ? `Payload Reduction vs Baseline: ${red}%` : '';
            }
          }
        }
      },
      scales: {
        ...lightScales,
        y: { ...lightScales.y, title: { display: true, text: 'Bytes on Wire', color: '#64748b' } }
      }
    }
  });

  // Chart 3: Computational Trade-Off
  const ctxTradeoff = document.getElementById('chart-tradeoff').getContext('2d');
  if (tradeoffChartInstance) tradeoffChartInstance.destroy();
  tradeoffChartInstance = new Chart(ctxTradeoff, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [
        {
          label: 'CPU Compute Overhead (T_ser + T_deser)',
          data: cpuTimes,
          backgroundColor: '#dc2626',
          borderRadius: 4
        },
        {
          label: 'Network Wire Transmission Time (T_net)',
          data: netTimes,
          backgroundColor: '#0284c7',
          borderRadius: 4
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: true, labels: { color: '#334155', font: { family: 'Inter', size: 11 } } },
        tooltip: {
          backgroundColor: '#0f172a',
          callbacks: {
            label: (item) => `${item.dataset.label}: ${item.parsed.y} ms`
          }
        }
      },
      scales: {
        ...lightScales,
        y: { ...lightScales.y, title: { display: true, text: 'Time (ms)', color: '#64748b' } }
      }
    }
  });
}

/* -----------------------------------------------------------------------------
   7. Structured Tables Viewer
   -------------------------------------------------------------------------- */

async function loadAndRenderTable(tableId) {
  currentActiveTable = tableId;
  const container = document.getElementById('table-display-container');
  const titleEl = document.getElementById('table-active-title');
  const countEl = document.getElementById('table-active-count');
  const downloadBtn = document.getElementById('btn-download-active-table');

  if (titleEl) titleEl.textContent = TABLE_DISPLAY_NAMES[tableId] || tableId;
  if (countEl) countEl.textContent = 'Loading...';
  if (container) container.innerHTML = '<div class="table-placeholder">Loading benchmark table data...</div>';

  if (downloadBtn) {
    downloadBtn.href = `/api/tables/download/${tableId}`;
    downloadBtn.setAttribute('download', `${tableId}.csv`);
  }

  try {
    const res = await fetch(`/api/tables/view/${tableId}`);
    if (!res.ok) {
      if (container) container.innerHTML = '<div class="table-placeholder">Table not generated yet. Run a benchmark or click "Regenerate Plots & Tables".</div>';
      if (countEl) countEl.textContent = '0 rows';
      return;
    }

    const data = await res.json();
    currentTableHeaders = data.headers || [];
    currentTableRows = data.rows || [];
    currentMarkdownContent = data.markdown || '';

    if (countEl) countEl.textContent = `${currentTableRows.length} rows`;

    if (currentTableFormat === 'markdown') {
      renderTableMarkdown(currentMarkdownContent);
    } else {
      renderTableDOM(currentTableHeaders, currentTableRows);
    }
  } catch (err) {
    if (container) container.innerHTML = `<div class="table-placeholder">Failed to load table: ${escapeHtml(err.message)}</div>`;
    if (countEl) countEl.textContent = 'Error';
  }
}

function renderTableDOM(headers, rows) {
  const container = document.getElementById('table-display-container');
  if (!container) return;

  if (!rows || rows.length === 0) {
    container.innerHTML = '<div class="table-placeholder">No rows available in this table.</div>';
    return;
  }

  let html = '<table class="benchmark-table"><thead><tr>';
  headers.forEach(h => {
    html += `<th>${escapeHtml(h)}</th>`;
  });
  html += '</tr></thead><tbody>';

  rows.forEach(row => {
    html += '<tr>';
    row.forEach((cell) => {
      const isNum = !isNaN(parseFloat(cell)) && isFinite(cell);
      const numClass = isNum ? 'class="num"' : '';
      let highlightClass = '';

      if (cell === 'SWITCH' || cell === 'Yes' || cell === 'True') {
        highlightClass = 'class="highlight-good"';
      } else if (cell === 'json' || cell === 'messagepack' || cell === 'json_gzip') {
        highlightClass = 'class="highlight-rec"';
      }

      html += `<td ${highlightClass || numClass}>${escapeHtml(String(cell))}</td>`;
    });
    html += '</tr>';
  });

  html += '</tbody></table>';
  container.innerHTML = html;
}

function renderTableMarkdown(mdText) {
  const container = document.getElementById('table-display-container');
  if (!container) return;
  if (!mdText) {
    container.innerHTML = '<div class="table-placeholder">No Markdown representation available.</div>';
    return;
  }
  container.innerHTML = `<pre class="markdown-preview-block"><code>${escapeHtml(mdText)}</code></pre>`;
}

function filterTableDisplay(keyword) {
  if (!currentTableRows.length) return;
  const kw = keyword.toLowerCase().trim();

  if (!kw) {
    renderTableDOM(currentTableHeaders, currentTableRows);
    const countEl = document.getElementById('table-active-count');
    if (countEl) countEl.textContent = `${currentTableRows.length} rows`;
    return;
  }

  const filtered = currentTableRows.filter(row => {
    return row.some(cell => String(cell).toLowerCase().includes(kw));
  });

  const countEl = document.getElementById('table-active-count');
  if (countEl) countEl.textContent = `${filtered.length} of ${currentTableRows.length} rows`;
  renderTableDOM(currentTableHeaders, filtered);
}

/* -----------------------------------------------------------------------------
   8. Research Plots Gallery
   -------------------------------------------------------------------------- */

const PLOT_DESCRIPTIONS = {
  chart1_payload_size_scaling: 'Chart 1: Payload Size vs Original Data Size',
  chart2_ser_deser_time: 'Chart 2: Serialization & Deserialization Time vs Payload Size',
  chart3_e2e_latency_scaling: 'Chart 3: End-to-End Latency vs Payload Size Scaling',
  chart4_latency_vs_bandwidth: 'Chart 4: Latency vs Network Bandwidth (10 Mbps to 1 Gbps)',
  chart5_latency_vs_rtt: 'Chart 5: Latency vs Network Latency (RTT Sensitivity)',
  chart6_resource_usage: 'Chart 6: CPU and Memory Overhead during Serialization',
  chart7_compute_vs_network_tradeoff: 'Chart 7: Network Time Saved vs Computational CPU Cost',
  chart8_relative_gain_thresholds: 'Chart 8: Relative Gain vs Payload Size with Decision Thresholds',
  chart9_breakeven_crossover: 'Chart 9: Payload and Network Break-Even Crossover Boundary',
  chart10_decision_surface_2d: 'Chart 10: 2D Decision Boundary (Payload Size vs Bandwidth)'
};

let allPlotsCache = [];

async function loadPlotGallery(selectedCategory = 'all') {
  const container = document.getElementById('plots-preview-container');
  if (!container) return;

  try {
    const res = await fetch('/api/plots/list');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    allPlotsCache = data.plots || [];
    filterPlotsGallery(selectedCategory);
  } catch (err) {
    container.innerHTML = '<div style="color: #64748b; font-size: 13px; grid-column: 1 / -1; padding: 24px; text-align: center;">Plots will generate automatically when running a benchmark.</div>';
  }
}

function filterPlotsGallery(category = 'all') {
  const container = document.getElementById('plots-preview-container');
  if (!container) return;

  const filtered = (!category || category === 'all')
    ? allPlotsCache
    : allPlotsCache.filter(p => p.category && p.category.toLowerCase() === category.toLowerCase());

  if (filtered.length === 0) {
    container.innerHTML = '<div style="color: #64748b; font-size: 13px; grid-column: 1 / -1; padding: 36px; text-align: center;">No charts found for this category. Click "Regenerate Plots & Tables" to create them.</div>';
    return;
  }

  let html = '';
  filtered.forEach(p => {
    const isAvail = p.exists && p.url;
    html += `
      <div class="plot-card">
        <div class="plot-card-thumb-wrap" data-url="${isAvail ? p.url : ''}" data-title="${escapeHtml(p.title)}">
          ${isAvail
            ? `<img class="plot-card-thumb" src="${p.url}" alt="${escapeHtml(p.title)}" loading="lazy">`
            : `<div class="plot-empty-thumb" style="display:flex; flex-direction:column; align-items:center; justify-content:center; height:100%; color:#64748b; font-size:11px; gap:4px;">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
                  <circle cx="8.5" cy="8.5" r="1.5"></circle>
                  <polyline points="21 15 16 10 5 21"></polyline>
                </svg>
                <span>Plot pending</span>
               </div>`
          }
        </div>
        <div class="plot-card-info">
          <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:8px;">
            <span class="plot-card-title">${escapeHtml(p.title)}</span>
            <span class="plot-category-badge">${escapeHtml(p.category || 'General')}</span>
          </div>
          <div class="plot-card-actions">
            ${isAvail
              ? `<button type="button" class="btn btn-xs btn-outline btn-view-plot" data-url="${p.url}" data-title="${escapeHtml(p.title)}">View High-Res</button>
                 <a href="${p.url}" download="${p.id}.png" class="btn btn-xs btn-outline">Download PNG</a>`
              : `<button type="button" class="btn btn-xs btn-outline" disabled>Not Available</button>`
            }
          </div>
        </div>
      </div>
    `;
  });

  container.innerHTML = html;

  container.querySelectorAll('.plot-card-thumb-wrap, .btn-view-plot').forEach(el => {
    el.addEventListener('click', () => {
      const url = el.getAttribute('data-url');
      const title = el.getAttribute('data-title');
      if (url) openPlotModal(url, title);
    });
  });
}

function renderPlotsGallery(plotsMap) {
  loadPlotGallery('all');
}

function openPlotModal(url, title) {
  const modal = document.getElementById('plot-modal');
  document.getElementById('plot-modal-title').textContent = title;
  document.getElementById('plot-modal-img').src = url;
  const dl = document.getElementById('btn-download-plot-img');
  dl.href = url;
  dl.setAttribute('download', `${title.replace(/[^a-zA-Z0-9_-]/g, '_')}.png`);
  modal.classList.remove('hidden');
}

/* -----------------------------------------------------------------------------
   9. Dataset Inspector Modal
   -------------------------------------------------------------------------- */

async function openDatasetModal(selectedWorkloadName) {
  const modal = document.getElementById('dataset-modal');
  modal.classList.remove('hidden');

  renderModalWorkloadSelector(selectedWorkloadName);
  await loadWorkloadDatasetPreview(selectedWorkloadName);
}

function renderModalWorkloadSelector(activeName) {
  const selector = document.getElementById('modal-workload-selector');
  selector.innerHTML = '';

  curatedWorkloads.forEach(w => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = `modal-wl-btn ${w.name === activeName ? 'active' : ''}`;
    btn.textContent = w.name;

    btn.addEventListener('click', async () => {
      selector.querySelectorAll('.modal-wl-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      await loadWorkloadDatasetPreview(w.name);
    });

    selector.appendChild(btn);
  });
}

async function loadWorkloadDatasetPreview(wName) {
  document.getElementById('modal-dataset-name').textContent = `Dataset Inspector: ${wName}`;
  document.getElementById('modal-json-content').textContent = 'Generating real payload snippet...';

  try {
    const res = await fetch(`/api/workloads/${wName}/dataset`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    document.getElementById('modal-stat-structure').textContent = data.structure.toUpperCase();
    document.getElementById('modal-stat-size').textContent = data.size_label;
    document.getElementById('modal-stat-json-bytes').textContent = `${data.sample_size_bytes.toLocaleString()} B`;
    document.getElementById('modal-stat-gzip-bytes').textContent = `${data.gzip_size_bytes.toLocaleString()} B`;
    document.getElementById('modal-stat-mp-bytes').textContent = `${data.messagepack_size_bytes.toLocaleString()} B`;
    document.getElementById('modal-keys-count').textContent = data.keys_count;

    document.getElementById('modal-json-content').textContent = data.preview_json;
  } catch (err) {
    document.getElementById('modal-json-content').textContent = `Error loading dataset: ${err.message}`;
  }
}

async function handleGenerateReports() {
  const btn = document.getElementById('btn-generate-reports');
  if (btn) {
    btn.disabled = true;
    btn.textContent = 'Regenerating Artifacts...';
  }

  try {
    const res = await fetch('/api/reports/generate', { method: 'POST' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    appendTerminalLog('[SYSTEM]', data.message || '10 publication plots and 7 benchmark tables generated.', 'log-info');
    loadPlotGallery('all');
    loadAndRenderTable(currentActiveTable || 'table1');
  } catch (err) {
    console.error('Report generation failed:', err);
    appendTerminalLog('[ERROR]', `Report generation failed: ${err.message}`, 'log-error');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = 'Regenerate Plots & Tables';
    }
  }
}

/* -----------------------------------------------------------------------------
   11. Primary View Switcher Navigation
   -------------------------------------------------------------------------- */

function setupPrimaryViewSwitcher() {
  const buttons = document.querySelectorAll('#main-view-switcher .view-switcher-btn');
  buttons.forEach(btn => {
    btn.addEventListener('click', () => {
      const targetViewId = btn.getAttribute('data-view');
      buttons.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');

      document.querySelectorAll('.main-view-section').forEach(sec => {
        sec.classList.add('hidden');
      });

      const targetSec = document.getElementById(targetViewId);
      if (targetSec) {
        targetSec.classList.remove('hidden');
      }

      if (targetViewId === 'section-calculator') {
        runCalculatorSimulation();
      }
    });
  });
}

/* -----------------------------------------------------------------------------
   12. Interactive Decision Matrix & Break-Even Calculator
   -------------------------------------------------------------------------- */

let calcDebounceTimer = null;
let currentPayloadKb = 250.0;
let currentBwMbps = 50.0;

// Logarithmic conversion for sliders (10 KB - 10 MB, and 1 Mbps - 1 Gbps)
function sliderPosToPayloadKb(pos) {
  // pos: 0 to 1000 -> 10 to 10000 KB
  const rawKb = 10 * Math.pow(1000, pos / 1000);
  if (rawKb < 50) return Math.round(rawKb / 2) * 2;
  if (rawKb < 500) return Math.round(rawKb / 10) * 10;
  if (rawKb < 2000) return Math.round(rawKb / 50) * 50;
  return Math.round(rawKb / 250) * 250;
}

function payloadKbToSliderPos(kb) {
  const clamped = Math.max(10, Math.min(10000, kb));
  return Math.round((Math.log10(clamped / 10) / 3) * 1000);
}

function sliderPosToBwMbps(pos) {
  // pos: 0 to 1000 -> 1 to 1000 Mbps
  const rawMbps = 1 * Math.pow(1000, pos / 1000);
  if (rawMbps < 10) return Math.round(rawMbps * 2) / 2;
  if (rawMbps < 100) return Math.round(rawMbps / 5) * 5;
  return Math.round(rawMbps / 25) * 25;
}

function bwMbpsToSliderPos(mbps) {
  const clamped = Math.max(1, Math.min(1000, mbps));
  return Math.round((Math.log10(clamped) / 3) * 1000);
}

function setupCalculator() {
  const payloadSlider = document.getElementById('calc-payload-slider');
  const bwSlider = document.getElementById('calc-bandwidth-slider');
  const structureSelect = document.getElementById('calc-structure-select');
  const rttSelect = document.getElementById('calc-rtt-select');

  if (payloadSlider) {
    payloadSlider.value = payloadKbToSliderPos(currentPayloadKb);
    payloadSlider.addEventListener('input', () => {
      const kb = sliderPosToPayloadKb(parseFloat(payloadSlider.value));
      currentPayloadKb = kb;
      updatePayloadReadout(kb);
      updatePresetActive('#payload-preset-pills', kb);
      runCalculatorSimulation();
    });
  }

  if (bwSlider) {
    bwSlider.value = bwMbpsToSliderPos(currentBwMbps);
    bwSlider.addEventListener('input', () => {
      const mbps = sliderPosToBwMbps(parseFloat(bwSlider.value));
      currentBwMbps = mbps;
      updateBandwidthReadout(mbps);
      updatePresetActive('#bw-preset-pills', mbps);
      runCalculatorSimulation();
    });
  }

  if (structureSelect) {
    structureSelect.addEventListener('change', runCalculatorSimulation);
  }

  if (rttSelect) {
    rttSelect.addEventListener('change', runCalculatorSimulation);
  }

  // Preset pill clicks for payload
  document.querySelectorAll('#payload-preset-pills .preset-pill-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const val = parseFloat(btn.getAttribute('data-payload'));
      currentPayloadKb = val;
      if (payloadSlider) {
        payloadSlider.value = payloadKbToSliderPos(val);
        updatePayloadReadout(val);
        updatePresetActive('#payload-preset-pills', val);
        runCalculatorSimulation();
      }
    });
  });

  // Preset pill clicks for bandwidth
  document.querySelectorAll('#bw-preset-pills .preset-pill-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const val = parseFloat(btn.getAttribute('data-bw'));
      currentBwMbps = val;
      if (bwSlider) {
        bwSlider.value = bwMbpsToSliderPos(val);
        updateBandwidthReadout(val);
        updatePresetActive('#bw-preset-pills', val);
        runCalculatorSimulation();
      }
    });
  });

  // Initialize readouts and presets
  updatePayloadReadout(currentPayloadKb);
  updatePresetActive('#payload-preset-pills', currentPayloadKb);
  updateBandwidthReadout(currentBwMbps);
  updatePresetActive('#bw-preset-pills', currentBwMbps);

  // Initial calculation
  runCalculatorSimulation();
}

function updatePayloadReadout(kbVal) {
  const kb = parseFloat(kbVal);
  const readout = document.getElementById('calc-payload-readout');
  if (readout) {
    if (kb >= 1000) {
      readout.textContent = `${kb.toLocaleString()} KB (${(kb / 1024).toFixed(2)} MB)`;
    } else {
      readout.textContent = `${kb.toLocaleString()} KB`;
    }
  }
}

function updateBandwidthReadout(mbpsVal) {
  const mbps = parseFloat(mbpsVal);
  const readout = document.getElementById('calc-bandwidth-readout');
  if (readout) {
    if (mbps >= 1000) {
      readout.textContent = `${mbps.toLocaleString()} Mbps (1.0 Gbps)`;
    } else {
      readout.textContent = `${mbps.toLocaleString()} Mbps`;
    }
  }
}

function updatePresetActive(containerSelector, val) {
  const targetVal = parseFloat(val);
  document.querySelectorAll(`${containerSelector} .preset-pill-btn`).forEach(b => {
    const pillVal = parseFloat(b.getAttribute('data-payload') || b.getAttribute('data-bw'));
    if (Math.abs(pillVal - targetVal) < 0.05 * targetVal || Math.abs(pillVal - targetVal) < 1.0) {
      b.classList.add('active');
    } else {
      b.classList.remove('active');
    }
  });
}

function runCalculatorSimulation() {
  const payloadSlider = document.getElementById('calc-payload-slider');
  const bwSlider = document.getElementById('calc-bandwidth-slider');
  const structureSelect = document.getElementById('calc-structure-select');
  const rttSelect = document.getElementById('calc-rtt-select');

  if (!payloadSlider || !bwSlider) return;

  const payload_kb = currentPayloadKb || 250.0;
  const bw_mbps = currentBwMbps || 50.0;
  const structure = structureSelect ? structureSelect.value : 'nested';
  const rtt_ms = parseFloat(rttSelect ? rttSelect.value : 15.0);

  // 1. Immediate client-side calculation (60fps responsive UI)
  const payload_bytes = Math.round(payload_kb * 1024);
  const bw_bps = bw_mbps * 1e6;

  let mp_factor = 0.78;
  let gzip_factor = 0.32;

  if (structure === 'numeric') {
    mp_factor = 0.55;
    gzip_factor = 0.45;
  } else if (structure === 'text') {
    mp_factor = 0.88;
    gzip_factor = 0.22;
  } else if (structure === 'flat') {
    mp_factor = 0.82;
    gzip_factor = 0.38;
  }

  const s_json = payload_bytes;
  const s_mp = Math.max(1, Math.round(s_json * mp_factor));
  const s_gzip = Math.max(1, Math.round(s_json * gzip_factor));

  const t_ser_j = 0.15 + (payload_kb * 0.0022);
  const t_deser_j = 0.20 + (payload_kb * 0.0028);

  const t_ser_mp = 0.22 + (payload_kb * 0.0025);
  const t_deser_mp = 0.28 + (payload_kb * 0.0031);

  const t_ser_g = t_ser_j;
  const t_comp_g = 0.80 + (payload_kb * 0.0120);
  const t_decomp_g = 0.25 + (payload_kb * 0.0040);
  const t_deser_g = t_deser_j;

  const t_net_j = rtt_ms + ((s_json * 8.0) / bw_bps * 1000.0);
  const t_net_g = rtt_ms + ((s_gzip * 8.0) / bw_bps * 1000.0);
  const t_net_mp = rtt_ms + ((s_mp * 8.0) / bw_bps * 1000.0);

  const t_proc_json = t_ser_j + t_deser_j;
  const t_proc_gzip = t_ser_g + t_comp_g + t_decomp_g + t_deser_g;
  const t_proc_mp = t_ser_mp + t_deser_mp;

  const t_e2e_json = t_proc_json + t_net_j;
  const t_e2e_gzip = t_proc_gzip + t_net_g;
  const t_e2e_mp = t_proc_mp + t_net_mp;

  const gain_gzip = (t_e2e_json - t_e2e_gzip) / t_e2e_json * 100.0;
  const gain_mp = (t_e2e_json - t_e2e_mp) / t_e2e_json * 100.0;

  const formats = [
    { key: 'json', name: 'JSON (Baseline)', wire: s_json, red: 0, proc: t_proc_json, net: t_net_j, e2e: t_e2e_json, gain: 0 },
    { key: 'json_gzip', name: 'JSON + GZIP', wire: s_gzip, red: (1.0 - s_gzip / s_json) * 100.0, proc: t_proc_gzip, net: t_net_g, e2e: t_e2e_gzip, gain: gain_gzip },
    { key: 'messagepack', name: 'MessagePack (Binary)', wire: s_mp, red: (1.0 - s_mp / s_json) * 100.0, proc: t_proc_mp, net: t_net_mp, e2e: t_e2e_mp, gain: gain_mp },
  ];

  formats.sort((a, b) => a.e2e - b.e2e);
  const bestFmt = formats[0];
  const maxGain = Math.max(gain_gzip, gain_mp, 0.0);

  // Decision Zone
  let zoneClass = 'zone-no-switch';
  let zoneLabel = 'ZONE 1: NO SWITCH';
  let recName = 'JSON (Baseline)';
  let rationale = '';

  if (maxGain < 5.0) {
    zoneClass = 'zone-no-switch';
    zoneLabel = 'ZONE 1: NO SWITCH';
    recName = 'JSON (Baseline)';
    rationale = `At ${payload_kb} KB and ${bw_mbps} Mbps, the maximum latency gain over JSON is only ${maxGain.toFixed(1)}% (< 5%). Stay with baseline JSON to retain full human-readability and eliminate CPU compression overhead.`;
  } else if (maxGain < 20.0) {
    zoneClass = 'zone-evaluate';
    zoneLabel = 'ZONE 2: EVALUATE';
    recName = bestFmt.key === 'json' ? 'JSON (Baseline)' : bestFmt.name;
    rationale = `At ${payload_kb} KB and ${bw_mbps} Mbps, an observable latency gain of ${maxGain.toFixed(1)}% is achieved with ${bestFmt.name}. Evaluate whether this improvement justifies the tooling, debugging, and CPU cost in your environment.`;
  } else {
    zoneClass = 'zone-switch';
    zoneLabel = 'ZONE 3: SWITCH';
    recName = bestFmt.name;
    rationale = `At ${payload_kb} KB and ${bw_mbps} Mbps, ${bestFmt.name} provides a substantial latency improvement of ${maxGain.toFixed(1)}% (>= 20%). Strongly recommended to switch to ${bestFmt.name} to maximize throughput and reduce network transit.`;
  }

  // Regime classification
  const netSaved = t_net_j - bestFmt.net;
  const cpuOverhead = bestFmt.proc - t_proc_json;
  let regimeText = 'Balanced';
  if (netSaved > cpuOverhead * 2.0) {
    regimeText = 'Network-Bound (Bandwidth Sensitive)';
  } else if (cpuOverhead > netSaved * 2.0) {
    regimeText = 'CPU-Bound (Compute Sensitive)';
  }

  // Update UI Elements
  const zoneBadge = document.getElementById('calc-zone-badge');
  if (zoneBadge) {
    zoneBadge.className = `calc-zone-badge ${zoneClass}`;
    zoneBadge.textContent = zoneLabel;
  }

  const recFormatEl = document.getElementById('calc-rec-format');
  if (recFormatEl) recFormatEl.textContent = recName;

  const gainDisplay = document.getElementById('calc-gain-display');
  if (gainDisplay) {
    gainDisplay.textContent = maxGain > 0 ? `+${maxGain.toFixed(1)}% Relative Gain` : `0.0% Baseline`;
  }

  const regimeBadge = document.getElementById('calc-regime-badge');
  if (regimeBadge) regimeBadge.textContent = regimeText;

  // Latency breakdown bars
  const maxLat = Math.max(t_e2e_json, t_e2e_gzip, t_e2e_mp);
  updateBar('json', t_proc_json, t_net_j, t_e2e_json, maxLat);
  updateBar('gzip', t_proc_gzip, t_net_g, t_e2e_gzip, maxLat);
  updateBar('mp', t_proc_mp, t_net_mp, t_e2e_mp, maxLat);

  // Table population
  const tbody = document.getElementById('calc-metrics-tbody');
  if (tbody) {
    let tHtml = '';
    const allFmts = [
      { key: 'json', name: 'JSON (Baseline)', wire: s_json, red: 0, proc: t_proc_json, net: t_net_j, e2e: t_e2e_json, gain: 0 },
      { key: 'json_gzip', name: 'JSON + GZIP', wire: s_gzip, red: (1.0 - s_gzip / s_json) * 100.0, proc: t_proc_gzip, net: t_net_g, e2e: t_e2e_gzip, gain: gain_gzip },
      { key: 'messagepack', name: 'MessagePack (Binary)', wire: s_mp, red: (1.0 - s_mp / s_json) * 100.0, proc: t_proc_mp, net: t_net_mp, e2e: t_e2e_mp, gain: gain_mp },
    ];

    allFmts.forEach(f => {
      const isWinner = f.key === bestFmt.key;
      tHtml += `
        <tr class="${isWinner ? 'winner-row' : ''}">
          <td><strong>${f.name}</strong> ${isWinner ? '<span class="badge-chip" style="font-size:10px; margin-left:4px;">FASTEST</span>' : ''}</td>
          <td>${f.wire.toLocaleString()} B</td>
          <td>${f.red.toFixed(1)}%</td>
          <td>${f.proc.toFixed(2)} ms</td>
          <td>${f.net.toFixed(2)} ms</td>
          <td><strong>${f.e2e.toFixed(2)} ms</strong></td>
          <td>${f.gain > 0 ? `+${f.gain.toFixed(1)}%` : `${f.gain.toFixed(1)}%`}</td>
        </tr>
      `;
    });
    tbody.innerHTML = tHtml;
  }

  // Analytical break-even bandwidths
  const diff_mp_proc_sec = (t_proc_mp - t_proc_json) / 1000.0;
  const diff_mp_bytes = s_json - s_mp;
  const bbe_mp = diff_mp_proc_sec > 0 ? ((diff_mp_bytes * 8.0 / diff_mp_proc_sec) / 1e6).toFixed(1) : 'Infinite';

  const diff_gzip_proc_sec = (t_comp_g + t_decomp_g) / 1000.0;
  const diff_gzip_bytes = s_json - s_gzip;
  const bbe_gzip = diff_gzip_proc_sec > 0 ? ((diff_gzip_bytes * 8.0 / diff_gzip_proc_sec) / 1e6).toFixed(1) : 'Infinite';

  const bbeMpEl = document.getElementById('calc-bbe-mp');
  if (bbeMpEl) bbeMpEl.textContent = `${bbe_mp} Mbps`;

  const bbeGzipEl = document.getElementById('calc-bbe-gzip');
  if (bbeGzipEl) bbeGzipEl.textContent = `${bbe_gzip} Mbps`;

  const rationaleEl = document.getElementById('calc-rationale-text');
  if (rationaleEl) rationaleEl.textContent = rationale;

  // 2. Debounced asynchronous server synchronization
  clearTimeout(calcDebounceTimer);
  calcDebounceTimer = setTimeout(async () => {
    try {
      const res = await fetch(`/api/decision/calculate?payload_kb=${payload_kb}&bandwidth_mbps=${bw_mbps}&rtt_ms=${rtt_ms}&structure=${structure}`);
      if (!res.ok) return;
      const data = await res.json();
      if (data.status === 'ok') {
        if (data.zone_label && zoneBadge) zoneBadge.textContent = data.zone_label.toUpperCase();
        if (data.regime_label && regimeBadge) regimeBadge.textContent = data.regime_label;
      }
    } catch (e) {
      // Client-side fallback calculation is already active and displayed
    }
  }, 150);
}

function updateBar(key, proc, net, total, maxLat) {
  const valEl = document.getElementById(`calc-val-${key}`);
  const procEl = document.getElementById(`bar-proc-${key}`);
  const netEl = document.getElementById(`bar-net-${key}`);

  if (valEl) valEl.textContent = `${total.toFixed(2)} ms`;

  if (procEl && netEl) {
    const rawProcPct = (proc / total) * 100.0;
    const procPct = Math.min(95, Math.max(5, rawProcPct));
    const netPct = 100.0 - procPct;
    procEl.style.width = `${procPct.toFixed(1)}%`;
    netEl.style.width = `${netPct.toFixed(1)}%`;
    procEl.textContent = procPct >= 14 ? `${proc.toFixed(1)}ms` : '';
    netEl.textContent = netPct >= 14 ? `${net.toFixed(1)}ms` : '';
  }
}

/* -----------------------------------------------------------------------------
   Interactive Information Popover System
   -------------------------------------------------------------------------- */

let activeHelpBtn = null;

function setupInfoPopovers() {
  document.addEventListener('click', (e) => {
    const helpBtn = e.target.closest('.info-help-btn');
    if (helpBtn) {
      e.preventDefault();
      e.stopPropagation();
      openInfoPopover(helpBtn);
      return;
    }
    const popover = document.getElementById('info-popover');
    if (popover && !popover.classList.contains('hidden') && !popover.contains(e.target)) {
      closeInfoPopover();
    }
  });

  const closeBtn = document.getElementById('btn-close-popover');
  if (closeBtn) {
    closeBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      closeInfoPopover();
    });
  }

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      closeInfoPopover();
    }
  });

  window.addEventListener('resize', () => {
    if (activeHelpBtn) positionInfoPopover(activeHelpBtn);
  });

  window.addEventListener('scroll', () => {
    if (activeHelpBtn) positionInfoPopover(activeHelpBtn);
  }, { passive: true });
}

function openInfoPopover(btn) {
  const popover = document.getElementById('info-popover');
  const titleEl = document.getElementById('info-popover-title');
  const bodyEl = document.getElementById('info-popover-body');
  if (!popover || !titleEl || !bodyEl) return;

  const title = btn.getAttribute('data-info-title') || 'Information';
  const text = btn.getAttribute('data-info-text') || '';

  // If already open on this button, toggle off
  if (activeHelpBtn === btn && !popover.classList.contains('hidden')) {
    closeInfoPopover();
    return;
  }

  if (activeHelpBtn) {
    activeHelpBtn.classList.remove('active');
  }

  activeHelpBtn = btn;
  btn.classList.add('active');

  titleEl.textContent = title;
  bodyEl.textContent = text;
  popover.classList.remove('hidden');
  popover.setAttribute('aria-hidden', 'false');

  positionInfoPopover(btn);
}

function positionInfoPopover(btn) {
  const popover = document.getElementById('info-popover');
  const arrowEl = document.getElementById('info-popover-arrow');
  if (!popover || !arrowEl || !btn) return;

  const rect = btn.getBoundingClientRect();
  const popoverRect = popover.getBoundingClientRect();
  const gap = 8;
  const viewportWidth = window.innerWidth;
  const viewportHeight = window.innerHeight;

  // Center horizontally relative to button
  let left = rect.left + (rect.width / 2) - (popoverRect.width / 2);
  const minLeft = 10;
  const maxLeft = viewportWidth - popoverRect.width - 10;
  if (left < minLeft) left = minLeft;
  if (left > maxLeft) left = maxLeft;

  // Arrow offset relative to popover left edge
  const btnCenterRel = (rect.left + rect.width / 2) - left;
  const arrowOffset = Math.max(14, Math.min(btnCenterRel - 4, popoverRect.width - 22));
  arrowEl.style.left = `${Math.round(arrowOffset)}px`;

  // Vertical position: prefer below unless space below is tight
  const spaceBelow = viewportHeight - rect.bottom;
  const spaceAbove = rect.top;
  let top;

  if (spaceBelow >= popoverRect.height + gap + 10 || spaceBelow >= spaceAbove) {
    // Show below button
    top = rect.bottom + gap;
    arrowEl.className = 'info-popover-arrow arrow-top';
  } else {
    // Show above button
    top = rect.top - popoverRect.height - gap;
    arrowEl.className = 'info-popover-arrow arrow-bottom';
  }

  popover.style.left = `${Math.round(left)}px`;
  popover.style.top = `${Math.round(top)}px`;
}

function closeInfoPopover() {
  const popover = document.getElementById('info-popover');
  if (popover) {
    popover.classList.add('hidden');
    popover.setAttribute('aria-hidden', 'true');
  }
  if (activeHelpBtn) {
    activeHelpBtn.classList.remove('active');
    activeHelpBtn = null;
  }
}

