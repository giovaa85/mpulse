/**
 * MarketPulse Terminal — Single-Page Application
 * Vanilla JS ES Module, no build step required.
 */

// ── State ─────────────────────────────────────────────────────────────────────
const state = {
  user: null,
  theme: 'dark',
  currentPage: null,
  wsReconnectTimer: null,
  chartInstances: {},
};

// ── API Client ────────────────────────────────────────────────────────────────
const api = {
  async request(path, opts = {}) {
    const res = await fetch(path, {
      credentials: 'include',
      headers: { 'Content-Type': 'application/json', ...(opts.headers || {}) },
      ...opts,
    });
    if (res.status === 401) {
      // Clear local state and show login WITHOUT calling the logout API endpoint
      // (calling it would trigger another 401 → infinite loop).
      state.user = null;
      disconnectWS();
      showLogin();
      throw new Error('Unauthorized');
    }
    if (!res.ok) {
      let detail = `HTTP ${res.status}`;
      try { const j = await res.json(); detail = j.detail || detail; } catch (_) {}
      throw new Error(detail);
    }
    if (res.status === 204) return null;
    return res.json();
  },
  get:    (p)    => api.request(p),
  post:   (p, d) => api.request(p, { method: 'POST',   body: JSON.stringify(d) }),
  put:    (p, d) => api.request(p, { method: 'PUT',    body: JSON.stringify(d) }),
  delete: (p)    => api.request(p, { method: 'DELETE' }),
};

// ── Toast ─────────────────────────────────────────────────────────────────────
function toast(msg, type = 'info', duration = 4000) {
  const icons = { success: '✅', error: '❌', warn: '⚠️', info: 'ℹ️' };
  const el = document.createElement('div');
  el.className = `toast toast-${type}`;
  el.innerHTML = `<span class="toast-icon">${icons[type]}</span><span>${msg}</span>`;
  document.getElementById('toast-container').appendChild(el);
  setTimeout(() => {
    el.classList.add('toast-exit');
    setTimeout(() => el.remove(), 300);
  }, duration);
}

// ── Format helpers ────────────────────────────────────────────────────────────
const fmt = {
  price: (v, currency) => {
    if (v == null) return '—';
    const sym = currency === 'EUR' ? '€' : currency === 'GBP' ? '£' : '$';
    return sym + Number(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 4 });
  },
  pct: (v) => v == null ? '—' : (v >= 0 ? '+' : '') + Number(v).toFixed(2) + '%',
  pctClass: (v) => v == null ? '' : v >= 0 ? 'pos' : 'neg',
  num: (v, d = 2) => v == null ? '—' : Number(v).toLocaleString('en-US', { maximumFractionDigits: d }),
  mcap: (v) => {
    if (v == null) return '—';
    if (v >= 1e12) return '$' + (v / 1e12).toFixed(2) + 'T';
    if (v >= 1e9)  return '$' + (v / 1e9).toFixed(2) + 'B';
    if (v >= 1e6)  return '$' + (v / 1e6).toFixed(2) + 'M';
    return '$' + v.toLocaleString();
  },
  date: (s) => s ? new Date(s).toLocaleString() : '—',
  dateShort: (s) => s ? new Date(s).toLocaleDateString() : '—',
};

// ── Skeleton helpers ──────────────────────────────────────────────────────────
function skelLines(n = 3, widths = []) {
  return Array.from({ length: n }, (_, i) => {
    const w = widths[i] || (60 + (i * 13) % 40);
    return `<div class="skeleton skel-line" style="width:${w}%"></div>`;
  }).join('');
}
function skelCards(n, h = 90) {
  return Array.from({ length: n }, () =>
    `<div class="skeleton skel-card" style="height:${h}px"></div>`
  ).join('');
}
function skelRows(n = 5) {
  return Array.from({ length: n }, () => `<div class="skeleton skel-row"></div>`).join('');
}

// ── Chart utilities ───────────────────────────────────────────────────────────
function destroyChart(key) {
  if (state.chartInstances[key]) {
    state.chartInstances[key].destroy();
    delete state.chartInstances[key];
  }
}
function destroyAllCharts() {
  Object.keys(state.chartInstances).forEach(destroyChart);
}

function lineChart(canvasId, labels, datasets, opts = {}) {
  destroyChart(canvasId);
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const isDark = document.documentElement.dataset.theme !== 'light';
  const gridColor = isDark ? '#30363d' : '#e8eaed';
  const textColor = isDark ? '#8b949e' : '#57606a';

  state.chartInstances[canvasId] = new Chart(canvas, {
    type: 'line',
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { labels: { color: textColor, font: { size: 12 } } },
        tooltip: { backgroundColor: isDark ? '#21262d' : '#fff', titleColor: textColor,
                   bodyColor: textColor, borderColor: isDark ? '#30363d' : '#d0d7de', borderWidth: 1 },
      },
      scales: {
        x: { ticks: { color: textColor, maxTicksLimit: 8, maxRotation: 0 },
             grid: { color: gridColor } },
        y: { ticks: { color: textColor }, grid: { color: gridColor }, ...opts.yAxis },
      },
      elements: { point: { radius: 0, hoverRadius: 4 } },
      ...opts.extra,
    },
  });
}

function barChart(canvasId, labels, values, colors) {
  destroyChart(canvasId);
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const isDark = document.documentElement.dataset.theme !== 'light';
  const gridColor = isDark ? '#30363d' : '#e8eaed';
  const textColor = isDark ? '#8b949e' : '#57606a';

  state.chartInstances[canvasId] = new Chart(canvas, {
    type: 'bar',
    data: {
      labels,
      datasets: [{ data: values, backgroundColor: colors, borderRadius: 4 }],
    },
    options: {
      indexAxis: 'y',
      responsive: true,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { color: textColor, callback: v => v + '%' }, grid: { color: gridColor } },
        y: { ticks: { color: textColor }, grid: { display: false } },
      },
    },
  });
}

// ── Auth ──────────────────────────────────────────────────────────────────────
async function checkAuth() {
  try {
    state.user = await api.get('/api/auth/me');
    return true;
  } catch (_) {
    return false;
  }
}

async function logout() {
  if (state.user) {
    // Only call the API if there's an active session to invalidate.
    try { await fetch('/api/auth/logout', { method: 'POST', credentials: 'include' }); } catch (_) {}
  }
  state.user = null;
  disconnectWS();
  showLogin();
}

// ── WebSocket ─────────────────────────────────────────────────────────────────
let ws = null;
const wsHandlers = {};

function connectWS() {
  if (ws) return;
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  ws = new WebSocket(`${proto}//${location.host}/ws/stream`);

  ws.onopen = () => {
    document.getElementById('ws-dot')?.classList.add('connected');
    clearTimeout(state.wsReconnectTimer);
  };

  ws.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data);
      if (wsHandlers[msg.type]) wsHandlers[msg.type](msg.payload);
      if (msg.type === 'market_update') handleMarketUpdate(msg.payload);
      if (msg.type === 'alert_triggered') handleAlertTriggered(msg.payload);
    } catch (_) {}
  };

  ws.onclose = () => {
    ws = null;
    document.getElementById('ws-dot')?.classList.remove('connected');
    state.wsReconnectTimer = setTimeout(connectWS, 5000);
  };

  ws.onerror = () => { ws.close(); };

  // Keepalive ping
  setInterval(() => { if (ws?.readyState === WebSocket.OPEN) ws.send('ping'); }, 25000);
}

function disconnectWS() {
  clearTimeout(state.wsReconnectTimer);
  if (ws) { ws.close(); ws = null; }
}

function handleMarketUpdate(payload) {
  // Update index cards if on dashboard
  if (state.currentPage === 'dashboard' && payload.indices) {
    payload.indices.forEach(idx => {
      const el = document.querySelector(`[data-ticker="${idx.ticker}"]`);
      if (el) {
        el.querySelector('.price')?.replaceChildren(document.createTextNode(fmt.price(idx.price, idx.currency)));
        const chEl = el.querySelector('.change');
        if (chEl) {
          chEl.textContent = fmt.pct(idx.change_pct);
          chEl.className = 'change ' + fmt.pctClass(idx.change_pct);
        }
      }
    });
  }
  // Update watchlist table if on watchlists page
  if (state.currentPage === 'watchlists' && payload.watchlist) {
    payload.watchlist.forEach(q => {
      const row = document.querySelector(`tr[data-ticker="${q.ticker}"]`);
      if (row) {
        row.querySelector('.col-price')?.replaceChildren(document.createTextNode(fmt.price(q.price, q.currency)));
        const chEl = row.querySelector('.col-chg');
        if (chEl) { chEl.textContent = fmt.pct(q.change_pct); chEl.className = 'col-chg ' + fmt.pctClass(q.change_pct); }
      }
    });
  }
}

function handleAlertTriggered(payload) {
  toast(`🔔 Alert: ${payload.message}`, 'warn', 8000);
}

// ── Router ────────────────────────────────────────────────────────────────────
function navigate(page, params = {}) {
  const hash = params.ticker ? `${page}/${params.ticker}` : page;
  location.hash = hash;
}

function router() {
  const raw = location.hash.slice(1) || 'dashboard';
  const parts = raw.split('/');
  const page = parts[0];
  const param = parts[1];

  destroyAllCharts();
  state.currentPage = page;

  document.querySelectorAll('.nav-item').forEach(el => {
    el.classList.toggle('active', el.dataset.page === page);
  });

  const content = document.getElementById('page-content');
  content.innerHTML = '';  // Clear

  switch (page) {
    case 'dashboard':  renderDashboard(content); break;
    case 'watchlists': renderWatchlists(content); break;
    case 'symbol':     renderSymbol(content, param); break;
    case 'portfolio':  renderPortfolio(content); break;
    case 'alerts':     renderAlerts(content); break;
    case 'settings':   renderSettings(content); break;
    case 'debug':      renderDebug(content); break;
    default:           renderDashboard(content);
  }
}

// ── Show / hide login ─────────────────────────────────────────────────────────
function showLogin() {
  document.getElementById('login-page').style.display = 'flex';
  document.getElementById('app-shell').style.display = 'none';
}

function showApp() {
  document.getElementById('login-page').style.display = 'none';
  document.getElementById('app-shell').style.display = 'grid';
  document.getElementById('topbar-user').textContent = state.user.username;
  if (state.user.role === 'admin') document.getElementById('nav-admin').style.display = 'flex';

  // Apply saved theme
  api.get('/api/settings').then(s => {
    applyTheme(s.theme);
  }).catch(() => {});

  connectWS();
  router();
}

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  state.theme = theme;
}

// ── LOGIN PAGE ────────────────────────────────────────────────────────────────
document.getElementById('login-form')?.addEventListener('submit', async (e) => {
  e.preventDefault();
  const errEl = document.getElementById('login-error');
  errEl.style.display = 'none';
  const btn = e.target.querySelector('button[type=submit]');
  btn.disabled = true; btn.textContent = 'Signing in…';

  try {
    const user = await api.post('/api/auth/login', {
      username: document.getElementById('login-user').value,
      password: document.getElementById('login-pass').value,
    });
    state.user = user;
    showApp();
  } catch (err) {
    errEl.textContent = err.message;
    errEl.style.display = 'block';
    btn.disabled = false; btn.textContent = 'Sign In';
  }
});

document.getElementById('btn-logout')?.addEventListener('click', logout);

// ── DASHBOARD PAGE ────────────────────────────────────────────────────────────
// Show short ticker (strip exchange suffix like .DE, .NL, .FR, .UK, .IT, .SW)
function _shortTicker(ticker) {
  return ticker.replace(/\.[A-Z]{2,3}$/, '');
}

function _rankRows(items, n = 5) {
  return items.slice(0, n).map((it, i) => `
    <div class="rank-row" onclick="navigate('symbol','${it.ticker}')" title="${it.ticker}">
      <span class="rank-num">${i + 1}</span>
      <span class="rank-name">
        <strong>${_shortTicker(it.ticker)}</strong>
        <span>${it.name || ''}</span>
      </span>
      <span class="rank-period">
        <span class="rp-val ${fmt.pctClass(it.change_pct)}">${fmt.pct(it.change_pct)}</span>
        <span class="rp-lbl">24H</span>
      </span>
      <span class="rank-period">
        <span class="rp-val ${fmt.pctClass(it.return_1m)}">${it.return_1m != null ? fmt.pct(it.return_1m) : '—'}</span>
        <span class="rp-lbl">1M</span>
      </span>
      <span class="rank-period">
        <span class="rp-val ${fmt.pctClass(it.return_1y)}">${it.return_1y != null ? fmt.pct(it.return_1y) : '—'}</span>
        <span class="rp-lbl">1A</span>
      </span>
    </div>
  `).join('');
}

function _bestWorstSection(data) {
  if (!data || !data.length) return `<p class="muted" style="font-size:12px">No data.</p>`;
  const valid = data.filter(d => d.change_pct != null);
  const sorted = [...valid].sort((a, b) => b.change_pct - a.change_pct);
  const best  = sorted.slice(0, 5);
  const worst = sorted.slice(-5).reverse();
  return `
    <div class="rank-section">
      <span class="rank-section-label best">▲ Migliori</span>
      ${_rankRows(best)}
    </div>
    <div class="rank-section" style="margin-top:12px">
      <span class="rank-section-label worst">▼ Peggiori</span>
      ${_rankRows(worst)}
    </div>
  `;
}

async function renderDashboard(container) {
  const skelCol = `
    <div class="card">
      <div style="height:14px;width:60%;background:var(--surface3);border-radius:4px;margin-bottom:16px"></div>
      ${skelRows(5)}
      <div style="height:12px;width:40%;background:var(--surface3);border-radius:4px;margin:14px 0 8px"></div>
      ${skelRows(5)}
    </div>`;

  container.innerHTML = `
    <div class="page-header">
      <h1 class="page-title">Dashboard <small>Market Overview</small></h1>
      <button class="btn btn-ghost btn-xs" id="dash-refresh">↻ Refresh</button>
    </div>

    <div class="dash-cols">
      <div>
        <div class="col-header">
          <span class="col-header-icon">📊</span>
          <span class="col-header-title">Listini</span>
        </div>
        <div class="card" id="col-indices">${skelRows(10)}</div>
      </div>
      <div>
        <div class="col-header">
          <span class="col-header-icon">🏢</span>
          <span class="col-header-title">Titoli Azionari</span>
        </div>
        <div class="card" id="col-stocks">${skelRows(10)}</div>
      </div>
      <div>
        <div class="col-header">
          <span class="col-header-icon">₿</span>
          <span class="col-header-title">Criptovalute</span>
        </div>
        <div class="card" id="col-crypto">${skelRows(10)}</div>
      </div>
    </div>

    <div class="grid-2" style="margin-top:24px">
      <div>
        <div class="col-header">
          <span class="col-header-icon">⭐</span>
          <span class="col-header-title">Watchlist</span>
        </div>
        <div class="card" id="dash-watchlist">${skelRows(5)}</div>
      </div>
      <div>
        <div class="col-header">
          <span class="col-header-icon">💼</span>
          <span class="col-header-title">Portfolio</span>
        </div>
        <div class="card" id="dash-portfolio">${skelRows(5)}</div>
      </div>
    </div>
  `;

  document.getElementById('dash-refresh')?.addEventListener('click', () => {
    destroyAllCharts();
    renderDashboard(container);
  });

  // Parallel data fetch
  const [markets, stocks, crypto, watchlists, portfolios] = await Promise.allSettled([
    api.get('/api/markets/overview'),
    api.get('/api/stocks/top'),
    api.get('/api/crypto/overview'),
    api.get('/api/watchlists'),
    api.get('/api/portfolios'),
  ]);

  // Column 1 — Indices best/worst
  const colIndices = document.getElementById('col-indices');
  if (markets.status === 'fulfilled') {
    colIndices.innerHTML = _bestWorstSection(markets.value.data);
  } else {
    colIndices.innerHTML = `<span class="neg">Impossibile caricare i listini.</span>`;
  }

  // Column 2 — Stocks best/worst
  const colStocks = document.getElementById('col-stocks');
  if (stocks.status === 'fulfilled') {
    colStocks.innerHTML = _bestWorstSection(stocks.value.data);
  } else {
    colStocks.innerHTML = `<span class="neg">Impossibile caricare i titoli.</span>`;
  }

  // Column 3 — Crypto compact list
  const colCrypto = document.getElementById('col-crypto');
  if (crypto.status === 'fulfilled') {
    const coins = crypto.value.data;
    colCrypto.innerHTML = coins.map((c, i) => `
      <div class="crypto-row">
        <span class="crypto-rank">${i + 1}</span>
        ${c.image ? `<img class="crypto-img-sm" src="${c.image}" alt="${c.symbol}" loading="lazy">` : ''}
        <span class="crypto-info">
          <strong>${c.symbol}</strong>
          <span>${c.name}</span>
        </span>
        <span class="crypto-price-col">
          <span class="price-val">${fmt.price(c.price_usd, 'USD')}</span>
          <span class="pct-val ${fmt.pctClass(c.change_24h_pct)}">${fmt.pct(c.change_24h_pct)}</span>
        </span>
        ${c.stale ? '<span class="badge badge-stale" style="font-size:9px">STALE</span>' : ''}
      </div>
    `).join('');
  } else {
    colCrypto.innerHTML = `<span class="neg">Impossibile caricare le crypto.</span>`;
  }

  // ── Watchlist ──────────────────────────────────────────────────────────────
  const dashWl = document.getElementById('dash-watchlist');
  if (watchlists.status === 'fulfilled' && watchlists.value.length > 0) {
    const wl = watchlists.value[0];
    if (wl.items.length) {
      dashWl.innerHTML = `
        <div style="font-size:11px;font-weight:700;color:var(--text-muted);margin-bottom:8px">${escHtml(wl.name)}</div>
        <div class="table-wrap">
          <table class="data-table">
            <thead><tr>
              <th>Ticker</th><th>Nome</th>
              <th class="num">Prezzo</th><th class="num">Var%</th>
            </tr></thead>
            <tbody>
              ${wl.items.map(it => `
                <tr style="cursor:pointer" onclick="navigate('symbol','${it.ticker}')">
                  <td><strong>${it.ticker}</strong></td>
                  <td class="muted" style="font-size:12px">${escHtml(it.name || '')}</td>
                  <td class="num">${fmt.price(it.price, it.currency)}</td>
                  <td class="num ${fmt.pctClass(it.change_pct)}">${fmt.pct(it.change_pct)}</td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
        ${watchlists.value.length > 1 ? `<div class="muted" style="font-size:11px;margin-top:6px">+${watchlists.value.length - 1} altre watchlist</div>` : ''}
        <div style="margin-top:10px"><a href="#watchlists" style="font-size:12px">Vai alle Watchlist →</a></div>
      `;
    } else {
      dashWl.innerHTML = `<div class="empty-state" style="padding:16px">
        <p class="muted" style="font-size:13px">Nessun titolo in <strong>${escHtml(wl.name)}</strong>.</p>
        <a href="#watchlists" style="font-size:12px">Aggiungi titoli →</a>
      </div>`;
    }
  } else if (watchlists.status === 'fulfilled') {
    dashWl.innerHTML = `<div class="empty-state" style="padding:16px">
      <p class="muted" style="font-size:13px">Nessuna watchlist.</p>
      <a href="#watchlists" style="font-size:12px">Crea una watchlist →</a>
    </div>`;
  } else {
    dashWl.innerHTML = `<span class="neg">Impossibile caricare la watchlist.</span>`;
  }

  // ── Portfolio ──────────────────────────────────────────────────────────────
  const dashPf = document.getElementById('dash-portfolio');
  if (portfolios.status === 'fulfilled' && portfolios.value.length > 0) {
    const pf = portfolios.value[0];
    try {
      const items = await api.get(`/api/portfolios/${pf.id}/holdings`);
      const totVal  = items.reduce((s, h) => s + (h.current_value  ?? 0), 0) || null;
      const totCost = items.reduce((s, h) => s + (h.total_cost     ?? 0), 0) || null;
      const totPnl  = items.reduce((s, h) => s + (h.unrealized_pnl ?? 0), 0) || null;
      const totPct  = (totCost && totPnl != null) ? (totPnl / totCost * 100) : null;

      dashPf.innerHTML = `
        <div style="font-size:11px;font-weight:700;color:var(--text-muted);margin-bottom:8px">${escHtml(pf.name)}</div>
        <div class="dash-pf-summary">
          <div class="dash-pf-stat">
            <span class="dash-pf-label">Valore</span>
            <span class="dash-pf-value">${fmt.price(totVal, pf.base_currency)}</span>
          </div>
          <div class="dash-pf-stat">
            <span class="dash-pf-label">Investito</span>
            <span class="dash-pf-value">${fmt.price(totCost, pf.base_currency)}</span>
          </div>
          <div class="dash-pf-stat">
            <span class="dash-pf-label">P&L</span>
            <span class="dash-pf-value ${fmt.pctClass(totPnl)}">${fmt.price(totPnl, pf.base_currency)}</span>
          </div>
          <div class="dash-pf-stat">
            <span class="dash-pf-label">Rendimento</span>
            <span class="dash-pf-value ${fmt.pctClass(totPct)}">${totPct != null ? fmt.pct(totPct) : '—'}</span>
          </div>
        </div>
        ${items.length ? `
        <div class="table-wrap" style="margin-top:12px">
          <table class="data-table">
            <thead><tr>
              <th>Ticker</th><th class="num">Qtà</th>
              <th class="num">Valore</th><th class="num">P&L%</th>
            </tr></thead>
            <tbody>
              ${items.map(h => `
                <tr style="cursor:pointer" onclick="navigate('symbol','${h.ticker}')">
                  <td><strong>${h.ticker}</strong></td>
                  <td class="num">${fmt.num(h.qty, 4)}</td>
                  <td class="num">${fmt.price(h.current_value, pf.base_currency)}</td>
                  <td class="num ${fmt.pctClass(h.unrealized_pnl_pct)}">${h.unrealized_pnl_pct != null ? fmt.pct(h.unrealized_pnl_pct) : '—'}</td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>` : '<p class="muted" style="font-size:12px;margin-top:8px">Nessuna posizione aperta.</p>'}
        ${portfolios.value.length > 1 ? `<div class="muted" style="font-size:11px;margin-top:6px">+${portfolios.value.length - 1} altri portfolio</div>` : ''}
        <div style="margin-top:10px"><a href="#portfolio" style="font-size:12px">Vai al Portfolio →</a></div>
      `;
    } catch (_) {
      dashPf.innerHTML = `<span class="neg">Impossibile caricare le posizioni.</span>`;
    }
  } else if (portfolios.status === 'fulfilled') {
    dashPf.innerHTML = `<div class="empty-state" style="padding:16px">
      <p class="muted" style="font-size:13px">Nessun portfolio.</p>
      <a href="#portfolio" style="font-size:12px">Crea un portfolio →</a>
    </div>`;
  } else {
    dashPf.innerHTML = `<span class="neg">Impossibile caricare il portfolio.</span>`;
  }
}

// ── WATCHLISTS PAGE ───────────────────────────────────────────────────────────
async function renderWatchlists(container) {
  container.innerHTML = `
    <div class="page-header">
      <h1 class="page-title">Watchlists</h1>
      <button class="btn btn-primary btn-xs" id="btn-new-wl">+ New Watchlist</button>
    </div>
    <div id="wl-container">${skelRows(6)}</div>
  `;

  document.getElementById('btn-new-wl')?.addEventListener('click', async () => {
    const name = prompt('Watchlist name:');
    if (!name) return;
    try {
      await api.post('/api/watchlists', { name });
      toast('Watchlist created', 'success');
      renderWatchlists(container);
    } catch (e) { toast(e.message, 'error'); }
  });

  try {
    const lists = await api.get('/api/watchlists');
    renderWatchlistTables(container, lists);
  } catch (e) {
    document.getElementById('wl-container').innerHTML = `<span class="neg">${e.message}</span>`;
  }
}

function renderWatchlistTables(container, lists) {
  const wrap = document.getElementById('wl-container');
  if (!lists.length) {
    wrap.innerHTML = `<div class="empty-state">
      <div class="empty-state-icon">⭐</div>
      <h3>No watchlists</h3>
      <p>Click "+ New Watchlist" to get started.</p>
    </div>`;
    return;
  }

  wrap.innerHTML = lists.map(wl => `
    <div class="card" style="margin-bottom:16px" id="wl-${wl.id}">
      <div class="flex items-center justify-between" style="margin-bottom:12px">
        <span style="font-weight:700;font-size:15px">${escHtml(wl.name)}</span>
        <div style="display:flex;gap:6px">
          <a href="/api/watchlists/${wl.id}/export" class="btn btn-xs">⬇ Export</a>
          <button class="btn btn-xs btn-danger" data-del-wl="${wl.id}">✕ Delete</button>
        </div>
      </div>

      <div style="display:flex;gap:8px;margin-bottom:4px;align-items:center" class="autocomplete-wrap">
        <input class="form-control" id="ac-${wl.id}" placeholder="Es: RACE.IT, VWCE.IT, AAPL, ^SPX…" style="max-width:300px"
               autocomplete="off" spellcheck="false"/>
        <button class="btn btn-primary btn-xs" data-add-item="${wl.id}">+ Aggiungi</button>
        <div class="autocomplete-dropdown" id="acd-${wl.id}" style="display:none"></div>
      </div>
      <p class="muted" style="font-size:11px;margin-bottom:10px">
        Italia: <code>RACE.IT</code> <code>ISP.IT</code> <code>VWCE.IT</code>
        &nbsp;·&nbsp; US: <code>AAPL</code>
        &nbsp;·&nbsp; UK: <code>SHEL.UK</code>
        &nbsp;·&nbsp; Germania: <code>SAP.DE</code>
        &nbsp;·&nbsp; Indici: <code>^SPX</code>
        &nbsp;·&nbsp; Puoi usare anche il formato Yahoo Finance: <code>RACE.MI</code>
      </p>

      ${wl.items.length === 0 ? '<p class="muted" style="font-size:13px">No symbols yet.</p>' : `
      <div class="table-wrap">
        <table class="data-table">
          <thead><tr>
            <th>Ticker</th><th>Name</th>
            <th class="num">Price</th><th class="num">Change</th><th class="num">Chg%</th>
            <th class="num">Currency</th><th></th>
          </tr></thead>
          <tbody>
            ${wl.items.map(it => `
              <tr data-ticker="${it.ticker}">
                <td><a href="#" onclick="event.preventDefault();navigate('symbol','${it.ticker}')"
                       style="font-weight:700">${it.ticker}</a></td>
                <td class="muted">${escHtml(it.name || '')}</td>
                <td class="num col-price">${fmt.price(it.price, it.currency)}</td>
                <td class="num ${fmt.pctClass(it.change_abs)}">${it.change_abs != null ? fmt.price(it.change_abs, it.currency) : '—'}</td>
                <td class="num col-chg ${fmt.pctClass(it.change_pct)}">${fmt.pct(it.change_pct)}</td>
                <td class="muted">${it.currency || '—'}</td>
                <td class="actions">
                  <button class="btn btn-ghost btn-xs" data-del-item="${wl.id}" data-ticker="${it.ticker}">✕</button>
                </td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
      `}
    </div>
  `).join('');

  // Autocomplete
  lists.forEach(wl => {
    const inp = document.getElementById(`ac-${wl.id}`);
    const drop = document.getElementById(`acd-${wl.id}`);
    let acTimer;

    inp?.addEventListener('input', () => {
      clearTimeout(acTimer);
      const q = inp.value.trim();
      if (q.length < 1) { drop.style.display = 'none'; return; }

      acTimer = setTimeout(async () => {
        // 1. Cerca nel DB locale
        let items = [];
        try {
          const res = await api.get(`/api/symbols/search?q=${encodeURIComponent(q)}`);
          items = res.results || [];
        } catch (_) {}

        // 2. Se DB vuoto, prova risoluzione live su Stooq
        if (!items.length && q.length >= 2) {
          drop.innerHTML = `<div class="autocomplete-item ac-loading">🔍 Cerco "${escHtml(q)}"…</div>`;
          drop.style.display = 'block';
          try {
            const live = await api.get(`/api/symbols/resolve?ticker=${encodeURIComponent(q)}`);
            items = [live];
          } catch (_) {
            // Ticker non trovato: offri comunque l'aggiunta diretta
            items = [{ ticker: q.toUpperCase(), name: 'Aggiungi direttamente (non verificato)', _unverified: true }];
          }
        }

        if (!items.length) { drop.style.display = 'none'; return; }

        drop.innerHTML = items.slice(0, 8).map(s =>
          `<div class="autocomplete-item${s._unverified ? ' ac-unverified' : ''}" data-ticker="${s.ticker}" tabindex="0">
             <span class="ac-ticker">${s.ticker}</span>
             <span class="ac-name">${escHtml(s.name || '')}</span>
             ${s.price ? `<span class="ac-price muted">${fmt.price(s.price, s.currency)}</span>` : ''}
           </div>`
        ).join('');
        drop.style.display = 'block';
        drop.querySelectorAll('.autocomplete-item').forEach(it => {
          it.addEventListener('click', () => { inp.value = it.dataset.ticker; drop.style.display = 'none'; });
        });
      }, 350);
    });

    inp?.addEventListener('blur', () => setTimeout(() => { drop.style.display = 'none'; }, 200));
  });

  // Delegate events
  wrap.addEventListener('click', async (e) => {
    const delWl = e.target.closest('[data-del-wl]');
    const addItem = e.target.closest('[data-add-item]');
    const delItem = e.target.closest('[data-del-item]');

    if (delWl) {
      if (!confirm('Delete this watchlist?')) return;
      try { await api.delete(`/api/watchlists/${delWl.dataset.delWl}`); toast('Deleted', 'success'); renderWatchlists(container); }
      catch (e) { toast(e.message, 'error'); }
    }

    if (addItem) {
      const wlId = addItem.dataset.addItem;
      const ticker = document.getElementById(`ac-${wlId}`)?.value?.trim().toUpperCase();
      if (!ticker) return;
      try { await api.post(`/api/watchlists/${wlId}/items`, { ticker }); toast(`${ticker} added`, 'success'); renderWatchlists(container); }
      catch (e) { toast(e.message, 'error'); }
    }

    if (delItem) {
      try { await api.delete(`/api/watchlists/${delItem.dataset.delItem}/items/${delItem.dataset.ticker}`); toast('Removed', 'success'); renderWatchlists(container); }
      catch (e) { toast(e.message, 'error'); }
    }
  });
}

// ── SYMBOL DETAIL PAGE ────────────────────────────────────────────────────────
async function renderSymbol(container, ticker) {
  if (!ticker) { container.innerHTML = '<p class="neg">No ticker specified.</p>'; return; }
  ticker = ticker.toUpperCase();

  container.innerHTML = `
    <div class="page-header">
      <h1 class="page-title" id="sym-title">${ticker} <small>Loading…</small></h1>
    </div>
    <div class="grid-4" id="sym-stats" style="margin-bottom:20px">${skelCards(4, 80)}</div>
    <div class="chart-wrap">
      <div class="period-btns" id="period-btns">
        ${['1mo','3mo','6mo','1y','2y','5y','max'].map((p, i) =>
          `<button class="period-btn ${i === 3 ? 'active' : ''}" data-period="${p}">${p}</button>`
        ).join('')}
      </div>
      <canvas id="sym-chart" height="180"></canvas>
    </div>
  `;

  let currentPeriod = '1y';

  async function loadHistory(period) {
    try {
      const hist = await api.get(`/api/symbols/${ticker}/history?period=${period}&interval=1d`);
      const labels = hist.data.map(b => b.ts.slice(0, 10));
      const vals = hist.data.map(b => b.close);
      const color = vals.length >= 2 && vals[vals.length - 1] >= vals[0] ? '#3fb950' : '#f85149';
      lineChart('sym-chart', labels, [{
        label: ticker,
        data: vals,
        borderColor: color,
        backgroundColor: color + '22',
        fill: true,
        tension: 0.2,
      }]);
    } catch (e) { toast(`History: ${e.message}`, 'warn'); }
  }

  document.getElementById('period-btns')?.addEventListener('click', (e) => {
    const btn = e.target.closest('.period-btn');
    if (!btn) return;
    document.querySelectorAll('.period-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    currentPeriod = btn.dataset.period;
    loadHistory(currentPeriod);
  });

  // Load quote and history in parallel
  const [quote, _] = await Promise.all([
    api.get(`/api/symbols/${ticker}/quote`).catch(() => null),
    loadHistory(currentPeriod),
  ]);

  if (quote) {
    document.getElementById('sym-title').innerHTML =
      `${ticker} <small>${escHtml(quote.name || '')}</small>`;

    document.getElementById('sym-stats').innerHTML = `
      <div class="card"><div class="card-title">Price</div>
        <div class="card-value">${fmt.price(quote.price, quote.currency)}</div>
        <div class="card-sub ${fmt.pctClass(quote.change_pct)}">${fmt.pct(quote.change_pct)} today</div>
        ${quote.stale ? '<span class="badge badge-stale">STALE</span>' : ''}
      </div>
      <div class="card"><div class="card-title">Open</div>
        <div class="card-value">${fmt.price(quote.open, quote.currency)}</div></div>
      <div class="card">
        <div class="card-title">Day Range</div>
        <div class="card-value" style="font-size:14px">
          ${fmt.price(quote.low, quote.currency)} – ${fmt.price(quote.high, quote.currency)}
        </div>
      </div>
      <div class="card"><div class="card-title">Volume</div>
        <div class="card-value" style="font-size:15px">${fmt.num(quote.volume, 0)}</div>
        <div class="card-sub">${quote.currency || ''}</div>
      </div>
    `;
  }
}

// ── PORTFOLIO PAGE ────────────────────────────────────────────────────────────
async function renderPortfolio(container) {
  container.innerHTML = `
    <div class="page-header">
      <h1 class="page-title">Portfolio</h1>
      <button class="btn btn-primary btn-xs" id="btn-new-port">+ New Portfolio</button>
    </div>
    <div id="port-selector" style="margin-bottom:16px">${skelLines(1)}</div>
    <div id="port-content">${skelRows(6)}</div>
  `;

  document.getElementById('btn-new-port')?.addEventListener('click', async () => {
    const name = prompt('Portfolio name:');
    if (!name) return;
    try { await api.post('/api/portfolios', { name }); toast('Portfolio created', 'success'); renderPortfolio(container); }
    catch (e) { toast(e.message, 'error'); }
  });

  try {
    const portfolios = await api.get('/api/portfolios');
    if (!portfolios.length) {
      document.getElementById('port-content').innerHTML = `<div class="empty-state">
        <div class="empty-state-icon">💼</div><h3>No portfolios</h3>
        <p>Click "+ New Portfolio" to create one.</p></div>`;
      document.getElementById('port-selector').innerHTML = '';
      return;
    }

    let selectedId = portfolios[0].id;

    function renderSelector() {
      document.getElementById('port-selector').innerHTML = `
        <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
          ${portfolios.map(p => `
            <button class="btn btn-xs ${p.id === selectedId ? 'btn-primary' : ''}" data-pid="${p.id}">${escHtml(p.name)}</button>
          `).join('')}
          <button class="btn btn-xs btn-danger" id="btn-del-port">Delete</button>
        </div>
      `;
      document.querySelectorAll('[data-pid]').forEach(b => {
        b.addEventListener('click', () => { selectedId = +b.dataset.pid; renderSelector(); loadPortfolio(); });
      });
      document.getElementById('btn-del-port')?.addEventListener('click', async () => {
        if (!confirm('Delete this portfolio?')) return;
        try { await api.delete(`/api/portfolios/${selectedId}`); toast('Deleted', 'success'); renderPortfolio(container); }
        catch (e) { toast(e.message, 'error'); }
      });
    }

    async function loadPortfolio() {
      const content = document.getElementById('port-content');
      content.innerHTML = `
        <div class="tabs" id="port-tabs">
          <button class="tab-btn active" data-tab="holdings">Holdings</button>
          <button class="tab-btn" data-tab="transactions">Transactions</button>
          <button class="tab-btn" data-tab="performance">Performance</button>
        </div>
        <div id="port-tab-content">${skelRows(5)}</div>
      `;

      document.getElementById('port-tabs')?.addEventListener('click', (e) => {
        const btn = e.target.closest('.tab-btn');
        if (!btn) return;
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        loadTab(btn.dataset.tab);
      });

      loadTab('holdings');
    }

    async function loadTab(tab) {
      const tc = document.getElementById('port-tab-content');
      tc.innerHTML = skelRows(5);

      if (tab === 'holdings') {
        try {
          const holdings = await api.get(`/api/portfolios/${selectedId}/holdings`);
          if (!holdings.length) {
            tc.innerHTML = `<div class="empty-state"><p>No holdings yet. Add a transaction first.</p></div>`; return;
          }
          const totalValue = holdings.reduce((s, h) => s + (h.current_value || 0), 0);
          const totalCost = holdings.reduce((s, h) => s + (h.total_cost || 0), 0);
          const totalPnl = totalValue - totalCost;
          tc.innerHTML = `
            <div class="grid-4" style="margin-bottom:20px">
              <div class="metric-card"><div class="metric-label">Total Value</div>
                <div class="metric-value">${fmt.price(totalValue, 'EUR')}</div></div>
              <div class="metric-card"><div class="metric-label">Total Cost</div>
                <div class="metric-value">${fmt.price(totalCost, 'EUR')}</div></div>
              <div class="metric-card"><div class="metric-label">Unrealized P&L</div>
                <div class="metric-value ${totalPnl >= 0 ? 'pos' : 'neg'}">${fmt.price(totalPnl, 'EUR')}</div></div>
              <div class="metric-card"><div class="metric-label">Return</div>
                <div class="metric-value ${totalPnl >= 0 ? 'pos' : 'neg'}">${totalCost ? fmt.pct(totalPnl / totalCost * 100) : '—'}</div></div>
            </div>
            <div class="table-wrap">
              <table class="data-table">
                <thead><tr><th>Ticker</th><th>Name</th><th class="num">Qty</th>
                  <th class="num">Avg Cost</th><th class="num">Total Cost</th>
                  <th class="num">Cur. Price</th><th class="num">Value</th>
                  <th class="num">P&L</th><th class="num">P&L %</th></tr></thead>
                <tbody>
                  ${holdings.map(h => `<tr>
                    <td><a href="#" onclick="event.preventDefault();navigate('symbol','${h.ticker}')"
                           style="font-weight:700">${h.ticker}</a></td>
                    <td class="muted">${escHtml(h.name || '')}</td>
                    <td class="num">${fmt.num(h.qty, 4)}</td>
                    <td class="num">${fmt.price(h.avg_cost, h.currency)}</td>
                    <td class="num">${fmt.price(h.total_cost, h.currency)}</td>
                    <td class="num">${fmt.price(h.current_price, h.currency)}</td>
                    <td class="num">${fmt.price(h.current_value, h.currency)}</td>
                    <td class="num ${fmt.pctClass(h.unrealized_pnl)}">${fmt.price(h.unrealized_pnl, h.currency)}</td>
                    <td class="num ${fmt.pctClass(h.unrealized_pnl_pct)}">${fmt.pct(h.unrealized_pnl_pct)}</td>
                  </tr>`).join('')}
                </tbody>
              </table>
            </div>
          `;
        } catch (e) { tc.innerHTML = `<span class="neg">${e.message}</span>`; }
      }

      if (tab === 'transactions') {
        tc.innerHTML = `
          <div style="margin-bottom:16px">
            <button class="btn btn-primary btn-xs" id="btn-add-tx">+ Add Transaction</button>
            <a href="/api/portfolios/${selectedId}/transactions/export" class="btn btn-xs" style="margin-left:6px">⬇ Export CSV</a>
          </div>
          <div id="tx-form-wrap" style="display:none"></div>
          <div id="tx-table">${skelRows(5)}</div>
        `;

        document.getElementById('btn-add-tx')?.addEventListener('click', () => {
          const fw = document.getElementById('tx-form-wrap');
          fw.style.display = fw.style.display === 'none' ? 'block' : 'none';
          if (fw.style.display === 'block') renderTxForm(fw, selectedId, () => loadTab('transactions'));
        });

        try {
          const txns = await api.get(`/api/portfolios/${selectedId}/transactions`);
          const tbl = document.getElementById('tx-table');
          if (!txns.length) { tbl.innerHTML = `<p class="muted">No transactions yet.</p>`; return; }
          tbl.innerHTML = `
            <div class="table-wrap">
              <table class="data-table">
                <thead><tr><th>Date</th><th>Ticker</th><th>Side</th><th class="num">Qty</th>
                  <th class="num">Price</th><th class="num">Fees</th><th>Note</th><th></th></tr></thead>
                <tbody>
                  ${txns.map(t => `<tr>
                    <td class="muted">${fmt.dateShort(t.ts)}</td>
                    <td><strong>${t.ticker}</strong></td>
                    <td><span class="badge ${t.side === 'buy' ? 'badge-pos' : 'badge-neg'}">${t.side.toUpperCase()}</span></td>
                    <td class="num">${fmt.num(t.qty, 4)}</td>
                    <td class="num">${fmt.num(t.price, 4)}</td>
                    <td class="num">${fmt.num(t.fees, 2)}</td>
                    <td class="muted">${escHtml(t.note || '')}</td>
                    <td class="actions">
                      <button class="btn btn-ghost btn-xs" data-del-tx="${t.id}">✕</button>
                    </td>
                  </tr>`).join('')}
                </tbody>
              </table>
            </div>
          `;
          tbl.addEventListener('click', async (e) => {
            const btn = e.target.closest('[data-del-tx]');
            if (!btn) return;
            if (!confirm('Delete this transaction?')) return;
            try { await api.delete(`/api/portfolios/${selectedId}/transactions/${btn.dataset.delTx}`); toast('Deleted', 'success'); loadTab('transactions'); }
            catch (err) { toast(err.message, 'error'); }
          });
        } catch (e) { document.getElementById('tx-table').innerHTML = `<span class="neg">${e.message}</span>`; }
      }

      if (tab === 'performance') {
        tc.innerHTML = `<div id="perf-content">${skelRows(4)}</div>`;
        try {
          const perf = await api.get(`/api/portfolios/${selectedId}/performance`);
          const { equity_curve, metrics } = perf;

          if (!equity_curve.length) {
            document.getElementById('perf-content').innerHTML = `<div class="empty-state"><p>Not enough data for performance chart.</p></div>`;
            return;
          }

          document.getElementById('perf-content').innerHTML = `
            ${Object.keys(metrics).length ? `
            <div class="grid-4" style="margin-bottom:20px">
              <div class="metric-card"><div class="metric-label">Total Return</div>
                <div class="metric-value ${(metrics.total_return_pct || 0) >= 0 ? 'pos' : 'neg'}">${fmt.pct(metrics.total_return_pct)}</div></div>
              <div class="metric-card"><div class="metric-label">Volatility (ann.)</div>
                <div class="metric-value">${fmt.pct(metrics.volatility_annualized_pct)}</div></div>
              <div class="metric-card"><div class="metric-label">Max Drawdown</div>
                <div class="metric-value neg">-${fmt.num(metrics.max_drawdown_pct, 2)}%</div></div>
              <div class="metric-card"><div class="metric-label">Unrealized P&L</div>
                <div class="metric-value ${(metrics.unrealized_pnl || 0) >= 0 ? 'pos' : 'neg'}">${fmt.price(metrics.unrealized_pnl, 'EUR')}</div></div>
            </div>` : ''}
            <div class="chart-wrap">
              <div class="chart-title">Equity Curve</div>
              <canvas id="equity-chart" height="200"></canvas>
            </div>
          `;

          const labels = equity_curve.map(p => p.date);
          const values = equity_curve.map(p => p.value);
          const color = values[values.length - 1] >= values[0] ? '#3fb950' : '#f85149';
          lineChart('equity-chart', labels, [{
            label: 'Portfolio Value',
            data: values,
            borderColor: color,
            backgroundColor: color + '22',
            fill: true,
            tension: 0.1,
          }]);
        } catch (e) { document.getElementById('perf-content').innerHTML = `<span class="neg">${e.message}</span>`; }
      }
    }

    renderSelector();
    await loadPortfolio();
  } catch (e) {
    document.getElementById('port-content').innerHTML = `<span class="neg">${e.message}</span>`;
  }
}

function renderTxForm(container, portfolioId, onSuccess) {
  const now = new Date().toISOString().slice(0, 16);
  container.innerHTML = `
    <div class="card" style="margin-bottom:16px;max-width:600px">
      <div style="font-weight:700;margin-bottom:12px">Add Transaction</div>
      <form id="tx-form">
        <div class="form-row">
          <div class="form-group">
            <label class="form-label">Ticker</label>
            <input class="form-control" name="ticker" required placeholder="e.g. AAPL"/>
          </div>
          <div class="form-group">
            <label class="form-label">Date & Time</label>
            <input class="form-control" name="ts" type="datetime-local" value="${now}" required/>
          </div>
        </div>
        <div class="form-row">
          <div class="form-group">
            <label class="form-label">Side</label>
            <select class="form-control" name="side">
              <option value="buy">Buy</option><option value="sell">Sell</option>
            </select>
          </div>
          <div class="form-group">
            <label class="form-label">Quantity</label>
            <input class="form-control" name="qty" type="number" step="any" min="0.0001" required placeholder="0"/>
          </div>
        </div>
        <div class="form-row">
          <div class="form-group">
            <label class="form-label">Price</label>
            <input class="form-control" name="price" type="number" step="any" min="0" required placeholder="0.00"/>
          </div>
          <div class="form-group">
            <label class="form-label">Fees</label>
            <input class="form-control" name="fees" type="number" step="any" min="0" value="0"/>
          </div>
        </div>
        <div class="form-group">
          <label class="form-label">Note (optional)</label>
          <input class="form-control" name="note" placeholder="Optional note"/>
        </div>
        <div style="display:flex;gap:8px">
          <button type="submit" class="btn btn-primary btn-xs">Add Transaction</button>
          <button type="button" class="btn btn-xs" id="cancel-tx-form">Cancel</button>
        </div>
      </form>
    </div>
  `;

  document.getElementById('cancel-tx-form')?.addEventListener('click', () => {
    container.style.display = 'none';
  });

  document.getElementById('tx-form')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const data = Object.fromEntries(fd.entries());
    data.qty = +data.qty; data.price = +data.price; data.fees = +(data.fees || 0);
    try {
      await api.post(`/api/portfolios/${portfolioId}/transactions`, data);
      toast('Transaction added', 'success');
      onSuccess();
    } catch (err) { toast(err.message, 'error'); }
  });
}

// ── ALERTS PAGE ───────────────────────────────────────────────────────────────
async function renderAlerts(container) {
  container.innerHTML = `
    <div class="page-header">
      <h1 class="page-title">Alerts</h1>
      <button class="btn btn-primary btn-xs" id="btn-add-alert">+ New Alert</button>
    </div>
    <div id="alert-form-wrap" style="display:none"></div>
    <div id="alerts-list">${skelRows(4)}</div>
    <div class="section-title" style="margin-top:24px">Recent Events</div>
    <div id="alert-events">${skelRows(3)}</div>
  `;

  document.getElementById('btn-add-alert')?.addEventListener('click', () => {
    const fw = document.getElementById('alert-form-wrap');
    fw.style.display = fw.style.display === 'none' ? 'block' : 'none';
    if (fw.style.display === 'block') renderAlertForm(fw, () => loadAlerts());
  });

  async function loadAlerts() {
    const [alerts, events] = await Promise.allSettled([
      api.get('/api/alerts'),
      api.get('/api/alerts/events?limit=20'),
    ]);

    const listEl = document.getElementById('alerts-list');
    if (alerts.status === 'fulfilled') {
      if (!alerts.value.length) {
        listEl.innerHTML = `<div class="empty-state"><div class="empty-state-icon">🔔</div>
          <h3>No alerts</h3><p>Click "+ New Alert" to set price triggers.</p></div>`;
      } else {
        listEl.innerHTML = `
          <div class="table-wrap">
            <table class="data-table">
              <thead><tr><th>Ticker</th><th>Kind</th><th class="num">Threshold</th>
                <th>Direction</th><th>Last Triggered</th><th>Enabled</th><th></th></tr></thead>
              <tbody>
                ${alerts.value.map(a => `
                  <tr class="${a.is_enabled ? 'alert-row-enabled' : 'alert-row-disabled'}">
                    <td><strong>${a.ticker}</strong></td>
                    <td><span class="badge badge-accent">${a.kind}</span></td>
                    <td class="num">${fmt.num(a.threshold, 4)}</td>
                    <td>${a.direction === 'above' ? '▲ Above' : '▼ Below'}</td>
                    <td class="muted">${a.last_triggered_at ? fmt.date(a.last_triggered_at) : 'Never'}</td>
                    <td>
                      <label class="toggle">
                        <input type="checkbox" ${a.is_enabled ? 'checked' : ''} data-toggle-alert="${a.id}"/>
                        <span class="toggle-track"><span class="toggle-thumb"></span></span>
                      </label>
                    </td>
                    <td class="actions">
                      <button class="btn btn-ghost btn-xs" data-del-alert="${a.id}">✕</button>
                    </td>
                  </tr>
                `).join('')}
              </tbody>
            </table>
          </div>
        `;

        listEl.addEventListener('change', async (e) => {
          const toggle = e.target.closest('[data-toggle-alert]');
          if (!toggle) return;
          try {
            await api.put(`/api/alerts/${toggle.dataset.toggleAlert}`, { is_enabled: toggle.checked });
            toast(`Alert ${toggle.checked ? 'enabled' : 'disabled'}`, 'success');
          } catch (err) { toast(err.message, 'error'); toggle.checked = !toggle.checked; }
        });

        listEl.addEventListener('click', async (e) => {
          const del = e.target.closest('[data-del-alert]');
          if (!del) return;
          if (!confirm('Delete this alert?')) return;
          try { await api.delete(`/api/alerts/${del.dataset.delAlert}`); toast('Deleted', 'success'); loadAlerts(); }
          catch (err) { toast(err.message, 'error'); }
        });
      }
    }

    const evEl = document.getElementById('alert-events');
    if (events.status === 'fulfilled') {
      evEl.innerHTML = events.value.length ? `
        <div class="table-wrap">
          <table class="data-table">
            <thead><tr><th>Time</th><th>Ticker</th><th>Message</th></tr></thead>
            <tbody>
              ${events.value.map(ev => `<tr>
                <td class="muted">${fmt.date(ev.ts)}</td>
                <td><strong>${ev.ticker}</strong></td>
                <td>${escHtml(ev.message || '')}</td>
              </tr>`).join('')}
            </tbody>
          </table>
        </div>
      ` : `<p class="muted" style="padding:16px">No alert events yet.</p>`;
    }
  }

  await loadAlerts();
}

function renderAlertForm(container, onSuccess) {
  container.innerHTML = `
    <div class="card" style="margin-bottom:16px;max-width:500px">
      <div style="font-weight:700;margin-bottom:12px">Create Alert</div>
      <form id="alert-form">
        <div class="form-row">
          <div class="form-group">
            <label class="form-label">Ticker</label>
            <input class="form-control" name="ticker" required placeholder="e.g. AAPL"/>
          </div>
          <div class="form-group">
            <label class="form-label">Kind</label>
            <select class="form-control" name="kind">
              <option value="price">Price</option>
              <option value="change_pct">Change %</option>
              <option value="drawdown">Drawdown %</option>
            </select>
          </div>
        </div>
        <div class="form-row">
          <div class="form-group">
            <label class="form-label">Direction</label>
            <select class="form-control" name="direction">
              <option value="above">▲ Above</option>
              <option value="below">▼ Below</option>
            </select>
          </div>
          <div class="form-group">
            <label class="form-label">Threshold</label>
            <input class="form-control" name="threshold" type="number" step="any" required placeholder="0"/>
          </div>
        </div>
        <div style="display:flex;gap:8px">
          <button type="submit" class="btn btn-primary btn-xs">Create</button>
          <button type="button" class="btn btn-xs" id="cancel-alert-form">Cancel</button>
        </div>
      </form>
    </div>
  `;

  document.getElementById('cancel-alert-form')?.addEventListener('click', () => {
    container.style.display = 'none';
  });

  document.getElementById('alert-form')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const data = Object.fromEntries(fd.entries());
    data.threshold = +data.threshold;
    try {
      await api.post('/api/alerts', data);
      toast('Alert created', 'success');
      container.style.display = 'none';
      onSuccess();
    } catch (err) { toast(err.message, 'error'); }
  });
}

// ── SETTINGS PAGE ─────────────────────────────────────────────────────────────
async function renderSettings(container) {
  container.innerHTML = `
    <div class="page-header"><h1 class="page-title">Settings</h1></div>
    <div style="max-width:520px">
      <div class="card" style="margin-bottom:16px" id="settings-card">${skelLines(3)}</div>
      <div class="card" id="pw-card">
        <div style="font-weight:700;margin-bottom:12px">Change Password</div>
        <form id="pw-form">
          <div class="form-group"><label class="form-label">Current Password</label>
            <input class="form-control" name="current_password" type="password" required/></div>
          <div class="form-group"><label class="form-label">New Password</label>
            <input class="form-control" name="new_password" type="password" required/></div>
          <button type="submit" class="btn btn-primary btn-xs">Update Password</button>
        </form>
      </div>
    </div>
  `;

  document.getElementById('pw-form')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    try {
      await api.post('/api/auth/change-password', Object.fromEntries(fd.entries()));
      toast('Password updated', 'success');
      e.target.reset();
    } catch (err) { toast(err.message, 'error'); }
  });

  try {
    const s = await api.get('/api/settings');
    document.getElementById('settings-card').innerHTML = `
      <div style="font-weight:700;margin-bottom:14px">Preferences</div>
      <form id="settings-form">
        <div class="form-group">
          <label class="form-label">Theme</label>
          <select class="form-control" name="theme" style="max-width:200px">
            <option value="dark" ${s.theme === 'dark' ? 'selected' : ''}>Dark</option>
            <option value="light" ${s.theme === 'light' ? 'selected' : ''}>Light</option>
          </select>
        </div>
        <div class="form-group">
          <label class="form-label">Dashboard Refresh Interval (seconds)</label>
          <input class="form-control" name="refresh_interval_sec" type="number" min="10" max="3600"
                 value="${s.refresh_interval_sec}" style="max-width:200px"/>
        </div>
        <div class="form-group">
          <label class="form-label">Default Currency</label>
          <select class="form-control" name="default_currency" style="max-width:200px">
            <option value="EUR" ${s.default_currency === 'EUR' ? 'selected' : ''}>EUR €</option>
            <option value="USD" ${s.default_currency === 'USD' ? 'selected' : ''}>USD $</option>
            <option value="GBP" ${s.default_currency === 'GBP' ? 'selected' : ''}>GBP £</option>
          </select>
        </div>
        <button type="submit" class="btn btn-primary btn-xs">Save Settings</button>
      </form>
    `;

    document.getElementById('settings-form')?.addEventListener('submit', async (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      const data = Object.fromEntries(fd.entries());
      data.refresh_interval_sec = +data.refresh_interval_sec;
      try {
        const updated = await api.put('/api/settings', data);
        applyTheme(updated.theme);
        toast('Settings saved', 'success');
      } catch (err) { toast(err.message, 'error'); }
    });
  } catch (e) {
    document.getElementById('settings-card').innerHTML = `<span class="neg">${e.message}</span>`;
  }
}

// ── DEBUG PAGE (admin only) ───────────────────────────────────────────────────
async function renderDebug(container) {
  container.innerHTML = `
    <div class="page-header"><h1 class="page-title">Debug — Cache Stats</h1></div>
    <div id="debug-content">${skelLines(5)}</div>
  `;
  try {
    const stats = await api.get('/api/debug/cache-stats');
    document.getElementById('debug-content').innerHTML = `
      <div class="grid-4" style="margin-bottom:20px">
        <div class="metric-card"><div class="metric-label">Total Fetches</div><div class="metric-value">${stats.total_fetches}</div></div>
        <div class="metric-card"><div class="metric-label">Cache Hits</div><div class="metric-value pos">${stats.cache_hits}</div></div>
        <div class="metric-card"><div class="metric-label">Hit Ratio</div><div class="metric-value">${(stats.hit_ratio * 100).toFixed(1)}%</div></div>
        <div class="metric-card"><div class="metric-label">Avg Fetch ms</div><div class="metric-value">${stats.avg_fetch_ms}</div></div>
      </div>
      <div class="card">
        <div style="font-weight:700;margin-bottom:10px">By Source</div>
        <table class="data-table">
          <thead><tr><th>Source</th><th class="num">Count</th></tr></thead>
          <tbody>${stats.by_source.map(r => `<tr><td>${r.source}</td><td class="num">${r.count}</td></tr>`).join('')}</tbody>
        </table>
      </div>
    `;
  } catch (e) { document.getElementById('debug-content').innerHTML = `<span class="neg">${e.message}</span>`; }
}

// ── Utils ─────────────────────────────────────────────────────────────────────
function escHtml(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// Make navigate work from inline onclick handlers
window.navigate = (page, ticker) => {
  if (ticker) location.hash = `${page}/${ticker}`;
  else location.hash = page;
};

// ── Sidebar navigation ────────────────────────────────────────────────────────
document.getElementById('sidebar')?.addEventListener('click', (e) => {
  const btn = e.target.closest('.nav-item[data-page]');
  if (btn) navigate(btn.dataset.page);
});

// ── Keyboard navigation ───────────────────────────────────────────────────────
document.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' || e.key === ' ') {
    const el = document.activeElement;
    if (el?.classList.contains('nav-item')) { e.preventDefault(); navigate(el.dataset.page); }
  }
});

// ── Init ──────────────────────────────────────────────────────────────────────
window.addEventListener('hashchange', () => {
  if (state.user) router();
});

(async () => {
  const authed = await checkAuth();
  if (authed) {
    showApp();
  } else {
    showLogin();
  }
})();
