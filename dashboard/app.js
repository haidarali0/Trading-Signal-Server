const $ = (s) => document.querySelector(s);
let latestBacktestDetails = [];
let savedSettings = {};
let testRunStarted = false;
let selectedSymbol = '';
let dashboardRequestIndex = 0;
let initialPrefetchDone = false;
let dashboardLoadingTimer = null;
let dashboardLoadingHideTimer = null;
let dashboardLoadingStartedAt = 0;
let dashboardLoadingMinDurationMs = 900;
let dashboardLoadingRequestToken = 0;
let dashboardLoadingActive = false;
let dashboardRefreshInFlight = false;
const symbolCache = new Map();
let liveDashboardData = null;
const metricIndicatorOptions = ['EMA20','EMA50','EMA100','EMA200','sma20','sma50','rsi','macd_line','macd_signal','macd_hist','stoch_k','stoch_d','atr','bb_upper','bb_middle','bb_lower','vwap'];

function renderDashboardPlaceholder() {
  $('#symbol').textContent = '—';
  $('#interval').textContent = '—';
  $('#updated').textContent = '—';
  $('#price').textContent = '—';
  $('#rsi').textContent = '—';
  $('#macd').textContent = '—';
  $('#forecast').textContent = '—';
  $('#news-count').textContent = '0';
  renderMetricCards({});
  renderNewsList($('#live-news-list'), []);
  if (typeof chart === 'function') chart([]);
}

function formatIndicatorLabel(indicator) {
  return String(indicator || '').replace(/_/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase());
}

function populateIndicatorSelectors() {
  document.querySelectorAll('.metric-selector').forEach((select) => {
    const currentValue = select.value || select.dataset.defaultIndicator || 'rsi';
    select.innerHTML = metricIndicatorOptions.map((indicator) => `<option value="${indicator}"${indicator === currentValue ? ' selected' : ''}>${formatIndicatorLabel(indicator)}</option>`).join('');
    if (!select.value && metricIndicatorOptions.length) {
      select.value = select.dataset.defaultIndicator || metricIndicatorOptions[0];
    }
  });
}

function getMetricValue(indicatorName, market = {}, candles = []) {
  const normalized = String(indicatorName || '').trim();
  if (!normalized) return null;
  const latestCandle = Array.isArray(candles) && candles.length ? candles[0] : {};
  const candidates = [normalized, normalized.toLowerCase(), normalized.toUpperCase(), normalized.replace(/_/g, '')];
  for (const candidate of candidates) {
    if (latestCandle[candidate] != null) return latestCandle[candidate];
    if (market[candidate] != null) return market[candidate];
  }
  const lower = normalized.toLowerCase();
  for (const [key, value] of Object.entries(latestCandle)) {
    if (String(key).toLowerCase() === lower && value != null) return value;
  }
  if (market[lower] != null) return market[lower];
  return null;
}

function renderMetricCards(data = {}) {
  const market = data.market || {};
  const candles = Array.isArray(market.candles) ? market.candles : [];
  document.querySelectorAll('.metric-selector').forEach((select) => {
    const targetId = select.dataset.metricTarget;
    const target = targetId ? document.getElementById(targetId) : null;
    const caption = targetId ? document.getElementById(`${targetId}-caption`) : null;
    if (!target) return;
    const selectedIndicator = select.value || select.dataset.defaultIndicator || 'rsi';
    const value = getMetricValue(selectedIndicator, market, candles);
    target.textContent = value == null ? '—' : fmt(value, 10);
    if (caption) {
      caption.textContent = `Last candle · ${formatIndicatorLabel(selectedIndicator)}`;
    }
  });
}

function showDashboardLoading(symbol = selectedSymbol) {
  const bar = $('#dashboard-loading');
  const label = $('#dashboard-loading-label');
  const symbolText = $('#dashboard-loading-symbol');
  const fill = $('#dashboard-loading-fill');
  if (!bar || !label || !symbolText || !fill) return;
  clearTimeout(dashboardLoadingHideTimer);
  if (dashboardLoadingTimer) clearInterval(dashboardLoadingTimer);
  dashboardLoadingRequestToken += 1;
  dashboardLoadingActive = true;
  dashboardLoadingStartedAt = Date.now();
  bar.hidden = false;
  bar.style.display = 'grid';
  label.textContent = 'Fetching latest data…';
  symbolText.textContent = symbol || '—';
  let progress = 8;
  fill.style.width = `${progress}%`;
  dashboardLoadingTimer = window.setInterval(() => {
    progress = Math.min(progress + (progress < 90 ? 8 + Math.floor(Math.random() * 6) : 0), 94);
    fill.style.width = `${progress}%`;
  }, 140);
  return dashboardLoadingRequestToken;
}

function formatProcessTime(date = new Date()) {
  return date.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit', second: '2-digit'});
}

function setDashboardProcessStatus(message, state = '') {
  const status = $('#dashboard-process-status');
  if (!status) return;
  status.textContent = message;
  status.dataset.state = state;
}

function hideDashboardLoading(requestToken = dashboardLoadingRequestToken) {
  const bar = $('#dashboard-loading');
  const fill = $('#dashboard-loading-fill');
  if (!bar || !fill) return;
  if (requestToken !== dashboardLoadingRequestToken) return;
  clearInterval(dashboardLoadingTimer);
  dashboardLoadingTimer = null;
  const elapsed = Date.now() - dashboardLoadingStartedAt;
  const remaining = Math.max(0, dashboardLoadingMinDurationMs - elapsed);
  fill.style.width = '100%';
  clearTimeout(dashboardLoadingHideTimer);
  dashboardLoadingHideTimer = window.setTimeout(() => {
    if (requestToken !== dashboardLoadingRequestToken) return;
    dashboardLoadingActive = false;
    bar.hidden = true;
    bar.style.display = 'none';
    fill.style.width = '0%';
  }, remaining + 180);
}

function clearTestPage() {
  latestBacktestDetails = [];
  const summary = $('#summary');
  if (summary) summary.innerHTML = 'No saved test result found.';
  document.querySelectorAll('#test-metrics strong').forEach((element, index) => {
    if (index === 0) element.textContent = '0';
    if (index === 1) element.textContent = '0.0%';
    if (index === 2) element.textContent = '0.00%';
    if (index === 3) element.textContent = '0.00%';
  });
  renderConsensus({});
  renderPerformance({});
  refreshTestDetails();
}

function setLiveTest(metrics) {
  const winRate = (metrics.win_rate || 0) * (Number(metrics.total_return || 0) < 0 ? -1 : 1);
  const values = [metrics.trades || 0, `${(winRate * 100).toFixed(1)}%`, `${Number(metrics.total_return || 0).toFixed(2)}%`, `${Number(metrics.max_drawdown || 0).toFixed(2)}%`];
  document.querySelectorAll('#test-metrics strong').forEach((element, index) => { if (index < values.length) element.textContent = values[index]; });
}

const testMetricGrid = $('#test-metrics');
if (testMetricGrid && !$('#llm-agreement')) {
  testMetricGrid.insertAdjacentHTML('beforeend', '<article><span>LLM agreement</span><strong id="llm-agreement">0.0%</strong><small>Directional consensus ratio</small></article><article><span>LLM disagreements</span><strong id="llm-disagreements">0</strong><small id="llm-consensus-detail">0 agreed · 0 no-trade</small></article>');
}
const llmDisagreementMetric = $('#llm-disagreements')?.closest('article');
if (llmDisagreementMetric) llmDisagreementMetric.style.display = 'none';
if (testMetricGrid && !$('#llm-direction-accuracy')) {
  testMetricGrid.insertAdjacentHTML('beforeend', '<article><span>Direction accuracy</span><strong id="llm-direction-accuracy">0.0%</strong><small>Correct up/down calls</small></article><article><span>Confidence error</span><strong id="llm-confidence-error">0.0%</strong><small>Lower is better</small></article><article><span>Decision stability</span><strong id="llm-decision-stability">0.0%</strong><small>Parameter repeatability</small></article>');
}
function renderConsensus(consensus = {}) {
  const agreed = consensus.agreed_windows || 0;
  const disagreed = consensus.disagreed_windows || 0;
  const noTrade = consensus.no_trade_windows || 0;
  $('#llm-agreement').textContent = `${((consensus.agreement_ratio || 0) * 100).toFixed(1)}%`;
  $('#llm-disagreements').textContent = disagreed;
  $('#llm-consensus-detail').textContent = `${agreed} agreed · ${noTrade} no-trade`;
}

function renderPerformance(performance = {}) {
  $('#llm-direction-accuracy').textContent = `${((performance.direction_accuracy || 0) * 100).toFixed(1)}%`;
  $('#llm-confidence-error').textContent = `${((performance.confidence_calibration_error || 0) * 100).toFixed(1)}%`;
  $('#llm-decision-stability').textContent = `${((performance.decision_stability || 0) * 100).toFixed(1)}%`;
}

function renderNewsList(container, results = []) {
  if (!container) return;
  if (!results.length) {
    container.innerHTML = '<p class="subtitle">No retrieved news context for this prediction.</p>';
    return;
  }
  container.innerHTML = results.slice(0, 5).map((item) => {
    const title = item.title || 'Untitled news item';
    const snippet = item.snippet || 'No summary available.';
    const time = item.published_at ? formatAxisTime(item.published_at) : 'Unknown time';
    const url = item.url || '#';
    return `<article class="news-item"><a href="${url}" target="_blank" rel="noreferrer">${title}</a><small>${time}</small><p>${snippet}</p></article>`;
  }).join('');
}

function renderTelegramMessage(payload = {}) {
  const container = $('#telegram-message');
  const statusEl = $('#telegram-status');
  if (!container) return;
  const status = String(payload.status || 'idle').toLowerCase();
  const configured = Boolean(payload.configured !== false);
  const dryRun = Boolean(payload.dry_run);
  const statusText = status === 'sent' ? 'Sent' : status === 'dry_run' ? 'Dry run' : status === 'not_configured' ? 'Not configured' : status === 'idle' ? 'Idle' : 'Ready';
  if (statusEl) statusEl.textContent = statusText;
  if (status === 'not_configured') {
    container.innerHTML = '<p class="subtitle telegram-empty">The trade analysis preview is not available yet.</p>';
    return;
  }
  const message = String(payload.message || '').trim();
  if (!message) {
    container.innerHTML = '<p class="subtitle telegram-empty">No confident trade analysis has been generated yet.</p>';
    return;
  }
  const modeBadge = dryRun ? '🟡 Dry run preview' : configured ? '📈 Analysis ready' : '📈 Preview';
  container.innerHTML = `<div style="display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:8px;"><span style="display:inline-block;padding:3px 8px;border-radius:999px;background:rgba(80,227,173,.12);border:1px solid rgba(80,227,173,.32);color:#8cf0d7;font-size:10px;letter-spacing:.08em;text-transform:uppercase;">${modeBadge}</span></div>${message}`;
}

function refreshTestDetails() {
  const select = $('#test-trade-select');
  if (!select) return;
  const selectedValue = select.value;
  select.innerHTML = latestBacktestDetails.map((trade, index) => `<option value="${index}">#${index + 1} ${formatTradeTime(trade.timestamp)} ${trade.scenario || '-'} ${trade.return_pct == null ? '' : Number(trade.return_pct).toFixed(2) + '%'}</option>`).join('');
  if (selectedValue && Number(selectedValue) < latestBacktestDetails.length) select.value = selectedValue;
  drawSelectedTestTrade();
}

function formatTradeTime(value) {
  if (!value) return '-';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString();
}

function formatAxisTime(value) {
  if (!value) return '-';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString(undefined, {month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit'});
}

function refreshSymbolSelector(symbols = []) {
  const selector = $('#symbol-selector');
  if (!selector) return;
  const current = selectedSymbol || $('#symbol')?.textContent || '';
  const defaults = ['BTCUSDT','BNBUSDT','ZECUSDT','ETHUSDT','PEPEUSDT','XRPUSDT','DOGEUSDT','SOLUSDT','FUNUSDT','ASTRUSDT','ETHFIUSDT'];
  const values = [...new Set([...defaults, ...symbols.filter(Boolean)])];
  selector.innerHTML = '<option value="">Select symbol</option>' + values.map((symbol) => `<option value="${symbol}"${symbol === current ? ' selected' : ''}>${symbol}</option>`).join('');
  if (!selector.value && values.length) {
    selector.value = values[0];
  }
  selectedSymbol = selector.value || current || '';
}

function drawSelectedTestTrade() {
  const select = $('#test-trade-select');
  const canvas = $('#test-candle-chart');
  if (!select || !canvas) return;
  const trade = latestBacktestDetails[Number(select.value || 0)] || {};
  const candles = trade.chart_candles || [];
  renderNewsList($('#test-news-list'), trade.web_context?.results || []);
  $('#test-trade-outcome').value = trade.outcome ? `${trade.outcome} / ${Number(trade.return_pct || 0).toFixed(2)}%` : '-';
  $('#test-trade-start').value = `${formatTradeTime(trade.chart_marker?.entry_time || trade.timestamp)} @ ${Number(trade.entry_price || 0).toFixed(2)}`;
  $('#test-trade-end').value = `${formatTradeTime(trade.chart_marker?.outcome_time)} @ ${Number(trade.chart_marker?.outcome_price || 0).toFixed(2)}`;
  const note = $('#test-chart-note');
  const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  if (!candles.length) {
    note.textContent = 'Run a new backtest to save candle windows for this chart.';
    return;
  }
  note.textContent = 'Green candles closed higher; red candles closed lower. Marker shows entry and result.';
  const prices = candles.flatMap((candle) => [Number(candle.high), Number(candle.low), Number(trade.entry_price), Number(trade.target_price), Number(trade.stop_loss), Number(trade.chart_marker?.outcome_price)]);
  const min = Math.min(...prices.filter(Number.isFinite));
  const max = Math.max(...prices.filter(Number.isFinite));
  const pad = 34;
  const bottomPad = 58;
  const span = max - min || 1;
  const y = (price) => canvas.height - bottomPad - ((price - min) / span) * (canvas.height - pad - bottomPad);
  const step = (canvas.width - pad * 2) / Math.max(candles.length, 1);
  ctx.font = '11px DM Mono, monospace';
  candles.forEach((candle, index) => {
    const x = pad + index * step + step / 2;
    const open = Number(candle.open), close = Number(candle.close), high = Number(candle.high), low = Number(candle.low);
    const up = close >= open;
    ctx.strokeStyle = up ? '#50e3ad' : '#fa7687';
    ctx.fillStyle = up ? '#50e3ad' : '#fa7687';
    ctx.beginPath();
    ctx.moveTo(x, y(high));
    ctx.lineTo(x, y(low));
    ctx.stroke();
    const bodyTop = Math.min(y(open), y(close));
    const bodyHeight = Math.max(2, Math.abs(y(close) - y(open)));
    ctx.fillRect(x - Math.max(3, step * 0.28), bodyTop, Math.max(6, step * 0.56), bodyHeight);
  });
  const tickCount = Math.min(6, candles.length);
  const tickIndexes = Array.from({length: tickCount}, (_, index) => Math.round(index * (candles.length - 1) / Math.max(tickCount - 1, 1)));
  ctx.strokeStyle = '#262f3b';
  ctx.fillStyle = '#8993a3';
  tickIndexes.forEach((index) => {
    const x = pad + index * step + step / 2;
    ctx.beginPath();
    ctx.moveTo(x, canvas.height - bottomPad + 8);
    ctx.lineTo(x, canvas.height - bottomPad + 14);
    ctx.stroke();
    ctx.fillText(formatAxisTime(candles[index]?.time), Math.min(x - 48, canvas.width - 120), canvas.height - 24);
  });
  const drawPriceLevel = (price, label, color, offset = 0) => {
    if (!Number.isFinite(Number(price))) return;
    const levelY = y(Number(price));
    ctx.strokeStyle = color;
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.moveTo(pad, levelY);
    ctx.lineTo(canvas.width - pad, levelY);
    ctx.stroke();
    ctx.fillText(`${label} ${Number(price).toFixed(2)}`, pad + 6, Math.max(14, Math.min(canvas.height - bottomPad - 8, levelY - 6 + offset)));
  };
  drawPriceLevel(trade.target_price, 'Target', '#4da3ff', 0);
  drawPriceLevel(trade.stop_loss, 'Stop', '#4da3ff', 14);
  const entryIndex = candles.findIndex((candle) => String(candle.time) === String(trade.chart_marker?.entry_time));
  const markerX = pad + (entryIndex >= 0 ? entryIndex : Math.floor(candles.length / 2)) * step + step / 2;
  const outcomeIndex = candles.findIndex((candle) => String(candle.time) === String(trade.chart_marker?.outcome_time));
  const outcomeX = pad + (outcomeIndex >= 0 ? outcomeIndex : Math.min(candles.length - 1, (entryIndex >= 0 ? entryIndex : 0) + 1)) * step + step / 2;
  ctx.strokeStyle = '#4da3ff';
  ctx.fillStyle = '#4da3ff';
  ctx.beginPath();
  ctx.moveTo(markerX, pad);
  ctx.lineTo(markerX, canvas.height - bottomPad);
  ctx.stroke();
  ctx.fillText(`Start ${formatAxisTime(trade.chart_marker?.entry_time || trade.timestamp)} @ ${Number(trade.entry_price || 0).toFixed(2)}`, Math.min(markerX + 8, canvas.width - 220), pad - 10);
  const outcomePrice = trade.chart_marker?.outcome_price || trade.entry_price;
  ctx.strokeStyle = '#4da3ff';
  ctx.fillStyle = '#4da3ff';
  ctx.beginPath();
  ctx.moveTo(outcomeX, pad);
  ctx.lineTo(outcomeX, canvas.height - bottomPad);
  ctx.stroke();
  ctx.fillText(`End ${formatAxisTime(trade.chart_marker?.outcome_time)} @ ${Number(outcomePrice || 0).toFixed(2)}`, Math.min(outcomeX + 8, canvas.width - 210), pad + 6);
}

function renderMarketData(data = {}) {
  liveDashboardData = data || {};
  const market = data.market || {};
  const availableSymbols = Array.isArray(data.available_symbols) ? data.available_symbols : [];
  refreshSymbolSelector(availableSymbols);
  selectedSymbol = market.symbol || selectedSymbol || '';
  if ($('#symbol-selector')?.value !== selectedSymbol) {
    $('#symbol-selector').value = selectedSymbol || '';
  }
  $('#symbol').textContent = market.symbol || '—';
  $('#interval').textContent = market.interval || '—';
  $('#updated').textContent = market.updated_at || '—';
  $('#price').textContent = market.price == null ? '—' : `$${fmt(market.price, 10)}`;
  $('#rsi').textContent = market.rsi == null ? '—' : fmt(market.rsi, 10);
  $('#macd').textContent = market.macd == null ? '—' : fmt(market.macd, 10);
  renderMetricCards(data);
  renderNewsList($('#live-news-list'), data.news || []);
  if (typeof chart === 'function') {
    const chartEl = $('#chart');
    if (chartEl) chartEl.dataset.interval = market.interval || '';
    chart(market.candles || []);
  }
}

async function fetchDashboardData(symbol, options = {}) {
  const { refresh = false } = options;
  const normalizedSymbol = String(symbol || '').trim();
  if (!normalizedSymbol) return null;
  const refreshParam = refresh ? '&refresh=1' : '';
  const response = await fetch(`/api/dashboard?symbol=${encodeURIComponent(normalizedSymbol)}${refreshParam}`);
  const data = await response.json();
  if (data?.market?.symbol) {
    symbolCache.set(data.market.symbol, data);
  }
  return data;
}

async function prefetchSymbolSet(symbols = []) {
  const pool = [...new Set(symbols.filter(Boolean))];
  const subset = pool.slice(0, Math.min(pool.length, 6));
  await Promise.allSettled(subset.map((symbol) => fetchDashboardData(symbol)));
}

async function refreshDashboard(forceSymbol = null, options = {}) {
  const { showLoading = false, refresh = false } = options;
  if (!refresh && dashboardRefreshInFlight) return;
  const requestedSymbol = String(forceSymbol || selectedSymbol || 'BTCUSDT').trim();
  if (!requestedSymbol) return;
  dashboardRefreshInFlight = true;
  setDashboardProcessStatus(`Started ${formatProcessTime()} · ${requestedSymbol}`, 'running');
  const requestId = ++dashboardRequestIndex;
  const cachedData = symbolCache.get(requestedSymbol);
  if (cachedData) {
    selectedSymbol = requestedSymbol;
    renderMarketData(cachedData);
  } else {
    selectedSymbol = requestedSymbol;
    renderDashboardPlaceholder();
  }
  const loadingRequestToken = showLoading ? showDashboardLoading(requestedSymbol) : null;
  try {
    const data = await fetchDashboardData(requestedSymbol, {refresh});
    if (requestId !== dashboardRequestIndex) return;
    if (!data) return;
    const run = data.run || {};
    const runMode = String(run.mode || '').toLowerCase();
    const isBacktestRun = runMode === 'backtest';
    const normalizedStatus = normalizeRunStatus(run.status);
    const isActiveStatus = ['Running', 'Stopping'].includes(normalizedStatus);
    const activeBacktest = runMode === 'backtest' && isActiveStatus;
    const activeLiveRun = runMode === 'live' && isActiveStatus;
    if (activeBacktest) {
      testRunStarted = true;
    } else if (activeLiveRun) {
      testRunStarted = false;
    }
    const details = data.backtest_details || [];
    latestBacktestDetails = testRunStarted ? details : [];
    if (isBacktestRun) {
      try { refreshTestDetails(); } catch (e) {}
    } else if (!activeLiveRun) {
      clearTestPage();
      testRunStarted = false;
    }
    renderMarketData(data);
    $('#connection').textContent = run.status || 'Online';
    // If web search is unavailable on the server, mark the web_search_sites field with an error
    try {
      const webUnavailable = Boolean(data.web_search_unavailable);
      const webMsg = data.web_search_context || '';
      const webField = document.querySelector('input[name="web_search_sites"]');
      if (webField) {
        if (webUnavailable) {
          setFieldError(webField, 'Web search currently unavailable on server.');
          webField.title = webMsg || webField.title;
        } else {
          setFieldError(webField, '');
        }
      }
    } catch (e) {}
    syncStopButtonsState(run);
    syncRunConsoleState({ run, logEl: $('#log'), statusEl: $('#run-state'), defaultText: 'Waiting for a run…' });
    const telegram = data.telegram || {};
    renderTelegramMessage(telegram);
    const testPage = $('#test');
    testPage.classList.remove('run-running', 'run-completed', 'run-failed');
    if (runMode === 'backtest') {
      testPage.classList.add(`run-${String(run.status || '').toLowerCase()}`);
    }
    if (activeBacktest) {
      setLiveTest(data.run_metrics || {});
      renderConsensus(data.run_metrics?.llm_consensus);
      renderPerformance(data.run_metrics?.llm_performance);
    } else if (activeLiveRun) {
      renderConsensus({});
      renderPerformance({});
      $('#log').textContent = (run.output || ['Waiting for a run…']).join('\n');
      if (['Running', 'Stopping'].includes(run.status)) scrollLogToBottom($('#log'));
    } else if (isBacktestRun && typeof setTest === 'function') {
      setTest(data.backtest || {});
      const latest = Object.values(data.backtest?.symbols || {})[0];
      renderConsensus(latest?.llm_consensus);
      renderPerformance(latest?.llm_performance);
      refreshTestDetails();
    }
    const selector = $('#symbol-selector');
    const selectorSymbols = Array.from(selector?.options || []).map((option) => option.value).filter(Boolean);
    if (selectorSymbols.length && !initialPrefetchDone) {
      initialPrefetchDone = true;
      void prefetchSymbolSet(selectorSymbols);
    }
  } catch (error) {
    console.error('Dashboard refresh failed:', error);
    $('#connection').textContent = 'API unavailable';
    setDashboardProcessStatus(`Error ${formatProcessTime()} · ${requestedSymbol}`, 'error');
  } finally {
    dashboardRefreshInFlight = false;
    if (requestId === dashboardRequestIndex) {
      hideDashboardLoading(loadingRequestToken ?? dashboardLoadingRequestToken);
      if (!$('#dashboard-process-status')?.dataset.state || $('#dashboard-process-status').dataset.state === 'running') {
        setDashboardProcessStatus(`Complete ${formatProcessTime()} · ${requestedSymbol}`, 'complete');
      }
    }
  }
}
const DASHBOARD_REFRESH_MS = 500;
let dashboardRefreshTimer = null;

const livePage = $('#live');
if (livePage && !$('#live-news-card')) {
  const newsCard = document.createElement('section');
  newsCard.className = 'card news-card';
  newsCard.id = 'live-news-card';
  newsCard.innerHTML = '<div class="card-head"><div><p class="eyebrow">NEWS CONTEXT</p><h3>Retrieved news used for live prediction</h3></div><span class="badge">Live</span></div><div class="news-list" id="live-news-list"><p class="subtitle">No retrieved news context yet.</p></div>';
  const metrics = $('.metrics');
  if (metrics && metrics.nextSibling) {
    metrics.parentNode.insertBefore(newsCard, metrics.nextSibling);
  } else if (metrics) {
    metrics.parentNode.appendChild(newsCard);
  } else {
    livePage.appendChild(newsCard);
  }
}

const testGrid = document.querySelector('#test .grid');
if (testGrid && !document.querySelector('#test-debug')) {
  testGrid.insertAdjacentHTML('beforeend', `<section class="card log-card" id="test-debug"><div class="card-head"><div><p class="eyebrow">TEST DEBUG</p><h3>Backtest activity</h3></div><div><span id="test-debug-state" class="badge">Idle</span> <button id="test-stop" class="text-button" type="button" title="Stop the running backtest process" aria-label="Stop backtest">Stop backtest</button></div></div><div class="metrics" style="grid-template-columns:repeat(3,1fr);margin-bottom:14px"><article><span>Elapsed time</span><strong id="test-debug-elapsed">00:00</strong><small>Since test started</small></article><article><span>Progress</span><strong id="test-debug-progress">—</strong><small id="test-debug-progress-meta">Historical test steps</small></article><article><span>Mode</span><strong id="test-debug-mode">—</strong><small>Execution type</small></article></div><div style="margin:0 0 12px"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:#8fa0b8;"><span>Test progress</span><span id="test-debug-progress-text">0%</span></div><div style="height:10px;border-radius:999px;background:rgba(148,163,184,.15);overflow:hidden;border:1px solid rgba(148,163,184,.2)"><div id="test-debug-progress-bar" style="height:100%;width:0%;background:linear-gradient(90deg,#4da3ff,#5eead4);border-radius:999px;transition:width .25s ease"></div></div></div><pre id="test-debug-log" style="max-height:260px;overflow-y:auto;white-space:pre-wrap;">Run a backtest to see detailed progress and debug output here.</pre></section>`);
}
const testMetrics = $('#test-metrics');
const testDebug = $('#test-debug');
if (testMetrics && testDebug) testDebug.insertAdjacentElement('afterend', testMetrics);
if (testMetrics && !$('#test-details-card')) {
  testMetrics.insertAdjacentHTML('afterend', '<section class="card test-details-card" id="test-details-card"><div class="card-head"><div><p class="eyebrow">TRADE DETAILS</p><h3>Candle test view</h3></div><button id="test-details-toggle" class="primary" type="button">Show details</button></div><div id="test-details-body" hidden><div class="detail-controls"><label class="detail-select">Trade<select id="test-trade-select"></select></label><label>Outcome<input id="test-trade-outcome" readonly></label><label>Position start<input id="test-trade-start" readonly></label><label>Position end<input id="test-trade-end" readonly></label></div><canvas id="test-candle-chart" width="900" height="360"></canvas><p class="subtitle" id="test-chart-note">Run a new backtest to save candle windows for this chart.</p><div class="trade-news"><div class="card-head"><div><p class="eyebrow">NEWS CONTEXT</p><h3>Retrieved news used for this test trade</h3></div></div><div class="news-list" id="test-news-list"><p class="subtitle">No retrieved news context for this trade.</p></div></div></div></section>');
}

document.querySelectorAll('.metric-selector').forEach((select) => {
  select.addEventListener('change', () => {
    renderMetricCards(liveDashboardData || {});
  });
});

$('#refresh-dashboard')?.addEventListener('click', async () => {
  const symbol = selectedSymbol || $('#symbol-selector')?.value || '';
  if (!symbol) return;
  try {
    await refreshDashboard(symbol, {showLoading: true, refresh: true});
  } catch (error) {
    console.error('Manual refresh failed:', error);
  }
});

$('#symbol-selector')?.addEventListener('change', async (event) => {
  const symbol = event.target.value;
  if (!symbol) return;
  selectedSymbol = symbol;
  const cachedData = symbolCache.get(symbol);
  if (cachedData) {
    renderMarketData(cachedData);
  } else {
    renderDashboardPlaceholder();
  }
  try {
    await refreshDashboard(symbol, {showLoading: false, refresh: true});
  } catch (error) {
    console.error('Symbol refresh failed:', error);
  }
});

const normalizeRunStatus = (value = '') => {
  const status = String(value || '').trim().toLowerCase();
  if (status === 'stopped') return 'Stopped';
  if (status === 'stopping') return 'Stopping';
  if (status === 'running') return 'Running';
  if (status === 'completed') return 'Completed';
  if (status === 'failed') return 'Failed';
  if (status === 'idle') return 'Idle';
  return 'Idle';
};

function syncStopButtonsState(run = {}) {
  const buttons = [
    document.querySelector('#stop'),
    document.querySelector('#stop-console'),
    document.querySelector('#test-stop'),
  ].filter(Boolean);
  if (!buttons.length) return;
  const rawStatus = String(run.status || '').trim().toLowerCase();
  const isStopping = rawStatus === 'stopping';
  const isTerminalState = ['stopped', 'completed', 'failed', 'idle'].includes(rawStatus);
  buttons.forEach((button) => {
    const isTestButton = button.id === 'test-stop';
    const label = isTestButton ? 'Stop backtest' : 'Stop live analysis';
    button.disabled = isStopping || isTerminalState;
    button.textContent = isStopping ? 'Stopping…' : label;
  });
}

const testElapsed = (startedAt, finishedAt = null) => {
  if (!startedAt) return '00:00';
  const endTime = finishedAt ? new Date(finishedAt).getTime() : Date.now();
  const seconds = Math.max(0, Math.floor((endTime - new Date(startedAt).getTime()) / 1000));
  return `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
};
const scrollLogToBottom = (logEl) => {
  if (!logEl) return;
  logEl.scrollTop = logEl.scrollHeight;
};
function syncRunConsoleState({run = {}, logEl = null, statusEl = null, defaultText = 'Waiting for a run…'} = {}) {
  const status = normalizeRunStatus(run.status);
  const runStatus = status.toLowerCase();
  if (statusEl) statusEl.textContent = status;
  if (logEl) {
    const nextLog = (run.output || [defaultText]).join('\n');
    logEl.textContent = nextLog;
    if (['running', 'stopping'].includes(runStatus)) scrollLogToBottom(logEl);
  }
}
$('#test-details-toggle')?.addEventListener('click', () => {
  const body = $('#test-details-body');
  body.hidden = !body.hidden;
  $('#test-details-toggle').textContent = body.hidden ? 'Show details' : 'Hide details';
  if (!body.hidden) drawSelectedTestTrade();
});
$('#test-trade-select')?.addEventListener('change', drawSelectedTestTrade);
async function refreshTestDebug() {
  try {
    const response = await fetch('/api/dashboard');
    const data = await response.json();
    const run = data.run || {};
    const progress = run.progress || {};
    const logEl = $('#test-debug-log');
    const normalizedStatus = normalizeRunStatus(run.status);
    const runStatus = normalizedStatus.toLowerCase();
    syncStopButtonsState(run);
    syncRunConsoleState({ run: { ...run, status: normalizedStatus }, logEl, statusEl: $('#test-debug-state'), defaultText: 'Waiting for a test run…' });
    const finishedAt = ['completed', 'failed', 'stopped'].includes(runStatus) ? run.finished_at : null;
    $('#test-debug-elapsed').textContent = testElapsed(run.started_at, finishedAt);
    $('#test-debug-progress').textContent = progress.total ? `${progress.current} / ${progress.total}` : '—';
    $('#test-debug-progress').setAttribute('title', progress.total ? `Total progress across all symbols: ${progress.current} / ${progress.total}` : 'Total progress across all symbols');
    const progressMeta = $('#test-debug-progress-meta');
    const symbolProgress = run.symbol_progress || {};
    const symbolProgressText = Object.entries(symbolProgress)
      .filter(([, info]) => info && typeof info.current === 'number' && typeof info.total === 'number' && info.total > 0)
      .map(([symbol, info]) => `${symbol}: ${info.current}/${info.total}`)
      .join(' • ');
    if (progressMeta) {
      progressMeta.textContent = symbolProgressText || 'Historical test steps';
      progressMeta.setAttribute('title', symbolProgressText ? `Per-symbol historical test steps: ${symbolProgressText}` : 'Historical test steps');
    }
    const isFinished = ['completed', 'failed', 'stopped'].includes(runStatus);
    const pctValue = progress.total
      ? (isFinished ? 100 : Math.min(100, Math.max(0, Number(progress.percent || 0))))
      : 0;
    $('#test-debug-progress-text').textContent = progress.total ? `${pctValue.toFixed(0)}%` : '0%';
    $('#test-debug-progress-text').setAttribute('title', progress.total ? `Total progress across all symbols: ${pctValue.toFixed(0)}%` : 'Total progress across all symbols');
    const bar = $('#test-debug-progress-bar');
    if (bar) {
      bar.style.width = `${pctValue}%`;
    }
    $('#test-debug-mode').textContent = run.mode || '—';
  } catch { $('#test-debug-state').textContent = 'API unavailable'; }
}
refreshTestDebug(); setInterval(refreshTestDebug, 2000);
populateIndicatorSelectors();
renderMetricCards(liveDashboardData || {});

// Complete the compact tabs with every option supported by the two argparse parsers.
const addFields = (formId, markup) => {
  const form = document.querySelector(formId);
  if (!form) return;
  const actions = form.querySelector('.form-actions');
  const details = `<details class="advanced-parameters"><summary>Advanced parameters</summary><div class="advanced-fields">${markup}</div></details>`;
  if (actions) {
    actions.insertAdjacentHTML('beforebegin', details);
  } else {
    // fallback: insert before first button inside form
    form.querySelector('button')?.insertAdjacentHTML('beforebegin', details);
  }
};
addFields('#live-form', `<h3 class="advanced-title">Advanced live parameters</h3>
<div class="pair"><label>Voting models<input name="model_names" placeholder="Default from .env, or model-a, model-b"></label><label>Gain ratio threshold<input name="gain_ratio" type="number" step=".1" min="0" value="1"></label></div>
<div class="pair"><label>Quant candle limit<input name="quant_limit" type="number" min="1" value="400"></label><label>Quant test size<input name="quant_test_size" type="number" step=".01" min=".01" max=".99" value=".2"></label></div>
<div class="pair"><label>Quant input data<select name="quant_input_data"><option>both</option><option>ohlcv</option><option>indicators</option></select></label></div>
<div class="pair"><label>Quant target mode<select name="quant_target_mode"><option>raw_price</option><option>percentage_return</option><option>log_return</option><option>binary_direction</option><option>ternary_direction</option><option>future_volatility</option></select></label><label>Quant models<input name="quant_models" value="random_forest" placeholder="random_forest, extra_trees"></label></div>
<div class="pair"><label>Quant model<select name="quant_model"><option>random_forest</option><option>extra_trees</option><option>gradient_boosting</option><option>hist_gradient_boosting</option><option>k_neighbors</option><option>ridge</option><option>svr</option><option>sgd</option><option>passive_aggressive</option><option>logistic_regression</option></select></label><label>Direction threshold<input name="quant_direction_threshold" type="number" step=".0001" min="0" value=".001"></label></div>
<div class="pair"><label>Quant transform<select name="quant_transform"><option>none</option><option>bins</option><option>average</option><option>log</option></select></label></div>
<div class="pair"><label>Quant target<input name="quant_output_target" value="close"></label><label>Quant shift<input name="quant_shift" type="number" min="1" value="1"></label></div>
<div class="pair"><label>Prediction rows<input name="quant_predict_rows" type="number" min="1" value="1"></label><label>Quant indicators<input name="quant_indicators" placeholder="rsi, atr, EMA20"></label></div>
<label>Higher timeframes<input name="higher_timeframes" value="4h" placeholder="4h, 1d"></label><label>Indicators<input name="indicators" value="EMA20, EMA50, EMA100, EMA200, sma20, sma50, rsi, macd_line, macd_signal, macd_hist, stoch_k, stoch_d, atr, bb_upper, bb_middle, bb_lower, vwap"></label>
<div class="pair"><label>Web aspects<input name="web_search_aspects" value="policy, news, macro, exchange"></label><label>Web extra terms<input name="web_search_extra_terms" placeholder="regulation, ETF"></label></div><div class="pair"><label>Web topics<input name="web_search_topics" placeholder="policy, news"></label><label>Web max results<input name="web_search_max_results" type="number" min="1" value="5"></label></div>`);
// add web_search_sites input to live advanced params
document.querySelector('#live-form .advanced-fields')?.insertAdjacentHTML('beforeend', '<label>Web sites<input name="web_search_sites" placeholder="coindesk.com, cointelegraph.com"></label>');
addFields('#test-form', `<h3 class="advanced-title">All backtest parameters</h3>
<div class="pair"><label>Step<input name="step" type="number" min="1" value="10"></label><label>Inferences per trade<input name="iterations" type="number" min="1" max="10" value="2"></label></div>
<label>Voting models<input name="model_names" placeholder="Default from .env, or model-a, model-b"></label>
<label>LLM input candles (n)<input name="n" type="number" min="1" value="40"></label>
<div class="pair"><label>Max expected time<input name="max_expected_time" type="number" min="1" value="12"></label><label>Token limit<input name="token_limit" type="number" min="0" value="1500000"></label></div>
<div class="pair"><label>Input token price<input name="input_token_price" type="number" min="0" step=".000001" value="0"></label><label>Output token price<input name="output_token_price" type="number" min="0" step=".000001" value="0"></label></div>
<div class="pair"><label>Maximum cost (USD)<input name="max_cost" type="number" min="0" step=".01" value="1"></label><label>Output directory<input name="output_dir" value="backtest_results"></label></div>
<label>Higher timeframes<input name="higher_timeframes" value="4h"></label><label>Indicators<input name="indicators" value="EMA20, EMA50, EMA100, EMA200, sma20, sma50, rsi, macd_line, macd_signal, macd_hist, stoch_k, stoch_d, atr, bb_upper, bb_middle, bb_lower, vwap"></label>
<div class="pair"><label>Quant input data<select name="quant_input_data"><option>both</option><option>ohlcv</option><option>indicators</option></select></label><label>Quant target mode<select name="quant_target_mode"><option>raw_price</option><option>percentage_return</option><option>log_return</option><option>binary_direction</option><option>ternary_direction</option><option>future_volatility</option></select></label></div>
<div class="pair"><label>Quant models<input name="quant_models" value="random_forest" placeholder="random_forest, extra_trees"></label><label>Direction threshold<input name="quant_direction_threshold" type="number" step=".0001" min="0" value=".001"></label></div>
<div class="pair"><label>Quant transform<select name="quant_transform"><option>none</option><option>bins</option><option>average</option><option>log</option></select></label><label>Quant output target<input name="quant_output_target" value="close"></label></div>
<div class="pair"><label>Quant shift<input name="quant_shift" type="number" min="1" value="1"></label><label>Quant prediction rows<input name="quant_predict_rows" type="number" min="1" value="1"></label></div>
<label>Quant indicators<input name="quant_indicators" placeholder="rsi, atr, EMA20"></label>
<div class="pair"><label>Web aspects<input name="web_search_aspects" value="policy, news, macro, exchange"></label><label>Web extra terms<input name="web_search_extra_terms" placeholder="regulation, ETF"></label></div><div class="pair"><label>Web topics<input name="web_search_topics" placeholder="policy, news"></label><label>Web max results<input name="web_search_max_results" type="number" min="1" value="5"></label></div><label class="switch"><input name="quant_enabled" type="checkbox"><span></span>Enable quant model</label><label class="switch"><input name="web_search_enabled" type="checkbox"><span></span>Enable web context</label>`);
// add web_search_sites input to test advanced params
document.querySelector('#test-form .advanced-fields')?.insertAdjacentHTML('beforeend', '<label>Web sites<input name="web_search_sites" placeholder="coindesk.com, cointelegraph.com"></label>');

// Insert Manage LLM prompts button inside advanced parameters (one row alone)
['live','test'].forEach((id) => {
  const details = document.querySelector(`#${id}-form .advanced-parameters`);
  if (!details) return;
  // append a manage-row as the last child of the details so it appears on its own row
  details.insertAdjacentHTML('beforeend', `<div class="manage-row"><button type="button" id="${id}-manage-prompts" class="text-button">Manage LLM prompts</button></div>`);
  const btn = document.getElementById(`${id}-manage-prompts`);
  if (btn) btn.addEventListener('click', () => setActiveTab('prompts'));
});

const parameterHelp = {
  symbols: 'Trading pairs to analyze, separated by comma or space.',
  interval: 'Main candle timeframe used for market data.',
  limit: 'Number of recent candles to load for analysis or backtest.',
  confidence: 'Minimum LLM confidence required before accepting a live signal.',
  iterations: 'Number of repeated LLM calls for the same request.',
  quant: 'Include quant model output in the live LLM context.',
  web: 'Include web/news context in the live LLM context.',
  dry_run: 'Run without sending Telegram alerts.',
  model_names: 'One or more LLM models for voting. Leave empty to use MODEL_NAME from .env. Iterations cycle through these models.',
  gain_ratio: 'Minimum reward-to-risk style threshold for accepting a signal.',
  quant_limit: 'Number of candles used to train the quant model.',
  quant_test_size: 'Fraction of quant data reserved for model testing.',
  quant_input_data: 'Feature source used by the quant model.',
  quant_target_mode: 'Target type used by the quant model: price, return, direction, or volatility.',
  quant_models: 'Quant models to run in parallel, separated by comma or space.',
  quant_model: 'Regression model used for quant prediction.',
  quant_direction_threshold: 'Minimum forward return used for direction classification.',
  quant_transform: 'Optional transform applied before quant training.',
  quant_output_target: 'Column the quant model tries to predict.',
  quant_shift: 'How many rows ahead the quant target is shifted.',
  quant_predict_rows: 'How many latest rows to predict with the quant model.',
  quant_indicators: 'Indicator columns used as quant features.',
  higher_timeframes: 'Extra higher timeframes added to LLM context.',
  indicators: 'Technical indicator columns included in LLM context.',
  web_search_aspects: 'Broad web-search categories to include.',
  web_search_extra_terms: 'Extra search terms appended to web queries.',
  web_search_topics: 'Topic keywords used for web context.',
  web_search_max_results: 'Maximum number of web results included.',
  web_search_sites: 'Comma-separated preferred websites to prioritize in web search (e.g. coindesk.com).',
  step: 'Number of candles to move forward between backtest windows.',
  n: 'Number of recent candles sent to the LLM for each backtest step.',
  max_expected_time: 'Maximum future candles used to judge each trade outcome.',
  token_limit: 'Stop the backtest when total token usage passes this limit.',
  input_token_price: 'Cost per input token for backtest cost tracking.',
  output_token_price: 'Cost per output token for backtest cost tracking.',
  max_cost: 'Stop the backtest when estimated cost passes this amount.',
  output_dir: 'Folder where backtest result files are saved.',
  quant_enabled: 'Enable quant model context during backtesting.',
  web_search_enabled: 'Enable web/news context during backtesting.',
};

function applyParameterTooltips() {
  document.querySelectorAll('#live-form input, #live-form select, #test-form input, #test-form select').forEach((field) => {
    const help = parameterHelp[field.name];
    if (!help) return;
    field.title = help;
    field.closest('label')?.setAttribute('title', help);
  });
}
applyParameterTooltips();

// Remove duplicate `quant_input_set` controls if present in static pages.
document.querySelectorAll('select[name="quant_input_set"], select[data-option="quant_input_set"]').forEach((sel) => {
  const label = sel.closest('label');
  if (label) label.remove(); else sel.remove();
});

async function loadSettings() {
  const form = $('#settings-form');
  if (!form) return;
  try {
    const response = await fetch('/api/settings');
    const settings = await response.json();
    savedSettings = settings || {};
    form.elements.openrouter_api_key.value = settings.openrouter_api_key || '';
    form.elements.telegram_bot_token.value = settings.telegram_bot_token || '';
    form.elements.telegram_chat_id.value = settings.telegram_chat_id || '';
    $('#settings-state').textContent = 'Loaded';
    // Load runtime defaults and apply to forms
    try {
      const dresp = await fetch('/api/defaults');
      const defaults = await dresp.json();
      function applyDefaultsToForm(formId, defs) {
        const f = document.querySelector(formId);
        if (!f) return;
        const map = {
          symbols: 'symbols',
          interval: 'interval',
          limit: 'limit',
          quant_limit: 'quant_limit',
          quant_test_size: 'quant_test_size',
          higher_timeframes: 'higher_timeframes',
          indicators: 'indicators',
          model_names: 'model_names',
          iterations: 'iterations',
          quant_input_data: 'quant_input_data',
          quant_target_mode: 'quant_target_mode',
          quant_models: 'quant_models',
          quant_direction_threshold: 'quant_direction_threshold',
          quant_indicators: 'quant_indicators',
          quant_model: 'quant_model',
          quant_transform: 'quant_transform',
          quant_output_target: 'quant_output_target',
          quant_shift: 'quant_shift',
          quant_predict_rows: 'quant_predict_rows',
          web_search_aspects: 'web_search_aspects',
          web_search_extra_terms: 'web_search_extra_terms',
          web_search_sites: 'web_search_sites',
          web_search_topics: 'web_search_topics',
          web_search_max_results: 'web_search_max_results',
          confidence_threshold: 'confidence',
          gain_ratio_threshold: 'gain_ratio',
          n: 'n',
        };
        const requiredFields = new Set(['symbols']);
        const restrictedFields = new Set(['symbols','confidence','gain_ratio','quant_test_size','web_search_max_results','limit','n','quant_shift','quant_predict_rows','token_limit','max_cost']);
        // ensure every input/select in the form has a visible default hint
        const fields = Array.from(f.querySelectorAll('input[name], select[name]'));
        fields.forEach((el) => {
          const elName = el.name;
          // find key in defs: prefer map lookup, else use element name
          const key = Object.keys(map).find(k => map[k] === elName) || elName;
          const val = defs.hasOwnProperty(key) ? defs[key] : undefined;
          let displayValue;
          if (val === undefined || val === null) {
            displayValue = requiredFields.has(elName) ? 'required' : 'none';
          } else if (Array.isArray(val)) {
            displayValue = elName === 'symbols' ? val.join(' ') : val.join(', ');
          } else {
            displayValue = String(val);
          }
          // set dataset and placeholder for clarity when there is no default
          try {
            el.dataset.default = displayValue;
            // remove previous warning marker
            el.classList.remove('field-warning');
            const label = el.closest('label');
            if (displayValue === 'none') {
              if (!el.value) el.placeholder = 'none';
              // show a small asterisk for fields without defaults
              if (label && !label.querySelector('.required-star')) {
                const star = document.createElement('span');
                star.className = 'required-star';
                star.textContent = '*';
                // Ensure label text and star sit together in a title row
                let titleWrap = label.querySelector('.label-title');
                if (!titleWrap) {
                  titleWrap = document.createElement('span');
                  titleWrap.className = 'label-title';
                  // Move all nodes before the first form control into the title wrap
                  while (label.firstChild && !(label.firstChild.tagName && ['INPUT','SELECT','TEXTAREA','BUTTON'].includes(label.firstChild.tagName))) {
                    titleWrap.appendChild(label.firstChild);
                  }
                  label.insertBefore(titleWrap, label.firstChild || null);
                }
                titleWrap.appendChild(star);
                label.classList.add('has-required');
              }
              // only apply red error styling for restricted parameters
              if (restrictedFields.has(elName)) {
                el.classList.add('field-error');
                if (label) label.classList.add('field-error-label');
              } else {
                el.classList.remove('field-error');
                if (label) label.classList.remove('field-error-label');
              }
            } else {
              // remove any previous star or error when a default exists
              if (label) {
                const star = label.querySelector('.required-star');
                if (star) star.remove();
                label.classList.remove('field-error-label');
              }
              el.classList.remove('field-error');
            }
            // only populate the field value when there is a real default
            if (val !== undefined && val !== null) {
              if (el.tagName.toLowerCase() === 'select') {
                // try to select matching option, otherwise set value directly
                const opt = Array.from(el.options).find(o => o.value === displayValue || o.text === displayValue);
                if (opt) el.value = opt.value; else el.value = displayValue;
              } else {
                el.value = displayValue;
              }
            }
            // label and default hint are handled here to keep DOM access single
            const label2 = el.closest('label');
            if (label2) {
              const existing = label2.querySelector('.default-hint');
              if (!existing) {
                const hint = document.createElement('small');
                hint.className = 'default-hint';
                hint.textContent = `Default: ${displayValue}`;
                label2.appendChild(hint);
              } else {
                existing.textContent = `Default: ${displayValue}`;
              }
              if (displayValue === 'required') label2.classList.add('field-required'); else label2.classList.remove('field-required');
            }
          } catch (e) {
            // ignore DOM errors
          }
        });
      }
      applyDefaultsToForm('#live-form', defaults);
      applyDefaultsToForm('#test-form', defaults);
    } catch (err) {
      console.warn('Could not load defaults:', err);
    }
    // Remove visible text from settings submit button per user preference
    try {
      const settingsBtn = form.querySelector('button[type="submit"]');
      if (settingsBtn) {
        settingsBtn.textContent = '';
        settingsBtn.setAttribute('aria-label', 'Save settings');
        settingsBtn.title = 'Save settings';
      }
    } catch (e) {}
    document.querySelectorAll('#live-form, #test-form').forEach(validateParameters);
  } catch {
    $('#settings-state').textContent = 'Unavailable';
  }
}

function splitModels(value) {
  return String(value || '').split(/[\s,]+/).filter(Boolean);
}

function splitPromptFiles(value) {
  return String(value || '').split(/[\s,]+/).filter(Boolean);
}

function setFieldError(field, message) {
  if (!field) return false;
  field.classList.toggle('field-error', Boolean(message));
  field.closest('label')?.classList.toggle('field-error-label', Boolean(message));
  field.setCustomValidity(message || '');
  if (message) field.title = message;
  return Boolean(message);
}

function fieldNumber(form, name, fallback = 0) {
  const value = form.elements[name]?.value;
  const number = Number(value === undefined || value === '' ? fallback : value);
  return Number.isFinite(number) ? number : fallback;
}

function validateParameters(form) {
  let valid = true;
  const modelNames = form.elements.model_names;
  const iterations = form.elements.iterations;
  const models = splitModels(modelNames?.value);
  if (modelNames) {
    const hasDuplicateModels = new Set(models).size !== models.length;
    valid = !setFieldError(modelNames, hasDuplicateModels ? 'Voting models must not contain duplicate model names.' : '') && valid;
  }
  if (iterations) {
    const iterationCount = fieldNumber(form, 'iterations', 0);
    const message = iterationCount < 1
      ? 'Iterations must be at least 1.'
      : models.length && iterationCount < models.length
        ? 'Iterations must be at least the number of voting models.'
        : '';
    valid = !setFieldError(iterations, message) && valid;
  }
  if (!savedSettings.openrouter_api_key) {
    valid = false;
    $('#settings-state').textContent = 'API key required';
  }
  const webMaxResults = form.elements.web_search_max_results;
  if (webMaxResults) valid = !setFieldError(webMaxResults, fieldNumber(form, 'web_search_max_results', 1) < 1 ? 'Web max results must be at least 1.' : '') && valid;
  const quantShift = form.elements.quant_shift;
  if (quantShift) valid = !setFieldError(quantShift, fieldNumber(form, 'quant_shift', 1) < 1 ? 'Quant shift must be at least 1.' : '') && valid;
  const quantPredictRows = form.elements.quant_predict_rows;
  if (quantPredictRows) valid = !setFieldError(quantPredictRows, fieldNumber(form, 'quant_predict_rows', 1) < 1 ? 'Quant prediction rows must be at least 1.' : '') && valid;
  const quantDirectionThreshold = form.elements.quant_direction_threshold;
  if (quantDirectionThreshold) valid = !setFieldError(quantDirectionThreshold, fieldNumber(form, 'quant_direction_threshold', 0.001) < 0 ? 'Direction threshold must be at least 0.' : '') && valid;
  if (form.id === 'live-form') {
    const promptFiles = splitPromptFiles(form.elements.prompt_files?.value);
    const models = splitModels(form.elements.model_names?.value);
    if (promptFiles.length && promptFiles.length !== 1 && promptFiles.length !== models.length) {
      valid = !setFieldError(form.elements.prompt_files, 'Prompt files must be either one shared file or match the number of voting models.') && valid;
    }
    const confidence = form.elements.confidence;
    if (confidence) {
      const value = fieldNumber(form, 'confidence', 0.7);
      valid = !setFieldError(confidence, value < 0 || value > 1 ? 'Confidence must be between 0 and 1.' : '') && valid;
    }
    const gainRatio = form.elements.gain_ratio;
    if (gainRatio) valid = !setFieldError(gainRatio, fieldNumber(form, 'gain_ratio', 1) < 0 ? 'Gain ratio must be at least 0.' : '') && valid;
    const limit = form.elements.limit;
    if (limit) valid = !setFieldError(limit, fieldNumber(form, 'limit', 1) < 1 ? 'Candle limit must be at least 1.' : '') && valid;
    const quantLimit = form.elements.quant_limit;
    if (quantLimit) valid = !setFieldError(quantLimit, fieldNumber(form, 'quant_limit', 1) < 1 ? 'Quant candle limit must be at least 1.' : '') && valid;
    const quantTestSize = form.elements.quant_test_size;
    if (quantTestSize) {
      const value = fieldNumber(form, 'quant_test_size', 0.2);
      valid = !setFieldError(quantTestSize, value < 0.01 || value > 0.99 ? 'Quant test size must be between 0.01 and 0.99.' : '') && valid;
    }
  } else {
    const promptFiles = splitPromptFiles(form.elements.prompt_files?.value);
    const models = splitModels(form.elements.model_names?.value);
    if (promptFiles.length && promptFiles.length !== 1 && promptFiles.length !== models.length) {
      valid = !setFieldError(form.elements.prompt_files, 'Prompt files must be either one shared file or match the number of voting models.') && valid;
    }
    const lookback = fieldNumber(form, 'limit', 400);
    const step = fieldNumber(form, 'step', 10);
    const n = fieldNumber(form, 'n', 40);
    const maxExpectedTime = fieldNumber(form, 'max_expected_time', 12);
    valid = !setFieldError(form.elements.limit, lookback < 1 ? 'Lookback must be at least 1.' : lookback <= n + maxExpectedTime ? 'Lookback must be greater than LLM input candles plus max expected time.' : '') && valid;
    valid = !setFieldError(form.elements.step, step < 1 || step >= lookback ? 'Step must be at least 1 and smaller than lookback.' : '') && valid;
    valid = !setFieldError(form.elements.n, n < 1 ? 'LLM input candles must be at least 1.' : '') && valid;
    valid = !setFieldError(form.elements.max_expected_time, maxExpectedTime < 1 ? 'Max expected time must be at least 1.' : '') && valid;
    valid = !setFieldError(form.elements.token_limit, fieldNumber(form, 'token_limit', 1) < 1 ? 'Token limit must be at least 1.' : '') && valid;
    valid = !setFieldError(form.elements.input_token_price, fieldNumber(form, 'input_token_price', 0) < 0 ? 'Input token price must be at least 0.' : '') && valid;
    valid = !setFieldError(form.elements.output_token_price, fieldNumber(form, 'output_token_price', 0) < 0 ? 'Output token price must be at least 0.' : '') && valid;
    valid = !setFieldError(form.elements.max_cost, fieldNumber(form, 'max_cost', 0) < 0 ? 'Maximum cost must be at least 0.' : '') && valid;
    valid = !setFieldError(form.elements.output_dir, String(form.elements.output_dir?.value || '').trim() ? '' : 'Output directory must not be empty.') && valid;
  }
  return valid;
}

function setupModelVotingValidation() {
  document.querySelectorAll('#live-form, #test-form').forEach((form) => {
    ['model_names', 'iterations'].forEach((name) => {
      form.elements.prompt_files?.addEventListener('input', () => validateParameters(form));
      form.elements[name]?.addEventListener('input', () => validateParameters(form));
      form.elements[name]?.addEventListener('change', () => validateParameters(form));
    });
    ['confidence', 'gain_ratio', 'limit', 'quant_limit', 'quant_test_size', 'web_search_max_results', 'step', 'n', 'max_expected_time', 'token_limit', 'input_token_price', 'output_token_price', 'max_cost', 'output_dir', 'quant_shift', 'quant_predict_rows', 'quant_direction_threshold'].forEach((name) => {
      form.elements[name]?.addEventListener('input', () => validateParameters(form));
      form.elements[name]?.addEventListener('change', () => validateParameters(form));
    });
    validateParameters(form);
  });
}
setupModelVotingValidation();

$('#settings-form')?.addEventListener('submit', async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const data = Object.fromEntries(new FormData(form));
  try {
    const response = await fetch('/api/settings', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)});
    const result = await response.json();
    toast(result.message || 'Settings saved.');
    form.reset();
    loadSettings();
  } catch (error) {
    toast(`Unable to save settings: ${error.message}`);
  }
});
loadSettings();
loadSavedConfigsFromServer().then(() => renderSavedConfigs());
clearTestPage();

// ML Data Builder UI
async function loadMLData(limit = 100) {
  try {
    const resp = await fetch(`/api/ml-data?limit=${limit}`);
    const records = await resp.json();
    const container = $('#ml-list');
    if (!container) return;
    if (!records || !records.length) {
      container.innerHTML = '<p class="subtitle">No ML records yet.</p>';
      return;
    }
    container.innerHTML = records.map((r) => {
      const id = r.id || '';
      const symbol = r.symbol || '-';
      const ts = r.timestamp || r.created_at || '-';
      const mode = (r.mode || 'signal').toString().toLowerCase();
      const modeLabel = mode === 'backtest' ? 'Backtest' : mode === 'live' ? 'Live' : 'Signal';
      const pred = r.predicted_label || r.predicted_label === 0 ? r.predicted_label : '-';
      const gt = r.ground_truth || '-';
      return `<div style="padding:8px;border-bottom:1px solid #262f3b"><div style="display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap;"><div><b>${symbol}</b> <small style="color:#8993a3;margin-left:8px">${ts}</small></div><span style="display:inline-block;padding:3px 7px;border-radius:999px;background:rgba(94,234,212,.12);color:#8cf0d7;border:1px solid rgba(94,234,212,.45);font-size:10px;letter-spacing:.08em;text-transform:uppercase;">${modeLabel}</span></div><div style="margin-top:6px">Predicted: <b>${pred}</b> · Ground truth: <b>${gt}</b></div><div style="margin-top:6px"><button data-id="${id}" class="ml-edit">Edit</button> <button data-id="${id}" class="ml-download">View JSON</button></div></div>`;
    }).join('');
    container.querySelectorAll('.ml-edit').forEach(btn => btn.addEventListener('click', async (ev) => {
      const id = ev.currentTarget.dataset.id;
      const val = prompt('Enter ground truth label for this record (e.g. up/down/no_trade):');
      if (!val) return;
      try {
        const res = await fetch('/api/ml-data/update', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({id, updates:{ground_truth: val, corrected_by: 'dashboard', corrected_at: new Date().toISOString()}})});
        const data = await res.json();
        toast(data.message || 'Record updated.');
        loadMLData(limit);
      } catch (e) { toast('Update failed'); }
    }));
    container.querySelectorAll('.ml-download').forEach(btn => btn.addEventListener('click', (ev) => {
      const id = ev.currentTarget.dataset.id;
      const rec = records.find(r => r.id === id);
      if (!rec) return toast('Record not found');
      const w = window.open();
      w.document.body.innerText = JSON.stringify(rec, null, 2);
    }));
  } catch (e) { console.warn('Could not load ML data', e); }
}

document.addEventListener('click', (e) => {
  const tab = e.target.closest('.tab');
  if (tab && tab.dataset.tab === 'ml-data') {
    loadMLData(200);
  }
});

$('#live-manage-prompts')?.addEventListener('click', () => setActiveTab('prompts'));
$('#test-manage-prompts')?.addEventListener('click', () => setActiveTab('prompts'));

$('#prompt-file-form')?.addEventListener('submit', async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const data = Object.fromEntries(new FormData(form));
  const name = String(data.name || '').trim();
  if (!name) {
    return toast('Please enter a prompt file name before saving.');
  }
  try {
    const response = await fetch('/api/prompt-files', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({name, content: String(data.content || '')}),
    });
    const result = await response.json();
    if (!response.ok || !result.ok) {
      return toast(result.message || 'Unable to save prompt file.');
    }
    toast(`Saved ${result.name}.`);
    selectedPromptFile = result.name;
    loadPromptFiles();
  } catch (error) {
    toast(`Unable to save prompt file: ${error.message}`);
  }
});

$('#prompt-file-clear')?.addEventListener('click', () => {
  clearPromptEditor();
});

let promptFiles = [];
let selectedPromptFile = '';

async function loadPromptFiles() {
  try {
    const response = await fetch('/api/prompt-files');
    const data = await response.json();
    promptFiles = Array.isArray(data.files) ? data.files : [];
  } catch (error) {
    console.warn('Could not load prompt files', error);
    promptFiles = [];
  }
  renderPromptFileList();
  renderPromptModelSummary();
}

function renderPromptFileList() {
  const container = $('#prompt-files-list');
  if (!container) return;
  if (!promptFiles.length) {
    container.innerHTML = '<p class="subtitle">No prompt files available yet. Create one using the editor.</p>';
    return;
  }
  container.innerHTML = promptFiles.map((name) => `
      <div class="prompt-file-row">
        <button type="button" class="secondary prompt-file-select" data-name="${name}">${name}</button>
        <button type="button" class="text-button prompt-file-edit" data-name="${name}">Edit</button>
      </div>
    `).join('');
  container.querySelectorAll('.prompt-file-select, .prompt-file-edit').forEach((button) => {
    button.addEventListener('click', (event) => {
      const name = event.currentTarget.dataset.name;
      loadPromptFile(name);
    });
  });
}

async function loadPromptFile(name) {
  if (!name) return;
  try {
    const response = await fetch(`/api/prompt-file?name=${encodeURIComponent(name)}`);
    const result = await response.json();
    if (!response.ok || !result.ok) {
      return toast(result.message || 'Unable to load prompt file.');
    }
    $('#prompt-file-name').value = result.name || name;
    $('#prompt-file-content').value = result.content || '';
    selectedPromptFile = result.name || name;
    toast(`Loaded ${result.name}`);
  } catch (error) {
    toast('Unable to load prompt file.');
  }
}

function clearPromptEditor() {
  selectedPromptFile = '';
  $('#prompt-file-name').value = '';
  $('#prompt-file-content').value = '';
  toast('Prompt editor cleared.');
}

function renderPromptModelSummary() {
  const container = $('#prompt-model-summary');
  if (!container) return;
  const liveModels = splitModels($('#live-form [name="model_names"]')?.value || '');
  const testModels = splitModels($('#test-form [name="model_names"]')?.value || '');
  const modelNames = liveModels.length ? liveModels : testModels;
  const availableFileCount = promptFiles.length;
  const lines = [];
  lines.push(`<p class="subtitle">Model names currently entered in the forms: ${modelNames.length ? modelNames.join(', ') : 'None'}</p>`);
  if (!availableFileCount) {
    lines.push('<p class="subtitle">No saved prompt files yet.</p>');
  } else if (modelNames.length && availableFileCount === modelNames.length) {
    lines.push('<ul>');
    modelNames.forEach((model, index) => {
      lines.push(`<li><strong>${model}</strong> → ${promptFiles[index] || 'none'}</li>`);
    });
    lines.push('</ul>');
  } else if (modelNames.length && availableFileCount === 1) {
    lines.push(`<p class="subtitle">Single shared prompt file: <strong>${promptFiles[0]}</strong></p>`);
  } else {
    lines.push(`<p class="subtitle">Available prompt files: ${promptFiles.join(', ')}</p>`);
    if (modelNames.length) {
      lines.push('<p class="subtitle">Use equal count of prompt files to match each voting model.</p>');
    }
  }
  container.innerHTML = lines.join('');
}

function createConfigLabel(prefix = 'LIVE') {
  const stamp = new Date().toISOString().slice(0, 19).replace('T', ' ');
  return `${prefix}-${stamp}`;
}

function getDefaultPromptValue() {
  return 'default_prompt';
}

function getDefaultPromptLabel() {
  return 'Default prompt';
}

function buildConfigPayload(form, overrideName = '') {
  const data = Object.fromEntries(new FormData(form));
  const resolvedPrompt = data.prompt_files || selectedPromptFile || getDefaultPromptValue();
  const name = overrideName || $('#test-config-label')?.textContent?.replace(/^Config:\s*/i, '') || createConfigLabel('TEST');
  const payload = {
    name,
    symbols: data.symbols || '',
    interval: data.interval || '',
    limit: data.limit || '',
    model_names: data.model_names || '',
    prompt_files: resolvedPrompt,
    prompt: resolvedPrompt,
    iterations: data.iterations || '',
    confidence: data.confidence || '',
    gain_ratio: data.gain_ratio || '',
    higher_timeframes: data.higher_timeframes || '',
    indicators: data.indicators || '',
    quant_enabled: Boolean(form.elements.quant_enabled?.checked || form.elements.quant?.checked),
    web_search_enabled: Boolean(form.elements.web_search_enabled?.checked || form.elements.web?.checked),
    dry_run: Boolean(form.elements.dry_run?.checked),
    created_at: new Date().toISOString(),
  };
  return payload;
}

async function loadSavedConfigsFromServer() {
  try {
    const response = await fetch('/api/saved-configs');
    if (!response.ok) return getSavedConfigs();
    const data = await response.json();
    const configs = Array.isArray(data.configs) ? data.configs : [];
    if (configs.length) {
      localStorage.setItem('saved-configs', JSON.stringify(configs));
    }
    return configs;
  } catch {
    return getSavedConfigs();
  }
}

function getSavedConfigs() {
  try {
    const raw = localStorage.getItem('saved-configs');
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function saveSavedConfigs(configs) {
  const normalized = Array.isArray(configs) ? configs : [];
  localStorage.setItem('saved-configs', JSON.stringify(normalized));
  fetch('/api/saved-configs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ configs: normalized }),
  }).catch(() => {});
}

function normalizeConfigResult(result = {}) {
  const business = result.business_metrics || {};
  const llmConsensus = result.llm_consensus || {};
  const llmPerformance = result.llm_performance || {};
  const snapshot = {
    ...result,
    saved_at: result.saved_at || new Date().toISOString(),
    symbol: result.symbol || '—',
    trades: Number(result.trades || result.total_trades || 0),
    total_trades: Number(result.total_trades || result.trades || 0),
    win_rate: Number(result.win_rate || result.success_rate || business.win_rate || 0),
    success_rate: Number(result.success_rate || result.win_rate || business.win_rate || 0),
    total_return: Number(result.total_return || 0),
    avg_return_per_trade: Number(result.avg_return_per_trade || 0),
    buy_and_hold_return: Number(result.buy_and_hold_return || 0),
    outperformance: Number(result.outperformance || 0),
    max_drawdown: Number(result.max_drawdown || business.max_drawdown || 0),
    profit_factor: Number(result.profit_factor || business.profit_factor || 0),
    avg_win: Number(result.avg_win || business.avg_win || 0),
    avg_loss: Number(result.avg_loss || business.avg_loss || 0),
    average_trade_duration: Number(result.average_trade_duration || business.average_trade_duration || 0),
    total_tokens: Number(result.total_tokens || 0),
    input_tokens: Number(result.input_tokens || 0),
    output_tokens: Number(result.output_tokens || 0),
    total_cost: Number(result.total_cost || 0),
    agreement_ratio: Number(result.agreement_ratio || llmConsensus.agreement_ratio || 0),
    agreed_windows: Number(result.agreed_windows || llmConsensus.agreed_windows || 0),
    disagreed_windows: Number(result.disagreed_windows || llmConsensus.disagreed_windows || 0),
    no_trade_windows: Number(result.no_trade_windows || llmConsensus.no_trade_windows || 0),
    direction_accuracy: Number(result.direction_accuracy || llmPerformance.direction_accuracy || 0),
    confidence_calibration_error: Number(result.confidence_calibration_error || llmPerformance.confidence_calibration_error || 0),
    decision_stability: Number(result.decision_stability || llmPerformance.decision_stability || 0),
    actual_start: result.actual_start || result.start_time || null,
    actual_end: result.actual_end || result.end_time || null,
    requested_lookback: Number(result.requested_lookback || result.lookback || 0),
    candle_range: result.candle_range || (result.actual_start && result.actual_end ? `${result.actual_start} → ${result.actual_end}` : null),
    business_metrics: business,
    llm_consensus: llmConsensus,
    llm_performance: llmPerformance,
  };
  return snapshot;
}

function buildBacktestResultSnapshot(backtest) {
  const symbol = Object.keys(backtest?.symbols || {})[0] || '—';
  const data = backtest?.symbols?.[symbol] || {};
  const business = data.business_metrics || {};
  const llmConsensus = data.llm_consensus || {};
  const llmPerformance = data.llm_performance || {};
  return normalizeConfigResult({
    symbol,
    trades: data.total_trades || 0,
    total_trades: data.total_trades || 0,
    success_rate: data.success_rate || 0,
    win_rate: business.win_rate || 0,
    total_return: data.total_return || 0,
    avg_return_per_trade: data.avg_return_per_trade || 0,
    buy_and_hold_return: data.buy_and_hold_return || 0,
    outperformance: data.outperformance || 0,
    max_drawdown: business.max_drawdown || 0,
    profit_factor: business.profit_factor || 0,
    avg_win: business.avg_win || 0,
    avg_loss: business.avg_loss || 0,
    average_trade_duration: business.average_trade_duration || 0,
    total_tokens: data.total_tokens || 0,
    input_tokens: data.input_tokens || 0,
    output_tokens: data.output_tokens || 0,
    total_cost: data.total_cost || 0,
    agreement_ratio: llmConsensus.agreement_ratio || 0,
    agreed_windows: llmConsensus.agreed_windows || 0,
    disagreed_windows: llmConsensus.disagreed_windows || 0,
    no_trade_windows: llmConsensus.no_trade_windows || 0,
    direction_accuracy: llmPerformance.direction_accuracy || 0,
    confidence_calibration_error: llmPerformance.confidence_calibration_error || 0,
    decision_stability: llmPerformance.decision_stability || 0,
    actual_start: data.actual_start || null,
    actual_end: data.actual_end || null,
    requested_lookback: data.requested_lookback || 0,
    candle_range: data.actual_start && data.actual_end ? `${data.actual_start} → ${data.actual_end}` : null,
    business_metrics: business,
    llm_consensus: llmConsensus,
    llm_performance: llmPerformance,
    saved_at: new Date().toISOString(),
  });
}

function getConfigSignature(config = {}) {
  const normalized = {};
  Object.keys(config || {}).sort().forEach((key) => {
    if (['last_test_result', 'test_results', 'created_at'].includes(key)) return;
    const value = config[key];
    if (value === undefined || value === null || value === '') return;
    normalized[key] = Array.isArray(value) ? value.map((item) => String(item).trim()) : String(value).trim();
  });
  return JSON.stringify(normalized);
}

function attachTestResultToConfig(configName, result, configPayload = null) {
  if (!configName || !result) return;
  const configs = getSavedConfigs();
  const normalized = normalizeConfigResult(result);
  const baseConfig = configPayload && typeof configPayload === 'object' ? { ...configPayload } : { name: configName };
  baseConfig.name = configName || baseConfig.name || 'TEST';
  const existingIndex = configs.findIndex((config) => {
    if (!config || typeof config !== 'object') return false;
    return getConfigSignature(config) === getConfigSignature(baseConfig);
  });

  let nextConfigs;
  if (existingIndex >= 0) {
    nextConfigs = configs.map((config, index) => {
      if (index !== existingIndex) return config;
      const previousResults = Array.isArray(config.test_results) ? config.test_results : [];
      const duplicateResult = previousResults.some((entry) => {
        const current = normalizeConfigResult(entry);
        return current.symbol === normalized.symbol &&
          Number(current.trades || 0) === Number(normalized.trades || 0) &&
          Number(current.total_return || 0) === Number(normalized.total_return || 0) &&
          Number(current.max_drawdown || 0) === Number(normalized.max_drawdown || 0) &&
          Number(current.win_rate || 0) === Number(normalized.win_rate || 0);
      });
      const mergedResults = duplicateResult ? previousResults : [...previousResults, normalized];
      return {
        ...config,
        ...baseConfig,
        name: config.name || baseConfig.name,
        last_test_result: mergedResults[mergedResults.length - 1] || normalized,
        test_results: mergedResults,
      };
    });
  } else {
    nextConfigs = [
      ...configs,
      {
        ...baseConfig,
        name: baseConfig.name,
        last_test_result: normalized,
        test_results: [normalized],
      },
    ];
  }

  saveSavedConfigs(nextConfigs);
  renderSavedConfigs();
}

function renderSavedConfigs() {
  const container = $('#saved-configs-list');
  if (!container) return;
  const expandedIndices = new Set(
    Array.from(container.querySelectorAll('details[data-config-index][open]')).map((detail) => Number(detail.dataset.configIndex))
  );
  const configs = getSavedConfigs();
  if (!configs.length) {
    container.innerHTML = 'No configs saved yet.';
    return;
  }
  container.innerHTML = configs.map((config, index) => {
    const promptValue = config.prompt || config.prompt_files || getDefaultPromptValue();
    const promptLabel = promptValue === getDefaultPromptValue() ? getDefaultPromptLabel() : promptValue;
    const result = config.last_test_result || null;
    const history = Array.isArray(config.test_results) ? config.test_results : result ? [result] : [];
    const resultBlock = result ? `
      <div style="margin-top:8px;padding:8px 10px;border:1px solid rgba(101,203,255,.45);background:rgba(90,188,255,.09);border-radius:8px;color:#dff6ff;">
        <div style="font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:#8ae4ff;margin-bottom:4px;">Latest test result</div>
        <div style="font-size:12px;line-height:1.6;">
          <strong>${result.symbol || '—'}</strong> · ${result.trades || 0} trades · ${(Number(result.win_rate || result.success_rate || 0) * 100).toFixed(1)}% win · ${Number(result.total_return || 0).toFixed(2)}% return
        </div>
      </div>
    ` : '';
    const historyBlock = history.length ? history.map((entry, idx) => `
      <div style="margin-top:8px;padding:8px 10px;border:1px solid rgba(148,163,184,.18);border-radius:8px;background:rgba(15,23,42,.35);">
        <div style="font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:#9ed7ff;margin-bottom:6px;">Result ${idx + 1} · ${new Date(entry.saved_at || Date.now()).toLocaleString()}</div>
        <div style="font-size:12px;line-height:1.7;">
          <div><strong>${entry.symbol || '—'}</strong> · ${entry.trades || 0} trades · ${(Number(entry.win_rate || entry.success_rate || 0) * 100).toFixed(1)}% win</div>
          <div>Return: ${Number(entry.total_return || 0).toFixed(2)}% · Drawdown: ${Number(entry.max_drawdown || 0).toFixed(2)}% · Outperformance: ${Number(entry.outperformance || 0).toFixed(2)}%</div>
          <div>Buy & hold: ${Number(entry.buy_and_hold_return || 0).toFixed(2)}% · Profit factor: ${Number(entry.profit_factor || 0).toFixed(2)} · Max DD: ${Number(entry.max_drawdown || 0).toFixed(2)}%</div>
          <div>Agreement: ${(Number(entry.agreement_ratio || 0) * 100).toFixed(1)}% · Accuracy: ${(Number(entry.direction_accuracy || 0) * 100).toFixed(1)}% · Stability: ${(Number(entry.decision_stability || 0) * 100).toFixed(1)}%</div>
          <div>Range: ${entry.candle_range || entry.actual_start || '—'}${entry.actual_end ? ` → ${entry.actual_end}` : ''} · Tokens: ${Number(entry.total_tokens || 0).toFixed(0)}</div>
        </div>
      </div>
    `).join('') : '<div style="color:#8896a8;margin-top:8px;">No test results saved yet.</div>';
    const detailEntries = Object.entries(config)
      .filter(([key]) => !['last_test_result', 'test_results'].includes(key))
      .filter(([, value]) => value !== undefined && value !== null && value !== '')
      .map(([key, value]) => `<div style="display:flex;justify-content:space-between;gap:10px;padding:5px 0;border-bottom:1px solid rgba(148,163,184,.18);"><span style="color:#8896a8;">${key}</span><span style="text-align:right;word-break:break-word;">${String(value)}</span></div>`)
      .join('');
    return `
    <div style="padding:10px 0;border-bottom:1px solid #262f3b;${result ? 'background:rgba(72,187,120,.06);border-left:2px solid #5eead4;padding-left:10px;' : ''}">
      <div style="display:flex;justify-content:space-between;gap:12px;align-items:flex-start;">
        <div style="flex:1;">
          <div style="font-weight:600;display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
            <span>${config.name || `Config ${index + 1}`}</span>
            ${result ? '<span style="display:inline-block;padding:3px 7px;border-radius:999px;background:rgba(94,234,212,.12);color:#8cf0d7;border:1px solid rgba(94,234,212,.45);font-size:10px;letter-spacing:.08em;text-transform:uppercase;">Test</span>' : ''}
          </div>
          <div style="font-size:12px;opacity:.72;">${config.symbols || '—'} · ${promptLabel} · ${config.model_names || 'No model'} · ${config.interval || '—'}</div>
        </div>
        <div>
          <button type="button" data-config-index="${index}" data-config-action="load" class="primary" style="margin-right:6px;">Load</button>
          <button type="button" data-config-index="${index}" data-config-action="delete" class="text-button">Delete</button>
        </div>
      </div>
      ${resultBlock}
      <details data-config-index="${index}" style="margin-top:8px;">
        <summary style="cursor:pointer;color:#dfe7f6;">Explore config</summary>
        <div style="margin-top:8px;padding:8px 10px;border:1px solid rgba(148,163,184,.18);border-radius:8px;background:rgba(15,23,42,.25);">
          ${detailEntries || '<div style="color:#8896a8;">No additional metadata saved.</div>'}
          ${historyBlock}
        </div>
      </details>
    </div>
  `;
  }).join('');

  container.querySelectorAll('details[data-config-index]').forEach((detail) => {
    const index = Number(detail.dataset.configIndex);
    detail.open = expandedIndices.has(index);
  });

  container.querySelectorAll('[data-config-action]').forEach((button) => {
    button.addEventListener('click', () => {
      const index = Number(button.dataset.configIndex || 0);
      const configs = getSavedConfigs();
      const config = configs[index];
      if (!config) return;
      if (button.dataset.configAction === 'load') {
        const testForm = $('#test-form');
        if (!testForm) return;
        Object.entries(config).forEach(([key, value]) => {
          if (['last_test_result', 'test_results'].includes(key)) return;
          if (!testForm.elements[key]) return;
          const field = testForm.elements[key];
          if (field.tagName === 'SELECT') {
            field.value = String(value || '');
          } else {
            field.value = String(value || '');
          }
        });
        $('#test-config-label').textContent = `Config: ${config.name || 'SAVED'}`;
        setActiveTab('test');
      } else {
        const next = configs.filter((_, i) => i !== index);
        saveSavedConfigs(next);
        renderSavedConfigs();
      }
    });
  });
}

function syncLiveConfigToTest() {
  const liveForm = $('#live-form');
  const testForm = $('#test-form');
  const configLabel = $('#test-config-label');
  if (!liveForm || !testForm) return;

  const liveData = Object.fromEntries(new FormData(liveForm));
  if (liveData.symbols) testForm.elements.symbols.value = String(liveData.symbols).trim();
  if (liveData.interval) testForm.elements.interval.value = String(liveData.interval).trim();
  if (liveData.limit) testForm.elements.limit.value = String(liveData.limit).trim();

  const generatedLabel = createConfigLabel('LIVE');
  testForm.dataset.configName = generatedLabel;
  if (configLabel) configLabel.textContent = `Config: ${generatedLabel}`;
}

function setActiveTab(tabName) {
  document.querySelectorAll('.tab,.page').forEach((el) => el.classList.remove('active'));
  const button = document.querySelector(`.tab[data-tab="${tabName}"]`);
  const page = $(`#${tabName}`);
  if (button) button.classList.add('active');
  if (page) page.classList.add('active');
  if (tabName === 'prompts') loadPromptFiles();
}

$('#ml-export')?.addEventListener('click', async () => {
  try {
    const r = await fetch('/api/ml-data/export');
    const j = await r.json();
    const blob = new Blob([JSON.stringify(j.records || [], null, 2)], {type: 'application/json'});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = 'ml_dataset.json'; a.click(); URL.revokeObjectURL(url);
  } catch (e) { toast('Export failed'); }
});

document.querySelectorAll('#live-form, #test-form').forEach((form) => form.addEventListener('submit', async (event) => {
  event.preventDefault(); event.stopImmediatePropagation();
  if (!validateParameters(form)) {
    toast('Please fix highlighted parameters before running.');
    return;
  }
  const data = Object.fromEntries(new FormData(form));
  data.symbols = (data.symbols || '').split(/[\s,]+/).filter(Boolean);
  data.mode = form.id === 'test-form' ? 'backtest' : 'live';
  data.quant_enabled = form.elements.quant_enabled?.checked || form.elements.quant?.checked || false;
  data.web_search_enabled = form.elements.web_search_enabled?.checked || form.elements.web?.checked || false;
  data.dry_run = form.elements.dry_run?.checked || false;
  if (data.mode === 'backtest') data.lookback = data.limit;
  const button = form.querySelector('button[type="submit"]');
  const originalButtonText = button.textContent;
  button.disabled = true; button.textContent = 'Starting…';
  if (data.mode === 'backtest') {
    const logEl = $('#test-debug-log');
    if (logEl) {
      logEl.textContent = 'Sending backtest request to the local engine…';
      scrollLogToBottom(logEl);
    }
  }
  try {
    const response = await fetch('/api/run', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)});
    const result = await response.json();
    toast(result.message || 'Request completed.');
    if (data.mode === 'backtest') {
      const logEl = $('#test-debug-log');
      if (logEl) {
        logEl.textContent = result.message || 'Backtest request completed.';
        scrollLogToBottom(logEl);
      }
      refreshTestDebug();
    }
  } catch (error) {
    const message = `Unable to start run: ${error.message}`;
    toast(message); if (data.mode === 'backtest') {
      const logEl = $('#test-debug-log');
      if (logEl) {
        logEl.textContent = message;
        scrollLogToBottom(logEl);
      }
    }
  } finally { button.disabled = false; button.textContent = originalButtonText; }
}, true));
const fmt = (value, digits = 2) => value == null ? '—' : Number(value).toLocaleString(undefined, {maximumFractionDigits: digits});
function toast(message, duration = 3000){const el=$('#toast');if(!el)return;el.textContent=message;el.style.transform='translateY(0)';clearTimeout(el._toastTimer);el._toastTimer=setTimeout(()=>el.style.transform='translateY(100px)',duration)}
function chart(candles){
  const el = $('#chart');
  if (!el) return;
  if (!candles?.length) {
    el.innerHTML = '<span class="subtitle">No cached market data yet.</span>';
    return;
  }

  const intervalLabel = el.dataset.interval || '';
  const values = candles.map((x) => Number(x.close));
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const barHtml = values.map((v) => `<i class="bar" style="height:${14 + ((v - min) / span) * 82}%" title="$${fmt(v, 6)}"></i>`).join('');

  const ticks = Math.min(5, candles.length);
  const tickIndexes = Array.from({length: ticks}, (_, index) => Math.round(index * (candles.length - 1) / Math.max(ticks - 1, 1)));
  const xLabels = tickIndexes.map((index) => {
    const candle = candles[index];
    const time = candle?.time || candle?.timestamp || '';
    const label = formatTradeTime(time);
    return `<span>${label}</span>`;
  }).join('');

  const priceLabels = [max, max - span * 0.66, max - span * 0.33, min].map((price) => `<span>${fmt(price, 6)}</span>`).join('');

  el.innerHTML = `
    <div class="chart-meta">
      <span class="chart-frame">Frame: ${intervalLabel || 'unknown'}</span>
      <div class="chart-price-labels">${priceLabels}</div>
    </div>
    <div class="chart-body">${barHtml}</div>
    <div class="chart-xaxis">${xLabels}</div>
  `;
}

function setTest(backtest){const symbol=Object.keys(backtest.symbols||{})[0],data=backtest.symbols?.[symbol];if(!data)return;const business=data.business_metrics||{};const signedWinRate=(data.success_rate||0)*(Number(data.total_return||0)<0?-1:1);const vals=[data.total_trades,`${(signedWinRate*100).toFixed(1)}%`,`${fmt(data.total_return)}%`,`${fmt(business.max_drawdown)}%`];document.querySelectorAll('#test-metrics strong').forEach((el,i)=>{if(i<vals.length)el.textContent=vals[i]});$('#summary').innerHTML=`<div class="summary-row" title="Saved backtest market."><p><span>Symbol:</span> <b>${symbol}</b></p></div><div class="summary-row" title="Holding from start to end."><p><span>Buy & hold:</span> <b>${fmt(data.buy_and_hold_return)}%</b></p></div><div class="summary-row" title="Strategy return versus holding."><p><span>Outperformance:</span> <b>${fmt(data.outperformance)}%</b></p></div><div class="summary-row" title="Token usage:"><p><span>Token usage:</span> <b>${fmt(data.total_tokens,0)}</b></p></div>`;const testForm = $('#test-form');const configName = ($('#test-config-label')?.textContent || '').replace(/^Config:\s*/i, '').trim() || 'TEST';const configPayload = testForm ? buildConfigPayload(testForm, configName) : { name: configName };attachTestResultToConfig(configName, buildBacktestResultSnapshot(backtest), configPayload);toast('Test complete. Config saved to Configs tab.', 2200)}
async function refresh(){try{const r=await fetch('/api/dashboard');const d=await r.json(),m=d.market,s=d.status;$('#connection').textContent=s.running?'Running':'Online';$('#symbol').textContent=m.symbol;$('#interval').textContent=m.interval;$('#updated').textContent=m.updated_at||'—';$('#price').textContent=m.price?`$${fmt(m.price, 10)}`:'—';$('#rsi').textContent=fmt(m.rsi, 10);$('#macd').textContent=fmt(m.macd, 10);$('#forecast').textContent=d.quant?.predictions?.[0]?`$${fmt(d.quant.predictions[0])}`:'—';$('#news-count').textContent=d.news?.length||0;$('#log').textContent=s.log?.join('\n')||'Waiting for a run…';scrollLogToBottom($('#log'));$('#run-state').textContent=s.running?'Running':'Idle';chart(m.candles);setTest(d.backtest)}catch(e){$('#connection').textContent='Offline'}}
document.querySelectorAll('.tab').forEach(button=>button.addEventListener('click',()=>{document.querySelectorAll('.tab,.page').forEach(el=>el.classList.remove('active'));button.classList.add('active');$('#'+button.dataset.tab).classList.add('active');if(button.dataset.tab==='test' && !testRunStarted) clearTestPage();}));
$('#save-and-test-configs')?.addEventListener('click', () => {
  syncLiveConfigToTest();
  setActiveTab('test');
});

$('#export-test-config')?.addEventListener('click', () => {
  const form = $('#test-form');
  if (!form) return;
  const configName = ($('#test-config-label')?.textContent || '').replace(/^Config:\s*/i, '').trim() || createConfigLabel('TEST');
  const payload = buildConfigPayload(form, configName);
  const config = getSavedConfigs().find((item) => getConfigSignature(item) === getConfigSignature(payload));
  if (config) {
    setActiveTab('configs');
    toast('Config already exists; new test result was appended to the saved entry.');
    return;
  }
  const configs = getSavedConfigs();
  configs.push(payload);
  saveSavedConfigs(configs);
  renderSavedConfigs();
  setActiveTab('configs');
  toast('Config saved to Saved Configs.');
});

$('#import-test-config')?.addEventListener('click', () => {
  const configs = getSavedConfigs();
  if (!configs.length) {
    toast('No saved configs available.');
    setActiveTab('configs');
    return;
  }
  renderSavedConfigs();
  setActiveTab('configs');
  toast('Choose a saved config from the list to import.');
});

async function submit(form,path){const data=Object.fromEntries(new FormData(form));['quant','web','dry_run'].forEach(k=>data[k]=form.elements[k]?.checked);const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});const d=await r.json();toast(d.message);refresh()}
async function stopCurrentRun(label = 'run') {
  const buttons = [
    document.querySelector('#stop'),
    document.querySelector('#stop-console'),
    document.querySelector('#test-stop'),
  ].filter(Boolean);

  const setStoppingState = () => {
    buttons.forEach((button) => {
      button.disabled = true;
      button.textContent = 'Stopping…';
    });
  };

  const resetButtonState = () => {
    const statusText = label === 'backtest' ? 'Stop backtest' : 'Stop live analysis';
    buttons.forEach((button) => {
      button.disabled = false;
      button.textContent = statusText;
    });
  };

  setStoppingState();

  try {
    const r = await fetch('/api/stop', {method: 'POST'});
    const payload = await r.json();
    toast(payload.message || `Stop signal sent for ${label}.`);
    if (!payload.ok) {
      resetButtonState();
      return;
    }
    if (label === 'backtest') {
      refreshTestDebug();
    } else {
      refreshDashboard(null, {showLoading: false});
    }
  } catch (error) {
    toast(`Unable to stop ${label}: ${error.message}`);
    resetButtonState();
  }
}
$('#stop')?.addEventListener('click', () => stopCurrentRun('live'));
$('#stop-console')?.addEventListener('click', () => stopCurrentRun('live'));
$('#test-stop')?.addEventListener('click', () => stopCurrentRun('backtest'));
void refreshDashboard(null, {showLoading: false, refresh: true}).finally(() => {
  dashboardRefreshTimer = setInterval(() => refreshDashboard(null, {showLoading: false, refresh: false}), DASHBOARD_REFRESH_MS);
});
