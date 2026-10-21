/**
 * The Cloud Scraper - Frontend Dashboard Application Logic
 * Premium CAD Course Project Web Dashboard
 * Manages Tabs, Live Scraping, SSRF Guardrails, Sorting, Pagination,
 * Execution History, CSV/JSON Exports, and Dual-Tier Storage Disambiguation.
 */

document.addEventListener('DOMContentLoaded', () => {
  // Global State
  let currentSiteId = 'books_toscrape';
  let currentRecords = [];
  let filteredRecords = [];
  let currentSortField = null;
  let currentSortAsc = true;
  let currentPage = 1;
  let pageSize = 25;
  let loadingInterval = null;

  // DOM Elements - Navigation & Layout
  const sidebar = document.getElementById('sidebar');
  const mobileMenuBtn = document.getElementById('mobileMenuBtn');
  const navItems = document.querySelectorAll('.nav-item[data-tab]');
  const tabPanes = document.querySelectorAll('.tab-pane');
  const currentViewTitle = document.getElementById('currentViewTitle');
  const currentViewSubtitle = document.getElementById('currentViewSubtitle');
  const sidebarRecordsCount = document.getElementById('sidebarRecordsCount');
  const backendStatusBadge = document.getElementById('backendStatusBadge');
  const backendStatusLabel = document.getElementById('backendStatusLabel');

  // DOM Elements - Overview
  const statTotalScraped = document.getElementById('statTotalScraped');
  const statTotalValid = document.getElementById('statTotalValid');
  const statTotalDuplicates = document.getElementById('statTotalDuplicates');
  const statTotalTransformed = document.getElementById('statTotalTransformed');
  const statRunsSummary = document.getElementById('statRunsSummary');
  const statRunsSub = document.getElementById('statRunsSub');
  const statLatestDuration = document.getElementById('statLatestDuration');
  const statLocalFilesCount = document.getElementById('statLocalFilesCount');
  const overviewRecentRunsBody = document.getElementById('overviewRecentRunsBody');
  const overviewQuickScrapeBtn = document.getElementById('overviewQuickScrapeBtn');
  const overviewViewAllHistoryBtn = document.getElementById('overviewViewAllHistoryBtn');

  // DOM Elements - Workspace
  const siteSelector = document.getElementById('siteSelector');
  const siteHint = document.getElementById('siteHint');
  const customUrlInput = document.getElementById('customUrlInput');
  const pageLimitInput = document.getElementById('pageLimitInput');
  const timeoutInput = document.getElementById('timeoutInput');
  const activeTargetUrlPreview = document.getElementById('activeTargetUrlPreview');
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

  // DOM Elements - Step Functions Stages
  const stagesCard = document.getElementById('stagesCard');
  const sfnExecIdBadge = document.getElementById('sfnExecIdBadge');
  const stagesList = document.getElementById('stagesList');

  // DOM Elements - Results Table & Pagination
  const tableCountBadge = document.getElementById('tableCountBadge');
  const tableSearchInput = document.getElementById('tableSearchInput');
  const pageSizeSelector = document.getElementById('pageSizeSelector');
  const tableHeaders = document.getElementById('tableHeaders');
  const tableBody = document.getElementById('tableBody');
  const paginationInfo = document.getElementById('paginationInfo');
  const prevPageBtn = document.getElementById('prevPageBtn');
  const nextPageBtn = document.getElementById('nextPageBtn');
  const currentPageIndicator = document.getElementById('currentPageIndicator');
  const downloadCsvBtn = document.getElementById('downloadCsvBtn');
  const downloadJsonBtn = document.getElementById('downloadJsonBtn');
  const copyJsonBtn = document.getElementById('copyJsonBtn');
  const jsonCodeBlock = document.getElementById('jsonCodeBlock');

  // DOM Elements - History
  const fullHistoryTableBody = document.getElementById('fullHistoryTableBody');
  const refreshHistoryBtn = document.getElementById('refreshHistoryBtn');

  // DOM Elements - Storage
  const localFilePath = document.getElementById('localFilePath');
  const storageFilesPreview = document.getElementById('storageFilesPreview');
  const downloadLocalBtn = document.getElementById('downloadLocalBtn');
  const downloadCsvLocalBtn = document.getElementById('downloadCsvLocalBtn');

  // Tab Title Metadata
  const tabMetadata = {
    overview: {
      title: 'Overview & Telemetry',
      subtitle: 'Live pipeline health, dataset statistics, and execution audit history',
    },
    workspace: {
      title: 'Scrape Workspace & Controls',
      subtitle: 'Configure target websites, pagination limits, timeouts, and execution triggers',
    },
    results: {
      title: 'Results & Structured Dataset',
      subtitle: 'Inspect, filter, sort, and export cleaned and deduplicated records',
    },
    history: {
      title: 'Execution Audit Trail',
      subtitle: 'Persisted history of serverless pipeline runs with latency and cost metrics',
    },
    storage: {
      title: 'Storage & Lineage Architecture',
      subtitle: 'Dual-tier storage inspection distinguishing local JSON archives from AWS targets',
    },
    architecture: {
      title: 'Step Functions ETL Architecture',
      subtitle: 'Serverless state machine workflow pattern with SQS DLQ fault isolation',
    },
  };

  // 1. Tab Switching Controller
  function switchTab(tabId) {
    navItems.forEach(item => {
      const match = item.getAttribute('data-tab') === tabId;
      item.classList.toggle('active', match);
    });

    tabPanes.forEach(pane => {
      pane.classList.toggle('active', pane.id === `pane-${tabId}`);
    });

    const meta = tabMetadata[tabId] || tabMetadata.overview;
    currentViewTitle.textContent = meta.title;
    currentViewSubtitle.textContent = meta.subtitle;

    if (sidebar.classList.contains('open')) {
      sidebar.classList.remove('open');
    }

    if (tabId === 'history') {
      loadFullHistory();
    } else if (tabId === 'overview') {
      loadOverviewMetrics();
    }
  }

  navItems.forEach(item => {
    item.addEventListener('click', (e) => {
      e.preventDefault();
      const tabId = item.getAttribute('data-tab');
      switchTab(tabId);
    });
  });

  if (mobileMenuBtn) {
    mobileMenuBtn.addEventListener('click', () => {
      sidebar.classList.toggle('open');
    });
  }

  if (overviewQuickScrapeBtn) {
    overviewQuickScrapeBtn.addEventListener('click', () => switchTab('workspace'));
  }

  if (overviewViewAllHistoryBtn) {
    overviewViewAllHistoryBtn.addEventListener('click', () => switchTab('history'));
  }

  // 2. Health & System Status Check
  async function checkBackendStatus() {
    try {
      const res = await fetch('/api/status');
      if (res.ok) {
        const data = await res.json();
        backendStatusBadge.textContent = 'Backend: ONLINE';
        backendStatusBadge.className = 'badge badge-green';
        backendStatusLabel.textContent = 'Backend: ONLINE';
        updateStorageFiles(data.local_output_files || []);
      } else {
        backendStatusBadge.textContent = 'Backend: HTTP Error';
        backendStatusBadge.className = 'badge badge-outline';
        backendStatusLabel.textContent = 'API Error';
      }
    } catch (err) {
      backendStatusBadge.textContent = 'Backend: Offline';
      backendStatusBadge.className = 'badge badge-outline';
      backendStatusLabel.textContent = 'Offline (Run server.py)';
    }
  }

  function updateStorageFiles(files) {
    statLocalFilesCount.textContent = `${files.length} active JSON file(s) in output/`;
    if (storageFilesPreview) {
      if (!files.length) {
        storageFilesPreview.innerHTML = '<span class="text-dim">No stored JSON files yet.</span>';
      } else {
        storageFilesPreview.innerHTML = files.map(f => {
          const sid = f.replace('.json', '');
          return `
            <div style="display:flex; justify-content:space-between; align-items:center;">
              <code>output/${escapeHtml(f)}</code>
              <div>
                <a href="/api/download/${sid}" class="btn btn-sm btn-outline" style="padding:0.2rem 0.5rem; font-size:0.75rem;">JSON</a>
                <a href="/api/download/${sid}?format=csv" class="btn btn-sm btn-outline" style="padding:0.2rem 0.5rem; font-size:0.75rem;">CSV</a>
              </div>
            </div>
          `;
        }).join('');
      }
    }
  }

  // 3. Site Selector Logic
  const siteConfigHints = {
    books_toscrape: {
      url: 'https://books.toscrape.com/catalogue/page-1.html',
      hint: 'Books to Scrape: E-commerce sandbox evaluating product titles, prices in GBP, and 1-5 star ratings.',
    },
    quotes_toscrape: {
      url: 'https://quotes.toscrape.com/',
      hint: 'Quotes to Scrape: Evaluates famous quotes, author attribution, and categorical tags arrays.',
    },
    webscraper_laptops: {
      url: 'https://webscraper.io/test-sites/e-commerce/allinone/computers/laptops',
      hint: 'WebScraper Laptops Sandbox: 117 laptop models with price, specifications, star ratings, and review counts.',
    },
    hacker_news: {
      url: 'https://news.ycombinator.com/',
      hint: 'Hacker News Permitted Feed: Evaluates 30 frontpage technology news articles, ranks, and external URLs.',
    },
  };

  siteSelector.addEventListener('change', (e) => {
    currentSiteId = e.target.value;
    const cfg = siteConfigHints[currentSiteId] || { url: '', hint: '' };
    siteHint.textContent = cfg.hint;
    if (!customUrlInput.value.trim()) {
      activeTargetUrlPreview.textContent = cfg.url;
    }
    localFilePath.textContent = `output/${currentSiteId}.json`;
    downloadLocalBtn.href = `/api/download/${currentSiteId}`;
    downloadCsvLocalBtn.href = `/api/download/${currentSiteId}?format=csv`;

    // Attempt to load existing data for this site
    loadStoredDataForSite(currentSiteId);
  });

  customUrlInput.addEventListener('input', (e) => {
    const val = e.target.value.trim();
    if (val) {
      activeTargetUrlPreview.textContent = val;
    } else {
      const cfg = siteConfigHints[currentSiteId] || { url: '' };
      activeTargetUrlPreview.textContent = cfg.url;
    }
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
        ? 'Injecting network failure to trigger Step Functions Catch Block & SQS DLQ...'
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

  // 5. Render Step Functions Stages
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
            <span class="stage-name">${icon} ${escapeHtml(stage.name)}</span>
            <span class="stage-service">${escapeHtml(stage.service)}</span>
          </div>
          <span class="stage-detail">${escapeHtml(stage.detail)}</span>
        </div>
      `;
    }).join('');
  }

  // 6. Scrape Pipeline Execution Handler
  async function executeScrapePipeline(simulateFailure = false) {
    const selectedSite = siteSelector.value;
    const customUrl = customUrlInput.value.trim() || null;
    const pageLimit = parseInt(pageLimitInput.value, 10) || 1;
    const timeoutSeconds = parseInt(timeoutInput.value, 10) || 15;
    const sourceMode = document.querySelector('input[name="sourceMode"]:checked')?.value || 'live';
    const isFixture = sourceMode === 'fixture';

    setLoading(true, simulateFailure);

    try {
      const response = await fetch('/api/scrape', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          site_id: selectedSite,
          custom_url: customUrl,
          page_limit: pageLimit,
          timeout_seconds: timeoutSeconds,
          fixture: isFixture,
          simulate_failure: simulateFailure,
        }),
      });

      const data = await response.json();
      setLoading(false);

      if (data.status === 'SUCCESS') {
        successBanner.style.display = 'flex';
        successTitle.textContent = `Pipeline Execution Succeeded (${Number(data.elapsed_seconds || 0).toFixed(2)}s)`;
        successMsg.textContent = `Harvested ${data.scraped} records (${data.pages_scraped || 1} page(s)), verified ${data.valid} valid, removed ${data.duplicates_removed} duplicates. Stored ${data.transformed} clean entities in local archive.`;

        renderStages(data.stages, false);
        setLoadedRecords(data.records || [], selectedSite);

        // Switch to Results Tab automatically so the user immediately sees the data
        switchTab('results');

        // Refresh overview stats and history
        loadOverviewMetrics();
      } else {
        errorBanner.style.display = 'flex';
        errorTitle.textContent = simulateFailure
          ? 'Fault Tolerance Verification: Step Functions Catch Block Engaged'
          : 'Scraper Pipeline Error Caught';
        errorMsg.textContent = simulateFailure
          ? `Injected simulated connection failure. State Machine trapped error '${data.error || 'Connection refused'}', diverted failed event to Amazon SQS Dead Letter Queue (ScraperDLQ), and published alarm to Amazon SNS.`
          : (data.error || 'An error occurred during pipeline execution.');

        renderStages(data.stages, true);
        if (data.records && data.records.length > 0) {
          setLoadedRecords(data.records, selectedSite);
        }
        loadOverviewMetrics();
      }
    } catch (err) {
      setLoading(false);
      errorBanner.style.display = 'flex';
      errorTitle.textContent = 'API Connection Error';
      errorMsg.textContent = `Could not reach server at /api/scrape: ${err.message}. Please verify python server.py is running.`;
    }
  }

  scrapeBtn.addEventListener('click', () => executeScrapePipeline(false));
  simulateFailBtn.addEventListener('click', () => executeScrapePipeline(true));

  // 7. Results Table, Sorting, Filtering & Pagination
  function setLoadedRecords(records, siteId) {
    currentSiteId = siteId;
    currentRecords = records || [];
    filteredRecords = [...currentRecords];
    currentPage = 1;
    sidebarRecordsCount.textContent = currentRecords.length;
    tableCountBadge.textContent = `${currentRecords.length} records`;

    renderTableHeaders(currentRecords, siteId);
    renderTablePage();
    renderJsonPreview(currentRecords);

    // Update storage links
    localFilePath.textContent = `output/${siteId}.json`;
    downloadLocalBtn.href = `/api/download/${siteId}`;
    downloadCsvLocalBtn.href = `/api/download/${siteId}?format=csv`;
  }

  function renderTableHeaders(records, siteId) {
    if (!records.length) {
      tableHeaders.innerHTML = '<th>Status</th>';
      return;
    }

    if (siteId === 'books_toscrape' || records[0]?.price !== undefined) {
      tableHeaders.innerHTML = `
        <th>#</th>
        <th class="sortable" data-field="title">Title</th>
        <th class="sortable" data-field="price">Price</th>
        <th class="sortable" data-field="rating">Rating</th>
        <th>Availability</th>
        <th>Record ID</th>
      `;
    } else if (siteId === 'quotes_toscrape') {
      tableHeaders.innerHTML = `
        <th>#</th>
        <th class="sortable" data-field="quote">Quote</th>
        <th class="sortable" data-field="author">Author</th>
        <th>Tags</th>
        <th>Record ID</th>
      `;
    } else if (siteId === 'webscraper_laptops') {
      tableHeaders.innerHTML = `
        <th>#</th>
        <th class="sortable" data-field="title">Laptop Model</th>
        <th class="sortable" data-field="price">Price</th>
        <th class="sortable" data-field="rating">Rating</th>
        <th>Reviews</th>
        <th>Record ID</th>
      `;
    } else if (siteId === 'hacker_news') {
      tableHeaders.innerHTML = `
        <th>#</th>
        <th class="sortable" data-field="rank">Rank</th>
        <th class="sortable" data-field="title">Article Title</th>
        <th>External Link</th>
        <th>Record ID</th>
      `;
    } else {
      // Generic header from first record
      const keys = Object.keys(records[0]).slice(0, 5);
      tableHeaders.innerHTML = '<th>#</th>' + keys.map(k => `<th class="sortable" data-field="${k}">${escapeHtml(k)}</th>`).join('') + '<th>Record ID</th>';
    }

    // Attach sort click handlers
    tableHeaders.querySelectorAll('th.sortable').forEach(th => {
      th.addEventListener('click', () => {
        const field = th.getAttribute('data-field');
        sortTable(field);
      });
    });
  }

  function sortTable(field) {
    if (currentSortField === field) {
      currentSortAsc = !currentSortAsc;
    } else {
      currentSortField = field;
      currentSortAsc = true;
    }

    // Update header classes
    tableHeaders.querySelectorAll('th.sortable').forEach(th => {
      th.classList.remove('sort-asc', 'sort-desc');
      if (th.getAttribute('data-field') === field) {
        th.classList.add(currentSortAsc ? 'sort-asc' : 'sort-desc');
      }
    });

    filteredRecords.sort((a, b) => {
      let valA = a[field] ?? '';
      let valB = b[field] ?? '';

      if (typeof valA === 'number' && typeof valB === 'number') {
        return currentSortAsc ? valA - valB : valB - valA;
      }
      valA = String(valA).toLowerCase();
      valB = String(valB).toLowerCase();
      if (valA < valB) return currentSortAsc ? -1 : 1;
      if (valA > valB) return currentSortAsc ? 1 : -1;
      return 0;
    });

    currentPage = 1;
    renderTablePage();
  }

  function renderTablePage() {
    if (!filteredRecords.length) {
      tableBody.innerHTML = '<tr><td colspan="6" class="text-center text-muted">No records match the query.</td></tr>';
      paginationInfo.textContent = 'Showing 0 of 0 records';
      prevPageBtn.disabled = true;
      nextPageBtn.disabled = true;
      currentPageIndicator.textContent = 'Page 1 of 1';
      return;
    }

    const totalRecords = filteredRecords.length;
    const totalPages = Math.max(1, Math.ceil(totalRecords / pageSize));
    if (currentPage > totalPages) currentPage = totalPages;
    if (currentPage < 1) currentPage = 1;

    const startIdx = (currentPage - 1) * pageSize;
    const endIdx = Math.min(startIdx + pageSize, totalRecords);
    const pageRecords = filteredRecords.slice(startIdx, endIdx);

    paginationInfo.textContent = `Showing ${startIdx + 1}–${endIdx} of ${totalRecords} records`;
    currentPageIndicator.textContent = `Page ${currentPage} of ${totalPages}`;
    prevPageBtn.disabled = currentPage <= 1;
    nextPageBtn.disabled = currentPage >= totalPages;

    tableBody.innerHTML = pageRecords.map((r, i) => {
      const idx = startIdx + i + 1;
      const recId = (r.record_id || '').substring(0, 14) + '...';

      if (currentSiteId === 'books_toscrape' || (r.price !== undefined && r.availability !== undefined)) {
        const stars = '★'.repeat(r.rating || 0) + '☆'.repeat(Math.max(0, 5 - (r.rating || 0)));
        return `
          <tr>
            <td>${idx}</td>
            <td><strong>${escapeHtml(r.title || 'Untitled')}</strong></td>
            <td><code style="color: #4ade80;">£${Number(r.price).toFixed(2)}</code></td>
            <td><span class="rating-stars">${stars}</span> (${r.rating || 0}/5)</td>
            <td><span class="badge badge-outline">${escapeHtml(r.availability || 'In stock')}</span></td>
            <td><code title="${escapeHtml(r.record_id || '')}">${escapeHtml(recId)}</code></td>
          </tr>
        `;
      } else if (currentSiteId === 'quotes_toscrape') {
        const tags = Array.isArray(r.tags) ? r.tags.map(t => `<span class="badge badge-purple" style="font-size:0.65rem;">${escapeHtml(t)}</span>`).join(' ') : '';
        return `
          <tr>
            <td>${idx}</td>
            <td style="max-width: 400px; font-style: italic;">“${escapeHtml(r.quote || '')}”</td>
            <td><strong>${escapeHtml(r.author || 'Unknown')}</strong></td>
            <td>${tags || '<span style="color:var(--text-dim);">-</span>'}</td>
            <td><code title="${escapeHtml(r.record_id || '')}">${escapeHtml(recId)}</code></td>
          </tr>
        `;
      } else if (currentSiteId === 'webscraper_laptops') {
        const ratingNum = parseInt(r.rating, 10) || 0;
        const stars = '★'.repeat(ratingNum) + '☆'.repeat(Math.max(0, 5 - ratingNum));
        return `
          <tr>
            <td>${idx}</td>
            <td><strong>${escapeHtml(r.title || 'Laptop')}</strong></td>
            <td><code style="color: #4ade80;">$${Number(r.price || 0).toFixed(2)}</code></td>
            <td><span class="rating-stars">${stars}</span> (${ratingNum}/5)</td>
            <td><span class="badge badge-outline">${escapeHtml(r.reviews || '0 reviews')}</span></td>
            <td><code title="${escapeHtml(r.record_id || '')}">${escapeHtml(recId)}</code></td>
          </tr>
        `;
      } else if (currentSiteId === 'hacker_news') {
        return `
          <tr>
            <td>${idx}</td>
            <td><code>${escapeHtml(r.rank || String(idx))}</code></td>
            <td><strong>${escapeHtml(r.title || 'Untitled')}</strong></td>
            <td><a href="${escapeHtml(r.detail_link || '#')}" target="_blank" rel="noopener" style="color:var(--accent-cyan); text-decoration:underline;">View Article &rarr;</a></td>
            <td><code title="${escapeHtml(r.record_id || '')}">${escapeHtml(recId)}</code></td>
          </tr>
        `;
      } else {
        const keys = Object.keys(r).slice(0, 5);
        const cells = keys.map(k => `<td>${escapeHtml(String(r[k] ?? ''))}</td>`).join('');
        return `<tr><td>${idx}</td>${cells}<td><code>${escapeHtml(recId)}</code></td></tr>`;
      }
    }).join('');
  }

  // Search filter
  tableSearchInput.addEventListener('input', (e) => {
    const q = e.target.value.toLowerCase().trim();
    if (!q) {
      filteredRecords = [...currentRecords];
    } else {
      filteredRecords = currentRecords.filter(r => {
        return Object.values(r).some(val => {
          if (Array.isArray(val)) return val.some(v => String(v).toLowerCase().includes(q));
          return String(val).toLowerCase().includes(q);
        });
      });
    }
    currentPage = 1;
    renderTablePage();
  });

  // Page Size Selector
  pageSizeSelector.addEventListener('change', (e) => {
    pageSize = parseInt(e.target.value, 10) || 25;
    currentPage = 1;
    renderTablePage();
  });

  // Prev / Next Page Buttons
  prevPageBtn.addEventListener('click', () => {
    if (currentPage > 1) {
      currentPage--;
      renderTablePage();
    }
  });

  nextPageBtn.addEventListener('click', () => {
    const totalPages = Math.ceil(filteredRecords.length / pageSize);
    if (currentPage < totalPages) {
      currentPage++;
      renderTablePage();
    }
  });

  // 8. JSON Preview & Clipboard
  function renderJsonPreview(records) {
    jsonCodeBlock.textContent = JSON.stringify(records, null, 2);
  }

  copyJsonBtn.addEventListener('click', () => {
    if (!jsonCodeBlock.textContent) return;
    navigator.clipboard.writeText(jsonCodeBlock.textContent).then(() => {
      const orig = copyJsonBtn.textContent;
      copyJsonBtn.textContent = '✅ Copied!';
      setTimeout(() => { copyJsonBtn.textContent = orig; }, 1800);
    });
  });

  // 9. Downloads (JSON and CSV)
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

  downloadCsvBtn.addEventListener('click', () => {
    window.location.href = `/api/download/${currentSiteId}?format=csv`;
  });

  // 10. Load Stored Data From Output File
  async function loadStoredDataForSite(siteId) {
    try {
      const res = await fetch(`/api/data/${siteId}`);
      if (res.ok) {
        const records = await res.json();
        setLoadedRecords(records, siteId);
      }
    } catch (e) {
      // No stored data yet
    }
  }

  // 11. Overview Metrics & History Loader
  async function loadOverviewMetrics() {
    try {
      const res = await fetch('/api/history');
      if (res.ok) {
        const data = await res.json();
        const sum = data.summary || {};
        statTotalScraped.textContent = sum.total_scraped || 0;
        statTotalValid.textContent = sum.total_valid || 0;
        statTotalDuplicates.textContent = sum.total_duplicates_removed || 0;
        statTotalTransformed.textContent = sum.total_transformed || 0;
        statRunsSummary.textContent = `${sum.successful_runs || 0} / ${sum.total_runs || 0}`;
        statRunsSub.textContent = `${sum.successful_runs || 0} successful, ${sum.failed_runs || 0} failed`;
        statLatestDuration.textContent = `${Number(sum.latest_duration || 0).toFixed(2)}s`;

        renderRecentOverviewRuns(data.history ? data.history.slice(0, 5) : []);
      }
    } catch (e) {
      console.warn('Could not load history metrics:', e);
    }
  }

  function renderRecentOverviewRuns(runs) {
    if (!runs.length) {
      overviewRecentRunsBody.innerHTML = '<tr><td colspan="8" class="text-center text-muted">No runs executed yet.</td></tr>';
      return;
    }
    overviewRecentRunsBody.innerHTML = runs.map(r => {
      const isSuccess = r.status === 'SUCCESS';
      const badgeClass = isSuccess ? 'badge-green' : 'badge-purple';
      const dateStr = r.timestamp ? new Date(r.timestamp).toLocaleTimeString() : '-';
      return `
        <tr>
          <td><code style="font-size:0.75rem;">${escapeHtml(dateStr)}</code></td>
          <td><strong>${escapeHtml(r.site_id || '')}</strong></td>
          <td><span class="badge badge-outline">${escapeHtml(r.mode || '')}</span></td>
          <td><span class="badge ${badgeClass}">${escapeHtml(r.status || '')}</span></td>
          <td>${Number(r.duration || 0).toFixed(2)}s</td>
          <td>${r.scraped || 0}</td>
          <td><strong class="text-green">${r.transformed || 0}</strong></td>
          <td><code style="color:var(--accent-yellow);">$${Number(r.cost_usd || 0).toFixed(6)}</code></td>
        </tr>
      `;
    }).join('');
  }

  // 12. Full Execution History Loader
  async function loadFullHistory() {
    try {
      const res = await fetch('/api/history');
      if (res.ok) {
        const data = await res.json();
        const runs = data.history || [];
        if (!runs.length) {
          fullHistoryTableBody.innerHTML = '<tr><td colspan="12" class="text-center text-muted">No execution history found in output/history.json.</td></tr>';
          return;
        }

        fullHistoryTableBody.innerHTML = runs.map(r => {
          const isSuccess = r.status === 'SUCCESS';
          const badgeClass = isSuccess ? 'badge-green' : 'badge-purple';
          const timeFormatted = r.timestamp ? new Date(r.timestamp).toLocaleString() : '-';
          return `
            <tr>
              <td><code>${escapeHtml(r.execution_id || '')}</code></td>
              <td>${escapeHtml(timeFormatted)}</td>
              <td><strong>${escapeHtml(r.site_id || '')}</strong></td>
              <td><span class="badge badge-outline">${escapeHtml(r.mode || '')}</span></td>
              <td><span class="badge ${badgeClass}">${escapeHtml(r.status || '')}</span></td>
              <td>${Number(r.duration || 0).toFixed(2)}s</td>
              <td>${r.scraped || 0}</td>
              <td>${r.valid || 0}</td>
              <td>${r.duplicates_removed || 0}</td>
              <td><strong class="text-green">${r.transformed || 0}</strong></td>
              <td><code style="color:var(--accent-yellow);">$${Number(r.cost_usd || 0).toFixed(6)}</code></td>
              <td>
                <button class="btn btn-sm btn-outline history-view-btn" data-site="${escapeHtml(r.site_id || '')}">View</button>
              </td>
            </tr>
          `;
        }).join('');

        // Attach view buttons
        fullHistoryTableBody.querySelectorAll('.history-view-btn').forEach(btn => {
          btn.addEventListener('click', () => {
            const sid = btn.getAttribute('data-site');
            if (sid) {
              siteSelector.value = sid;
              siteSelector.dispatchEvent(new Event('change'));
              switchTab('results');
            }
          });
        });
      }
    } catch (e) {
      fullHistoryTableBody.innerHTML = `<tr><td colspan="12" class="text-center text-muted">Failed loading history: ${escapeHtml(e.message)}</td></tr>`;
    }
  }

  if (refreshHistoryBtn) {
    refreshHistoryBtn.addEventListener('click', loadFullHistory);
  }

  // 13. Initialization
  checkBackendStatus();
  loadOverviewMetrics();
  loadStoredDataForSite('books_toscrape');

  // Helper: HTML escaping
  function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }
});
