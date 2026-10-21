/**
 * The Cloud Scraper - Frontend Dashboard Application Logic
 * Integrates interactive UI controls with the local Serverless Pipeline REST API.
 * CAD Course Project Demonstration.
 */

document.addEventListener('DOMContentLoaded', () => {
  // Global State
  let currentSiteId = 'books_toscrape';
  let currentRecords = [];
  let loadingInterval = null;

  // DOM Elements
  const backendStatusBadge = document.getElementById('backendStatusBadge');
  const siteSelector = document.getElementById('siteSelector');
  const siteHint = document.getElementById('siteHint');
  const scrapeBtn = document.getElementById('scrapeBtn');
  const scrapeBtnIcon = document.getElementById('scrapeBtnIcon');
  const scrapeBtnText = document.getElementById('scrapeBtnText');
  const simulateFailBtn = document.getElementById('simulateFailBtn');
  const loadingBarWrap = document.getElementById('loadingBarWrap');
  const loadingStatusText = document.getElementById('loadingStatusText');
  const errorBanner = document.getElementById('errorBanner');
  const errorTitle = document.getElementById('errorTitle');
  const errorMsg = document.getElementById('errorMsg');
  const successBanner = document.getElementById('successBanner');
  const successTitle = document.getElementById('successTitle');
  const successMsg = document.getElementById('successMsg');

  // Metrics
  const metricsGrid = document.getElementById('metricsGrid');
  const metricScraped = document.getElementById('metricScraped');
  const metricValid = document.getElementById('metricValid');
  const metricInvalid = document.getElementById('metricInvalid');
  const metricDuplicates = document.getElementById('metricDuplicates');
  const metricClean = document.getElementById('metricClean');
  const metricDuration = document.getElementById('metricDuration');
  const metricCost = document.getElementById('metricCost');

  // Stages & SFN
  const stagesCard = document.getElementById('stagesCard');
  const sfnExecIdBadge = document.getElementById('sfnExecIdBadge');
  const stagesList = document.getElementById('stagesList');

  // Storage
  const storageCard = document.getElementById('storageCard');
  const localFilePath = document.getElementById('localFilePath');
  const downloadLocalBtn = document.getElementById('downloadLocalBtn');

  // Results Table
  const resultsCard = document.getElementById('resultsCard');
  const tableCountBadge = document.getElementById('tableCountBadge');
  const tableSearchInput = document.getElementById('tableSearchInput');
  const tableHeaders = document.getElementById('tableHeaders');
  const tableBody = document.getElementById('tableBody');
  const downloadJsonBtn = document.getElementById('downloadJsonBtn');

  // JSON Preview
  const jsonCard = document.getElementById('jsonCard');
  const copyJsonBtn = document.getElementById('copyJsonBtn');
  const jsonCodeBlock = document.getElementById('jsonCodeBlock');

  // Architecture Accordion
  const archToggleBtn = document.getElementById('archToggleBtn');
  const archToggleText = document.getElementById('archToggleText');
  const archBody = document.getElementById('archBody');

  // 1. Accordion Toggle
  if (archToggleBtn && archBody) {
    archToggleBtn.addEventListener('click', () => {
      const isHidden = archBody.style.display === 'none';
      archBody.style.display = isHidden ? 'block' : 'none';
      archToggleText.textContent = isHidden ? 'Collapse ▲' : 'Expand ▼';
    });
  }

  // 2. Health & Sites Check
  async function checkBackendStatus() {
    try {
      const res = await fetch('/api/status');
      if (res.ok) {
        const data = await res.json();
        backendStatusBadge.textContent = 'Backend: ONLINE (Zero-Cost Mode)';
        backendStatusBadge.className = 'badge badge-green';
      } else {
        backendStatusBadge.textContent = 'Backend: HTTP Error';
        backendStatusBadge.className = 'badge badge-outline';
      }
    } catch (err) {
      backendStatusBadge.textContent = 'Backend: Offline (Start server.py)';
      backendStatusBadge.className = 'badge badge-outline';
    }
  }

  // 3. Site Selector Change
  siteSelector.addEventListener('change', (e) => {
    currentSiteId = e.target.value;
    if (currentSiteId === 'books_toscrape') {
      siteHint.textContent = 'Books to Scrape: Evaluates e-commerce HTML, product titles, sterling prices, and 1-5 star ratings.';
    } else if (currentSiteId === 'quotes_toscrape') {
      siteHint.textContent = 'Quotes to Scrape: Evaluates textual quotes, famous authors, and categorical tag arrays.';
    }
    localFilePath.textContent = `output/${currentSiteId}.json`;
    downloadLocalBtn.href = `/api/download/${currentSiteId}`;
  });

  // 4. Loading State Controller
  const loadingSteps = [
    'Triggering EventBridge dispatcher & initializing Step Functions...',
    'Invoking Scraper Lambda: Fetching target HTML (Robots.txt compliant)...',
    'Executing Validation Lambda: Verifying schema, required fields & types...',
    'Executing Transformation Lambda: Cleaning text & SHA-256 deduplicating...',
    'Executing Storage Lambda: Saving local immutable JSON & preparing DynamoDB write...',
    'Executing FinOps Telemetry Lambda: Calculating CloudWatch metrics & SNS alerts...',
  ];

  function setLoading(isLoading, isFailureTest = false) {
    if (isLoading) {
      scrapeBtn.disabled = true;
      simulateFailBtn.disabled = true;
      scrapeBtnIcon.textContent = '⏳';
      scrapeBtnText.textContent = isFailureTest ? 'Simulating Fault...' : 'Scraping...';
      loadingBarWrap.style.display = 'block';
      errorBanner.style.display = 'none';
      successBanner.style.display = 'none';

      let stepIndex = 0;
      loadingStatusText.textContent = isFailureTest
        ? 'Injecting network failure to trigger Step Functions Catch Block...'
        : loadingSteps[0];

      if (!isFailureTest) {
        loadingInterval = setInterval(() => {
          stepIndex = (stepIndex + 1) % loadingSteps.length;
          loadingStatusText.textContent = loadingSteps[stepIndex];
        }, 600);
      }
    } else {
      if (loadingInterval) {
        clearInterval(loadingInterval);
        loadingInterval = null;
      }
      scrapeBtn.disabled = false;
      simulateFailBtn.disabled = false;
      scrapeBtnIcon.textContent = '▶';
      scrapeBtnText.textContent = 'Scrape Now';
      loadingBarWrap.style.display = 'none';
    }
  }

  // 5. Render Stages
  function renderStages(stages, isFailure = false) {
    if (!stages || !stages.length) return;
    stagesCard.style.display = 'block';

    if (isFailure) {
      sfnExecIdBadge.textContent = 'State Machine: Caught -> SQS DLQ';
      sfnExecIdBadge.className = 'badge badge-purple';
    } else {
      sfnExecIdBadge.textContent = 'State Machine: Succeeded';
      sfnExecIdBadge.className = 'badge badge-green';
    }

    stagesList.innerHTML = stages.map(stage => {
      const isFailed = stage.status === 'FAILED';
      const statusClass = isFailed ? 'failed' : 'completed';
      const icon = isFailed ? '❌' : '✅';
      return `
        <div class="stage-item ${statusClass}">
          <div class="stage-info">
            <span class="stage-name">${icon} ${stage.name}</span>
            <span class="stage-service">${stage.service}</span>
          </div>
          <span class="stage-detail">${stage.detail}</span>
        </div>
      `;
    }).join('');
  }

  // 6. Render Metrics
  function renderMetrics(data) {
    metricsGrid.style.display = 'grid';
    const scraped = data.scraped ?? data.raw_records_count ?? 0;
    const valid = data.valid ?? 0;
    const invalid = data.invalid_count ?? 0;
    const duplicates = data.duplicates_removed ?? 0;
    const clean = data.transformed ?? (data.records ? data.records.length : 0);
    const duration = data.elapsed_seconds ?? data.duration_seconds ?? 0;
    const cost = data.cost_metrics?.estimated_total_usd ?? 0;

    metricScraped.textContent = scraped;
    metricValid.textContent = valid;
    metricInvalid.textContent = `${invalid} rejected`;
    metricDuplicates.textContent = duplicates;
    metricClean.textContent = clean;
    metricDuration.textContent = `${Number(duration).toFixed(2)}s`;
    metricCost.textContent = `$${Number(cost).toFixed(6)}`;
  }

  // 7. Render Results Table
  function renderTable(records, siteId) {
    currentRecords = records || [];
    tableCountBadge.textContent = `${currentRecords.length} records`;

    if (!currentRecords.length) {
      tableHeaders.innerHTML = '<th>Status</th>';
      tableBody.innerHTML = '<tr><td style="text-align:center; color: var(--text-muted);">No records available</td></tr>';
      return;
    }

    resultsCard.style.display = 'block';

    if (siteId === 'books_toscrape' || currentRecords[0]?.price !== undefined) {
      // Books Schema
      tableHeaders.innerHTML = `
        <th>#</th>
        <th>Title</th>
        <th>Price</th>
        <th>Rating</th>
        <th>Availability</th>
        <th>Record ID (SHA-256)</th>
      `;

      tableBody.innerHTML = currentRecords.map((r, i) => {
        const stars = '★'.repeat(r.rating_num || 0) + '☆'.repeat(Math.max(0, 5 - (r.rating_num || 0)));
        return `
          <tr>
            <td>${i + 1}</td>
            <td><strong>${escapeHtml(r.title || 'Untitled')}</strong></td>
            <td><code style="color: #4ade80;">£${Number(r.price).toFixed(2)}</code></td>
            <td><span class="rating-stars">${stars}</span> (${r.rating_num || 0}/5)</td>
            <td><span class="badge badge-outline">${escapeHtml(r.availability || 'In stock')}</span></td>
            <td><code title="${r.record_id}">${(r.record_id || '').substring(0, 12)}...</code></td>
          </tr>
        `;
      }).join('');
    } else {
      // Quotes Schema
      tableHeaders.innerHTML = `
        <th>#</th>
        <th>Quote</th>
        <th>Author</th>
        <th>Tags</th>
        <th>Record ID (SHA-256)</th>
      `;

      tableBody.innerHTML = currentRecords.map((r, i) => {
        const tags = Array.isArray(r.tags) ? r.tags.map(t => `<span class="badge badge-purple" style="font-size:0.65rem;">${escapeHtml(t)}</span>`).join(' ') : '';
        return `
          <tr>
            <td>${i + 1}</td>
            <td style="max-width: 400px; font-style: italic;">“${escapeHtml(r.text || '')}”</td>
            <td><strong>${escapeHtml(r.author || 'Unknown')}</strong></td>
            <td>${tags || '<span style="color:var(--text-muted);">-</span>'}</td>
            <td><code title="${r.record_id}">${(r.record_id || '').substring(0, 12)}...</code></td>
          </tr>
        `;
      }).join('');
    }
  }

  // Search filter for table
  tableSearchInput.addEventListener('input', (e) => {
    const q = e.target.value.toLowerCase().trim();
    const rows = tableBody.querySelectorAll('tr');
    rows.forEach(row => {
      const text = row.textContent.toLowerCase();
      row.style.display = text.includes(q) ? '' : 'none';
    });
  });

  // 8. Render Storage Card
  function renderStorage(siteId, count) {
    storageCard.style.display = 'block';
    localFilePath.textContent = `output/${siteId}.json`;
    downloadLocalBtn.href = `/api/download/${siteId}`;
  }

  // 9. Render JSON Code Block
  function renderJsonPreview(records) {
    jsonCard.style.display = 'block';
    jsonCodeBlock.textContent = JSON.stringify(records, null, 2);
  }

  // 10. Copy JSON button
  copyJsonBtn.addEventListener('click', () => {
    if (!jsonCodeBlock.textContent) return;
    navigator.clipboard.writeText(jsonCodeBlock.textContent).then(() => {
      const orig = copyJsonBtn.textContent;
      copyJsonBtn.textContent = '✅ Copied!';
      setTimeout(() => { copyJsonBtn.textContent = orig; }, 1800);
    }).catch(err => {
      console.error('Clipboard copy failed:', err);
    });
  });

  // 11. Download JSON buttons
  downloadJsonBtn.addEventListener('click', () => {
    if (!currentRecords.length) return;
    const blob = new Blob([JSON.stringify(currentRecords, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${currentSiteId}_clean_records.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  });

  downloadLocalBtn.addEventListener('click', (e) => {
    // Falls back to direct API download
    if (!downloadLocalBtn.getAttribute('href') || downloadLocalBtn.getAttribute('href') === '#') {
      e.preventDefault();
      window.location.href = `/api/download/${currentSiteId}`;
    }
  });

  // 12. Main Scrape Pipeline Execution Handler
  async function executeScrapePipeline(simulateFailure = false) {
    const selectedSite = siteSelector.value;
    const sourceMode = document.querySelector('input[name="sourceMode"]:checked')?.value || 'live';
    const isFixture = sourceMode === 'fixture';

    setLoading(true, simulateFailure);

    try {
      const response = await fetch('/api/scrape', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          site_id: selectedSite,
          fixture: isFixture,
          simulate_failure: simulateFailure,
        }),
      });

      const data = await response.json();
      setLoading(false);

      if (data.status === 'SUCCESS') {
        // Success execution
        successBanner.style.display = 'flex';
        successTitle.textContent = `Pipeline Execution Succeeded (${Number(data.elapsed_seconds || 0).toFixed(2)}s)`;
        successMsg.textContent = `Harvested ${data.scraped} records, verified ${data.valid} valid, removed ${data.duplicates_removed} duplicates. Stored ${data.transformed} clean entities in local JSON archive.`;

        renderMetrics(data);
        renderStages(data.stages, false);
        renderStorage(selectedSite, data.transformed);
        renderTable(data.records, selectedSite);
        renderJsonPreview(data.records);

      } else {
        // Fault or simulation
        errorBanner.style.display = 'flex';
        errorTitle.textContent = simulateFailure
          ? 'Fault Tolerance Verification: Step Functions Catch Block Engaged'
          : 'Scraper Pipeline Error Caught';
        errorMsg.textContent = simulateFailure
          ? `Injected simulated connection failure. State Machine trapped error '${data.error || 'Connection refused'}', diverted failed event to Amazon SQS Dead Letter Queue (ScraperDLQ), and published alarm to Amazon SNS.`
          : (data.error || 'An error occurred during pipeline execution.');

        renderMetrics(data);
        renderStages(data.stages, true);
        if (data.records && data.records.length > 0) {
          renderTable(data.records, selectedSite);
          renderJsonPreview(data.records);
        }
      }
    } catch (err) {
      setLoading(false);
      errorBanner.style.display = 'flex';
      errorTitle.textContent = 'API Connection Error';
      errorMsg.textContent = `Could not reach server at /api/scrape: ${err.message}. Please verify python server.py is running.`;
    }
  }

  // 13. Event Listeners for Action Buttons
  scrapeBtn.addEventListener('click', () => executeScrapePipeline(false));
  simulateFailBtn.addEventListener('click', () => executeScrapePipeline(true));

  // Initialize
  checkBackendStatus();

  // Helper
  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }
});
