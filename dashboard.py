"""
dashboard.py — Dashboard HTML templates (desktop + mobile).

Exports:
  LANDING_HTML  — desktop-optimized portfolio dashboard
  DASHBOARD_HTML — mobile-friendly portfolio dashboard
"""

LANDING_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>DCA Dynamic — Portfolio Dashboard</title>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
      background: #0a0805;
      color: #e2e8f0;
      min-height: 100vh;
    }

    /* ── Navigation ── */
    nav {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 16px 40px;
      border-bottom: 1px solid rgba(255,255,255,0.06);
      backdrop-filter: blur(12px);
      position: sticky;
      top: 0;
      z-index: 10;
      background: rgba(12,10,26,0.85);
    }
    .nav-brand {
      display: flex;
      align-items: center;
      gap: 10px;
      font-size: 16px;
      font-weight: 700;
      letter-spacing: -0.02em;
    }
    .nav-brand .icon {
      width: 36px; height: 36px; border-radius: 10px;
      background: linear-gradient(135deg, #f59e0b, #b45309);
      display: flex; align-items: center; justify-content: center;
      font-size: 20px;
      box-shadow: 0 0 16px rgba(245,158,11,0.25);
    }
    .nav-right {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .nav-pills {
      display: flex;
      gap: 8px;
    }
    .pill {
      display: inline-flex;
      align-items: center;
      gap: 5px;
      font-size: 12px;
      padding: 5px 12px;
      border-radius: 99px;
      font-weight: 600;
      border: 1px solid transparent;
    }
    .pill.green  { background: rgba(52,211,153,0.12); color: #34d399; border-color: rgba(52,211,153,0.2); }
    .pill.red    { background: rgba(248,113,113,0.12); color: #f87171; border-color: rgba(248,113,113,0.2); }
    .pill.yellow { background: rgba(251,191,36,0.12);  color: #fbbf24; border-color: rgba(251,191,36,0.2); }
    .pill.amber  { background: rgba(245,158,11,0.12);  color: #f59e0b; border-color: rgba(245,158,11,0.2); }
    .pill.muted  { background: rgba(255,255,255,0.04); color: #64748b; border-color: rgba(255,255,255,0.06); }
    #refresh-btn {
      background: rgba(255,255,255,0.05);
      border: 1px solid rgba(255,255,255,0.08);
      color: #94a3b8;
      padding: 7px 14px;
      border-radius: 8px;
      font-size: 13px;
      font-weight: 500;
      cursor: pointer;
      transition: all 0.15s;
    }
    #refresh-btn:hover { background: rgba(255,255,255,0.1); color: #e2e8f0; }

    /* ── Layout ── */
    .container { max-width: 1280px; margin: 0 auto; padding: 28px 40px 60px; }

    .hero {
      display: grid;
      grid-template-columns: 1fr 1fr 1fr 1fr;
      gap: 16px;
      margin-bottom: 24px;
    }

    .grid-2 {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16px;
      margin-bottom: 16px;
    }

    .grid-3 {
      display: grid;
      grid-template-columns: 2fr 1fr;
      gap: 16px;
      margin-bottom: 16px;
    }

    /* ── Cards ── */
    .card {
      background: rgba(255,255,255,0.03);
      border: 1px solid rgba(255,255,255,0.06);
      border-radius: 16px;
      padding: 24px;
      transition: border-color 0.2s;
    }
    .card:hover { border-color: rgba(255,255,255,0.1); }

    .card-title {
      font-size: 11px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: #475569;
      margin-bottom: 12px;
    }

    /* ── Stat cards (hero) ── */
    .stat-card .stat-value {
      font-size: 28px;
      font-weight: 800;
      letter-spacing: -0.03em;
      margin-bottom: 4px;
    }
    .stat-card .stat-sub {
      font-size: 12px;
      color: #64748b;
    }
    .stat-card .stat-value.green { color: #34d399; }
    .stat-card .stat-value.red   { color: #f87171; }
    .stat-card.amber-card {
      background: rgba(245,158,11,0.06);
      border-color: rgba(245,158,11,0.15);
    }
    .stat-card.green-card {
      background: rgba(52,211,153,0.05);
      border-color: rgba(52,211,153,0.15);
    }
    .stat-card .stat-value { color: #fef3c7; }
    .stat-card .stat-percent {
      font-size: 11px;
      margin-top: 2px;
    }

    /* ── Allocation bars ── */
    .allocation-row {
      display: flex;
      align-items: center;
      gap: 12px;
      margin-bottom: 12px;
    }
    .alloc-symbol {
      font-weight: 700;
      width: 48px;
      font-size: 14px;
      color: #e2e8f0;
    }
    .alloc-bar-wrap {
      flex: 1;
      background: rgba(255,255,255,0.04);
      border-radius: 99px;
      height: 10px;
      overflow: hidden;
    }
    .alloc-bar {
      height: 100%;
      border-radius: 99px;
      transition: width 0.6s cubic-bezier(0.22,1,0.36,1);
    }
    .alloc-pct { font-size: 13px; color: #94a3b8; width: 42px; text-align: right; font-weight: 500; }
    .alloc-target { font-size: 12px; color: #475569; width: 42px; text-align: right; }
    .drift-badge {
      font-size: 12px;
      font-weight: 600;
      width: 54px;
      text-align: right;
      padding: 2px 8px;
      border-radius: 6px;
    }
    .drift-badge.over  { color: #f87171; background: rgba(248,113,113,0.1); }
    .drift-badge.under { color: #60a5fa; background: rgba(96,165,250,0.1); }
    .drift-badge.on    { color: #34d399; background: rgba(52,211,153,0.1); }

    /* ── Charts ── */
    .chart-wrap { position: relative; height: 260px; }
    .chart-wrap-sm { position: relative; height: 220px; }

    /* ── Contribution history ── */
    .contribution-list { list-style: none; }
    .contribution-item {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      padding: 14px 0;
      border-bottom: 1px solid rgba(255,255,255,0.04);
      gap: 12px;
    }
    .contribution-item:last-child { border-bottom: none; }
    .contrib-left { flex: 1; }
    .contrib-date { font-size: 12px; color: #475569; margin-bottom: 3px; }
    .contrib-alloc { font-size: 13px; font-weight: 500; }
    .contrib-alloc span { color: #f59e0b; font-weight: 600; }
    .contrib-reasoning {
      font-size: 12px;
      color: #475569;
      margin-top: 4px;
      line-height: 1.5;
      max-width: 500px;
    }
    .contrib-right { font-size: 15px; font-weight: 700; color: #e2e8f0; white-space: nowrap; }

    /* ── Event log ── */
    .event-list { list-style: none; max-height: 400px; overflow-y: auto; }
    .event-list::-webkit-scrollbar { width: 4px; }
    .event-list::-webkit-scrollbar-thumb { background: #1e2035; border-radius: 4px; }
    .event-item {
      display: flex;
      gap: 10px;
      padding: 10px 0;
      border-bottom: 1px solid rgba(255,255,255,0.03);
      font-size: 12px;
      align-items: flex-start;
    }
    .event-item:last-child { border-bottom: none; }
    .event-dot {
      width: 8px; height: 8px; border-radius: 50%;
      margin-top: 4px; flex-shrink: 0;
    }
    .event-dot.green  { background: #34d399; }
    .event-dot.red    { background: #f87171; }
    .event-dot.blue   { background: #60a5fa; }
    .event-dot.purple { background: #a78bfa; }
    .event-dot.orange { background: #f97316; }
    .event-dot.gray   { background: #334155; }
    .event-time { color: #475569; flex-shrink: 0; font-variant-numeric: tabular-nums; }
    .event-text { color: #94a3b8; line-height: 1.4; }

    .loading { color: #334155; font-size: 13px; text-align: center; padding: 28px; }

    #last-updated {
      font-size: 11px;
      color: #334155;
      text-align: center;
      margin-top: 12px;
    }

    /* ── Claude reasoning callout ── */
    .reasoning-card {
      background: rgba(245,158,11,0.07);
      border: 1px solid rgba(245,158,11,0.18);
    }
    .reasoning-card .card-title { color: #92400e; }
    .reasoning-text {
      color: #fcd34d;
      font-size: 13px;
      font-style: italic;
      line-height: 1.6;
    }
    .reasoning-meta { font-size: 10px; color: #78716c; margin-top: 8px; }

    /* ── Plaid status panel ── */
    .plaid-rows { display: flex; flex-direction: column; gap: 9px; margin-top: 4px; }
    .plaid-row { display: flex; align-items: center; gap: 8px; font-size: 11px; }
    .plaid-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
    .plaid-dot.green  { background: #34d399; }
    .plaid-dot.amber  { background: #f59e0b; }
    .plaid-dot.red    { background: #f87171; }
    .plaid-label { color: #94a3b8; }
    .plaid-payday-label { font-size: 9px; color: #78716c; text-transform: uppercase; letter-spacing: 0.06em; margin-top: 6px; }
    .plaid-payday-value { font-size: 13px; font-weight: 700; color: #fef3c7; margin-top: 2px; }

    /* ── 2fr/1fr grid for reasoning + plaid ── */
    .grid-plaid {
      display: grid;
      grid-template-columns: 2fr 1fr;
      gap: 16px;
      margin-bottom: 16px;
    }

    /* ── Responsive ── */
    @media (max-width: 900px) {
      .hero { grid-template-columns: 1fr 1fr; }
      .grid-2, .grid-3 { grid-template-columns: 1fr; }
      .grid-plaid { grid-template-columns: 1fr; }
      .container { padding: 20px 16px 40px; }
      nav { padding: 12px 16px; }
    }
  </style>
</head>
<body>

<nav>
  <div class="nav-brand">
    <div class="icon">◈</div>
    <div>
      <div>DCA DYNAMIC</div>
      <div style="font-size:10px;font-weight:400;color:#78716c;letter-spacing:0.03em;margin-top:1px;">Automated wealth engine</div>
    </div>
  </div>
  <div class="nav-right">
    <div class="nav-pills" id="status-bar">
      <span class="pill muted">Loading…</span>
    </div>
    <button id="refresh-btn" onclick="loadAll()">↻ Refresh</button>
  </div>
</nav>

<div class="container">

  <!-- ── Hero stats ── -->
  <div class="hero" id="hero">
    <div class="card stat-card amber-card"><div class="card-title">Portfolio value</div><div class="stat-value" id="s-total">—</div><div class="stat-sub">Total assets</div></div>
    <div class="card stat-card"><div class="card-title">Cash available</div><div class="stat-value" id="s-cash">—</div><div class="stat-sub">Uninvested</div></div>
    <div class="card stat-card"><div class="card-title">Invested</div><div class="stat-value" id="s-invested">—</div><div class="stat-sub">In positions</div></div>
    <div class="card stat-card" id="pl-card"><div class="card-title">Unrealised P&amp;L</div><div class="stat-value" id="s-pl">—</div><div class="stat-percent" id="s-pl-pct"></div></div>
  </div>

  <!-- ── Claude reasoning + Plaid status ── -->
  <div class="grid-plaid">
    <div class="card reasoning-card">
      <div class="card-title">Claude's last allocation rationale</div>
      <div class="reasoning-text" id="reasoning-text">—</div>
      <div class="reasoning-meta" id="reasoning-meta"></div>
    </div>
    <div class="card">
      <div class="card-title">Paycheck automation</div>
      <div class="plaid-rows" id="plaid-rows">
        <div class="loading">…</div>
      </div>
      <div class="plaid-payday-label">Next expected payday</div>
      <div class="plaid-payday-value" id="plaid-payday">—</div>
    </div>
  </div>

  <!-- ── Charts row ── -->
  <div class="grid-2">
    <div class="card">
      <div class="card-title">Portfolio value over time</div>
      <div class="chart-wrap"><canvas id="valueChart"></canvas></div>
    </div>
    <div class="card">
      <div class="card-title">Allocation drift history</div>
      <div class="chart-wrap"><canvas id="driftChart"></canvas></div>
    </div>
  </div>

  <!-- ── Allocation + Activity ── -->
  <div class="grid-3">
    <div class="card">
      <div class="card-title">Current allocation vs target</div>
      <div id="allocation-rows"><div class="loading">…</div></div>
    </div>
    <div class="card">
      <div class="card-title">Recent activity</div>
      <ul class="event-list" id="event-log"><li class="loading">…</li></ul>
    </div>
  </div>

  <!-- ── Target Weight History ── -->
  <div class="card">
    <div class="card-title">Target weight history (dynamic adjustments)</div>
    <div class="chart-wrap"><canvas id="targetChart"></canvas></div>
  </div>

  <!-- ── Contributions ── -->
  <div class="card">
    <div class="card-title">Contribution history</div>
    <ul class="contribution-list" id="contributions"><li class="loading">…</li></ul>
  </div>

  <div id="last-updated"></div>
</div>

<script>
const COLORS = {
  VTI:  '#f59e0b', VXUS: '#34d399', AVUV: '#60a5fa', BND: '#f87171',
  default: ['#f59e0b','#34d399','#60a5fa','#f87171','#d97706','#fbbf24'],
};
const BASE_TARGETS = { VTI: 0.50, VXUS: 0.35, AVUV: 0.10, BND: 0.05 };
function colorFor(sym, i) { return COLORS[sym] || COLORS.default[i % COLORS.default.length]; }

let valueChart = null, driftChart = null, targetChart = null;

Chart.defaults.color = '#475569';
Chart.defaults.borderColor = 'rgba(255,255,255,0.04)';
Chart.defaults.font.family = "'Inter', -apple-system, sans-serif";

function mkValueChart(labels, values) {
  const ctx = document.getElementById('valueChart');
  if (valueChart) valueChart.destroy();
  const grad = ctx.getContext('2d').createLinearGradient(0,0,0,260);
  grad.addColorStop(0, 'rgba(245,158,11,0.25)');
  grad.addColorStop(1, 'rgba(245,158,11,0)');
  valueChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        data: values, borderColor: '#f59e0b', backgroundColor: grad,
        borderWidth: 2, fill: true, tension: 0.4,
        pointRadius: values.length < 20 ? 3 : 0,
        pointBackgroundColor: '#f59e0b', pointBorderWidth: 0,
      }],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { display: false }, ticks: { maxTicksLimit: 8, maxRotation: 0, font: { size: 11 } } },
        y: { grid: { color: 'rgba(255,255,255,0.03)' }, ticks: { callback: v => '$' + (v >= 1000 ? (v/1000).toFixed(1)+'k' : v), font: { size: 11 } } },
      },
    },
  });
}

function mkDriftChart(labels, symbolData) {
  const ctx = document.getElementById('driftChart');
  if (driftChart) driftChart.destroy();
  const symbols = Object.keys(symbolData);
  driftChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: symbols.map((sym, i) => ({
        label: sym, data: symbolData[sym],
        borderColor: colorFor(sym, i), borderWidth: 2,
        fill: false, tension: 0.4, pointRadius: 0,
      })),
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { position: 'bottom', labels: { boxWidth: 10, padding: 14, font: { size: 11 } } } },
      scales: {
        x: { grid: { display: false }, ticks: { maxTicksLimit: 6, maxRotation: 0, font: { size: 11 } } },
        y: { grid: { color: 'rgba(255,255,255,0.03)' }, ticks: { callback: v => (v*100).toFixed(0)+'%', font: { size: 11 } } },
      },
    },
  });
}

function mkTargetChart(labels, symbolData) {
  const ctx = document.getElementById('targetChart');
  if (targetChart) targetChart.destroy();
  const symbols = Object.keys(symbolData);
  const datasets = [];

  // Solid lines for actual adjusted targets
  symbols.forEach((sym, i) => {
    datasets.push({
      label: sym, data: symbolData[sym],
      borderColor: colorFor(sym, i), borderWidth: 2,
      fill: false, tension: 0.3, pointRadius: 3,
      pointBackgroundColor: colorFor(sym, i),
    });
  });

  // Dashed lines for base targets
  symbols.forEach((sym, i) => {
    const baseVal = BASE_TARGETS[sym] || 0;
    datasets.push({
      label: sym + ' base',
      data: labels.map(() => baseVal),
      borderColor: colorFor(sym, i),
      borderWidth: 1,
      borderDash: [6, 4],
      fill: false,
      pointRadius: 0,
    });
  });

  targetChart = new Chart(ctx, {
    type: 'line',
    data: { labels, datasets },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: {
          position: 'bottom',
          labels: {
            boxWidth: 10, padding: 14, font: { size: 11 },
            filter: item => !item.text.includes('base'),
          },
        },
      },
      scales: {
        x: { grid: { display: false }, ticks: { maxTicksLimit: 8, maxRotation: 0, font: { size: 11 } } },
        y: {
          grid: { color: 'rgba(255,255,255,0.03)' },
          ticks: { callback: v => (v*100).toFixed(0)+'%', font: { size: 11 } },
          min: 0, max: 0.65,
        },
      },
    },
  });
}

function fmt(n) { return '$' + Number(n).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2}); }
function fmtTs(ts) {
  const d = new Date(ts);
  return d.toLocaleDateString('en-US',{month:'short',day:'numeric'}) + ' ' + d.toLocaleTimeString('en-US',{hour:'numeric',minute:'2-digit'});
}
function fmtDateShort(ts) { return new Date(ts).toLocaleDateString('en-US',{month:'short',day:'numeric'}); }

function renderPortfolio(p, health) {
  const bar = document.getElementById('status-bar');
  const marketPill = health.market_open
    ? '<span class="pill green">● Market open</span>'
    : health.trading_day
      ? '<span class="pill yellow">● After hours</span>'
      : '<span class="pill red">● Market closed</span>';
  const nextPill = (health.next_contribution && health.next_contribution !== 'event_driven')
    ? `<span class="pill muted">Next run: ${fmtTs(health.next_contribution)}</span>` : '';
  bar.innerHTML = marketPill
    + '<span class="pill amber">Live</span>'
    + '<span class="pill amber">Plaid</span>'
    + nextPill;

  const total = p.total_value;
  const cash = p.cash_available;
  const invested = total - cash;
  const pl = Object.values(p.holdings).reduce((s,h)=>s+h.unrealized_pl,0);
  const plClass = pl >= 0 ? 'green' : 'red';
  const invClass = invested >= 0 ? '' : 'red';

  document.getElementById('s-total').textContent = fmt(total);
  document.getElementById('s-cash').textContent = fmt(cash);

  const sInvested = document.getElementById('s-invested');
  sInvested.textContent = fmt(invested);
  sInvested.className = 'stat-value ' + invClass;

  const sPl = document.getElementById('s-pl');
  sPl.textContent = (pl >= 0 ? '+' : '') + fmt(pl);
  sPl.className = 'stat-value ' + plClass;

  const plCard = document.getElementById('pl-card');
  plCard.className = 'card stat-card ' + (pl >= 0 ? 'green-card' : '');

  const costBasis = total - pl;
  const plPct = costBasis > 0 ? (pl / costBasis * 100).toFixed(1) : '0.0';
  const sPct = document.getElementById('s-pl-pct');
  sPct.textContent = (pl >= 0 ? '+' : '') + plPct + '% all time';
  sPct.style.color = pl >= 0 ? '#34d399' : '#f87171';

  const symbols = Object.keys(p.target_allocation);
  document.getElementById('allocation-rows').innerHTML = symbols.map((sym, i) => {
    const current = p.holdings[sym]?.weight ?? 0;
    const target = p.target_allocation[sym];
    const drift = current - target;
    const dc = Math.abs(drift) < 0.005 ? 'on' : drift > 0 ? 'over' : 'under';
    const ds = drift > 0 ? '+' : '';
    const color = colorFor(sym, i);
    return `
      <div class="allocation-row">
        <div class="alloc-symbol">${sym}</div>
        <div class="alloc-bar-wrap">
          <div class="alloc-bar" style="width:${Math.min(current*100,100)}%;background:${color}"></div>
        </div>
        <div class="alloc-pct">${(current*100).toFixed(1)}%</div>
        <div class="alloc-target">/ ${(target*100).toFixed(0)}%</div>
        <div class="drift-badge ${dc}">${ds}${(drift*100).toFixed(1)}%</div>
      </div>`;
  }).join('') || '<div class="loading">No positions yet</div>';
}

function renderHistory(entries) {
  const snapshots = entries.filter(e => e.event === 'portfolio_snapshot' && e.total_value > 0);
  const byDay = {};
  snapshots.forEach(s => { byDay[s.timestamp.slice(0,10)] = s; });
  const days = Object.values(byDay).sort((a,b) => a.timestamp.localeCompare(b.timestamp));

  if (days.length >= 2) {
    mkValueChart(days.map(d => fmtDateShort(d.timestamp)), days.map(d => d.total_value));
    const allSymbols = [...new Set(days.flatMap(d => Object.keys(d.drift_from_target || {})))];
    const driftData = {};
    allSymbols.forEach(sym => { driftData[sym] = days.map(d => d.drift_from_target?.[sym] ?? null); });
    mkDriftChart(days.map(d => fmtDateShort(d.timestamp)), driftData);
  } else {
    const vc = document.getElementById('valueChart');
    if (vc) vc.parentElement.innerHTML = '<div class="loading">Not enough data yet — charts appear after a few contribution cycles.</div>';
    const dc = document.getElementById('driftChart');
    if (dc) dc.parentElement.innerHTML = '<div class="loading">Not enough data yet.</div>';
  }

  // Target weight history chart
  const dynamicEntries = entries.filter(e => e.event === 'dynamic_allocation_proposed' && e.adjusted_targets);
  if (dynamicEntries.length >= 2) {
    const sorted = [...dynamicEntries].reverse();
    const targetLabels = sorted.map(e => fmtDateShort(e.timestamp));
    const targetSymbols = Object.keys(BASE_TARGETS);
    const targetData = {};
    targetSymbols.forEach(sym => {
      targetData[sym] = sorted.map(e => e.adjusted_targets?.[sym] ?? BASE_TARGETS[sym]);
    });
    mkTargetChart(targetLabels, targetData);
  } else {
    const tc = document.getElementById('targetChart');
    if (tc) tc.parentElement.innerHTML = '<div class="loading">Target weight history will appear after multiple dynamic allocations.</div>';
  }

  // Contributions
  const proposals = entries.filter(e => e.event === 'dynamic_allocation_proposed').slice(0, 10);
  const ul = document.getElementById('contributions');
  if (!proposals.length) {
    ul.innerHTML = '<li class="loading">No contributions yet — the bot runs on the 1st and 16th.</li>';
  } else {
    ul.innerHTML = proposals.map(p => {
      const parts = Object.entries(p.allocations).map(([sym, amt]) => `<span>${sym} ${fmt(amt)}</span>`).join('&nbsp;&nbsp;');
      const reason = p.allocation_reasoning || p.reasoning || '';
      return `<li class="contribution-item">
        <div class="contrib-left">
          <div class="contrib-date">${fmtTs(p.timestamp)}</div>
          <div class="contrib-alloc">${parts}</div>
          <div class="contrib-reasoning">${reason}</div>
        </div>
        <div class="contrib-right">${fmt(p.new_cash)}</div>
      </li>`;
    }).join('');
  }

  // Event log
  const eventDot = {
    portfolio_snapshot: 'gray', dynamic_allocation_proposed: 'purple',
    fixed_counterfactual_logged: 'orange', orders_placed: 'green',
    market_data_fetched: 'blue', contribution_error: 'red',
    ai_allocation_proposed: 'purple',
  };
  const eventLabel = e => {
    switch(e.event) {
      case 'portfolio_snapshot':             return `Snapshot — ${fmt(e.total_value)}`;
      case 'dynamic_allocation_proposed':    return `Dynamic: ${Object.entries(e.allocations).map(([s,a])=>s+' '+fmt(a)).join(', ')}`;
      case 'ai_allocation_proposed':         return `AI proposed ${Object.entries(e.allocations).map(([s,a])=>s+' '+fmt(a)).join(', ')}`;
      case 'fixed_counterfactual_logged':    return `Fixed counterfactual: ${Object.entries(e.allocations).map(([s,a])=>s+' '+fmt(a)).join(', ')}`;
      case 'orders_placed':                  return `Orders placed — ${e.receipts?.map(r=>r.symbol).join(', ')} (${e.strategy || 'dynamic'})`;
      case 'market_data_fetched':            return 'Market data fetched';
      case 'contribution_error':             return `Error: ${e.error}`;
      default:                               return e.event.replace(/_/g,' ');
    }
  };
  document.getElementById('event-log').innerHTML = entries.slice(0, 25).map(e => `
    <li class="event-item">
      <div class="event-dot ${eventDot[e.event] || 'gray'}"></div>
      <div class="event-time">${fmtTs(e.timestamp)}</div>
      <div class="event-text">${eventLabel(e)}</div>
    </li>`).join('');
}

function renderReasoning(entries) {
  const latest = entries.find(e => e.event === 'dynamic_allocation_proposed');
  const textEl = document.getElementById('reasoning-text');
  const metaEl = document.getElementById('reasoning-meta');
  if (!latest) {
    textEl.textContent = 'No allocation reasoning yet — appears after the first contribution cycle.';
    textEl.style.fontStyle = 'normal';
    textEl.style.color = '#475569';
    metaEl.textContent = '';
    return;
  }
  const reason = latest.allocation_reasoning || latest.reasoning || '';
  textEl.textContent = reason ? `"${reason}"` : '(No reasoning recorded for this cycle.)';
  metaEl.textContent = fmtTs(latest.timestamp) + ' · Dynamic strategy';
}

function renderPlaid(health) {
  const connected = health.plaid_institution != null;
  const institution = health.plaid_institution || '';
  const mask = health.plaid_account_mask || '';
  const rows = document.getElementById('plaid-rows');

  if (connected) {
    rows.innerHTML = `
      <div class="plaid-row">
        <div class="plaid-dot green"></div>
        <span class="plaid-label">${institution} ••${mask} connected</span>
      </div>
      <div class="plaid-row">
        <div class="plaid-dot amber"></div>
        <span class="plaid-label">Watching for deposit</span>
      </div>`;
  } else {
    rows.innerHTML = `
      <div class="plaid-row">
        <div class="plaid-dot red"></div>
        <span class="plaid-label">No account linked</span>
      </div>`;
  }

  const paydayEl = document.getElementById('plaid-payday');
  paydayEl.textContent = (health.next_contribution && health.next_contribution !== 'event_driven')
    ? fmtTs(health.next_contribution) : 'On next paycheck';
}

async function loadAll() {
  document.getElementById('refresh-btn').textContent = '↻ …';
  try {
    const [portfolio, health, audit] = await Promise.all([
      fetch('/portfolio').then(r => r.json()),
      fetch('/health').then(r => r.json()),
      fetch('/audit').then(r => r.json()),
    ]);
    renderPortfolio(portfolio, health);
    renderHistory(audit);
    renderReasoning(audit);
    renderPlaid(health);
    document.getElementById('last-updated').textContent =
      'Updated ' + new Date().toLocaleTimeString('en-US',{hour:'numeric',minute:'2-digit',second:'2-digit'});
  } catch(err) {
    document.getElementById('status-bar').innerHTML = `<span class="pill red">⚠ ${err.message}</span>`;
  }
  document.getElementById('refresh-btn').textContent = '↻ Refresh';
}

loadAll();
setInterval(loadAll, 60_000);
</script>
</body>
</html>"""


# ─────────────────────────────────────────────────────────────────────────────
# MOBILE DASHBOARD
# ─────────────────────────────────────────────────────────────────────────────

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>DCA Dynamic Portfolio</title>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      background: #0c0a1a;
      color: #e2e8f0;
      min-height: 100vh;
      padding: 16px;
    }

    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 20px;
    }
    header h1 { font-size: 18px; font-weight: 700; }
    #refresh-btn {
      background: #1e1e2e;
      border: 1px solid #2d2d3d;
      color: #a0aec0;
      padding: 6px 12px;
      border-radius: 8px;
      font-size: 13px;
      cursor: pointer;
    }
    #refresh-btn:hover { background: #2d2d3d; }

    .pill {
      display: inline-flex;
      align-items: center;
      gap: 5px;
      font-size: 12px;
      padding: 3px 10px;
      border-radius: 99px;
      font-weight: 600;
    }
    .pill.green  { background: #064e3b; color: #34d399; }
    .pill.red    { background: #450a0a; color: #f87171; }
    .pill.yellow { background: #451a03; color: #fbbf24; }
    .pill.purple { background: #2e1065; color: #a855f7; }

    .card {
      background: #1a1a2e;
      border: 1px solid #2d2d3d;
      border-radius: 16px;
      padding: 20px;
      margin-bottom: 14px;
    }
    .card-title {
      font-size: 11px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: .06em;
      color: #64748b;
      margin-bottom: 10px;
    }

    .stat-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
    }
    .stat .label { font-size: 11px; color: #64748b; margin-bottom: 2px; }
    .stat .value { font-size: 22px; font-weight: 700; }
    .stat .value.green { color: #34d399; }
    .stat .value.red   { color: #f87171; }

    .allocation-row {
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 10px;
    }
    .alloc-symbol { font-weight: 700; width: 42px; font-size: 14px; }
    .alloc-bar-wrap { flex: 1; background: #0f0f13; border-radius: 99px; height: 8px; overflow: hidden; }
    .alloc-bar { height: 100%; border-radius: 99px; transition: width .5s; }
    .alloc-pct { font-size: 13px; color: #94a3b8; width: 36px; text-align: right; }
    .alloc-target { font-size: 11px; color: #475569; width: 42px; text-align: right; }
    .drift-badge {
      font-size: 11px; font-weight: 600; width: 48px; text-align: right;
    }
    .drift-badge.over  { color: #f87171; }
    .drift-badge.under { color: #60a5fa; }
    .drift-badge.on    { color: #34d399; }

    .chart-wrap { position: relative; height: 200px; }
    .chart-wrap-sm { position: relative; height: 160px; }

    .contribution-list { list-style: none; }
    .contribution-item {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      padding: 12px 0;
      border-bottom: 1px solid #1e2035;
      gap: 8px;
    }
    .contribution-item:last-child { border-bottom: none; }
    .contrib-left { flex: 1; }
    .contrib-date { font-size: 12px; color: #64748b; margin-bottom: 2px; }
    .contrib-alloc { font-size: 13px; }
    .contrib-alloc span { color: #a78bfa; font-weight: 600; }
    .contrib-reasoning {
      font-size: 11px;
      color: #475569;
      margin-top: 3px;
      line-height: 1.4;
    }
    .contrib-right { font-size: 14px; font-weight: 700; color: #e2e8f0; white-space: nowrap; }

    .event-list { list-style: none; }
    .event-item {
      display: flex;
      gap: 10px;
      padding: 9px 0;
      border-bottom: 1px solid #1e2035;
      font-size: 12px;
      align-items: flex-start;
    }
    .event-item:last-child { border-bottom: none; }
    .event-dot {
      width: 8px; height: 8px; border-radius: 50%;
      margin-top: 3px; flex-shrink: 0;
    }
    .event-dot.green  { background: #34d399; }
    .event-dot.red    { background: #f87171; }
    .event-dot.blue   { background: #60a5fa; }
    .event-dot.purple { background: #a78bfa; }
    .event-dot.orange { background: #f97316; }
    .event-dot.gray   { background: #64748b; }
    .event-time { color: #475569; flex-shrink: 0; }
    .event-text { color: #94a3b8; line-height: 1.4; }

    .status-bar {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      margin-bottom: 16px;
    }

    .loading { color: #475569; font-size: 14px; text-align: center; padding: 24px; }
    .error   { color: #f87171; font-size: 13px; text-align: center; padding: 16px; }

    #last-updated { font-size: 11px; color: #475569; text-align: center; margin-top: 8px; }
  </style>
</head>
<body>

<header>
  <div>
    <h1>🧪 DCA Dynamic</h1>
  </div>
  <button id="refresh-btn" onclick="loadAll()">↻ Refresh</button>
</header>

<div class="status-bar" id="status-bar">
  <span class="loading">Loading…</span>
</div>

<!-- ── PORTFOLIO VALUE ── -->
<div class="card">
  <div class="card-title">Portfolio value</div>
  <div class="stat-grid" id="stats">
    <div class="loading">…</div>
  </div>
</div>

<!-- ── ALLOCATION ── -->
<div class="card">
  <div class="card-title">Current allocation vs target</div>
  <div id="allocation-rows"><div class="loading">…</div></div>
</div>

<!-- ── PORTFOLIO VALUE CHART ── -->
<div class="card">
  <div class="card-title">Portfolio value over time</div>
  <div class="chart-wrap"><canvas id="valueChart"></canvas></div>
</div>

<!-- ── ALLOCATION DRIFT CHART ── -->
<div class="card">
  <div class="card-title">Allocation drift history</div>
  <div class="chart-wrap-sm"><canvas id="driftChart"></canvas></div>
</div>

<!-- ── CONTRIBUTION HISTORY ── -->
<div class="card">
  <div class="card-title">Contributions</div>
  <ul class="contribution-list" id="contributions">
    <li class="loading">…</li>
  </ul>
</div>

<!-- ── EVENT LOG ── -->
<div class="card">
  <div class="card-title">Recent activity</div>
  <ul class="event-list" id="event-log">
    <li class="loading">…</li>
  </ul>
</div>

<div id="last-updated"></div>

<script>
const COLORS = {
  VTI:  '#818cf8', VXUS: '#34d399', AVUV: '#fbbf24', BND: '#f87171',
  default: ['#818cf8','#34d399','#fbbf24','#f87171','#60a5fa','#a78bfa'],
};
function colorFor(sym, i) {
  return COLORS[sym] || COLORS.default[i % COLORS.default.length];
}

let valueChart = null;
let driftChart = null;

Chart.defaults.color = '#64748b';
Chart.defaults.borderColor = '#1e2035';
Chart.defaults.font.family = "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif";

function mkValueChart(labels, values) {
  const ctx = document.getElementById('valueChart');
  if (valueChart) valueChart.destroy();

  const grad = ctx.getContext('2d').createLinearGradient(0,0,0,200);
  grad.addColorStop(0,  'rgba(129,140,248,0.3)');
  grad.addColorStop(1,  'rgba(129,140,248,0)');

  valueChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        data: values,
        borderColor: '#818cf8',
        backgroundColor: grad,
        borderWidth: 2,
        fill: true,
        tension: 0.4,
        pointRadius: values.length < 15 ? 4 : 0,
        pointBackgroundColor: '#818cf8',
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { display: false }, ticks: { maxTicksLimit: 6, maxRotation: 0 } },
        y: {
          grid: { color: '#1e2035' },
          ticks: {
            callback: v => '$' + (v >= 1000 ? (v/1000).toFixed(0)+'k' : v.toLocaleString()),
          },
        },
      },
    },
  });
}

function mkDriftChart(labels, symbolData) {
  const ctx = document.getElementById('driftChart');
  if (driftChart) driftChart.destroy();

  const symbols = Object.keys(symbolData);
  driftChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: symbols.map((sym, i) => ({
        label: sym,
        data: symbolData[sym],
        borderColor: colorFor(sym, i),
        borderWidth: 2,
        fill: false,
        tension: 0.4,
        pointRadius: 0,
      })),
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: 'bottom',
          labels: { boxWidth: 10, padding: 12, font: { size: 11 } },
        },
      },
      scales: {
        x: { grid: { display: false }, ticks: { maxTicksLimit: 5, maxRotation: 0 } },
        y: {
          grid: { color: '#1e2035' },
          ticks: { callback: v => (v * 100).toFixed(0) + '%' },
        },
      },
    },
  });
}

function fmt(n)  { return '$' + Number(n).toLocaleString('en-US', {minimumFractionDigits:2,maximumFractionDigits:2}); }
function fmtTs(ts) {
  const d = new Date(ts);
  return d.toLocaleDateString('en-US',{month:'short',day:'numeric'}) + ' '
       + d.toLocaleTimeString('en-US',{hour:'numeric',minute:'2-digit'});
}
function fmtDateShort(ts) {
  return new Date(ts).toLocaleDateString('en-US',{month:'short',day:'numeric'});
}

function renderPortfolio(p, health) {
  const bar = document.getElementById('status-bar');
  const marketPill = health.market_open
    ? '<span class="pill green">● Market open</span>'
    : health.trading_day
      ? '<span class="pill yellow">● After hours</span>'
      : '<span class="pill red">● Market closed</span>';
  const nextPill = health.next_contribution
    ? `<span class="pill" style="background:#1e1e2e;color:#a0aec0">Next: ${fmtTs(health.next_contribution)}</span>`
    : '';
  bar.innerHTML = marketPill
    + '<span class="pill red">Live</span>'
    + '<span class="pill purple">Dynamic</span>'
    + nextPill;

  const plClass = (p.total_value - p.cash_available) >= 0 ? 'green' : 'red';
  const invested = p.total_value - p.cash_available;
  document.getElementById('stats').innerHTML = `
    <div class="stat">
      <div class="label">Total value</div>
      <div class="value">${fmt(p.total_value)}</div>
    </div>
    <div class="stat">
      <div class="label">Cash available</div>
      <div class="value">${fmt(p.cash_available)}</div>
    </div>
    <div class="stat" style="margin-top:8px">
      <div class="label">Invested</div>
      <div class="value ${plClass}">${fmt(invested)}</div>
    </div>
    <div class="stat" style="margin-top:8px">
      <div class="label">Unrealised P&L</div>
      <div class="value ${plClass}">${fmt(Object.values(p.holdings).reduce((s,h)=>s+h.unrealized_pl,0))}</div>
    </div>
  `;

  const symbols = Object.keys(p.target_allocation);
  const rows = symbols.map((sym, i) => {
    const current = (p.holdings[sym]?.weight ?? 0);
    const target  = p.target_allocation[sym];
    const drift   = (current - target);
    const driftClass = Math.abs(drift) < 0.005 ? 'on' : drift > 0 ? 'over' : 'under';
    const driftSign  = drift > 0 ? '+' : '';
    const color = colorFor(sym, i);
    const barPct = Math.min(current * 100, 100);
    return `
      <div class="allocation-row">
        <div class="alloc-symbol">${sym}</div>
        <div class="alloc-bar-wrap">
          <div class="alloc-bar" style="width:${barPct}%;background:${color}"></div>
        </div>
        <div class="alloc-pct">${(current*100).toFixed(1)}%</div>
        <div class="alloc-target">/ ${(target*100).toFixed(0)}%</div>
        <div class="drift-badge ${driftClass}">${driftSign}${(drift*100).toFixed(1)}%</div>
      </div>`;
  }).join('');
  document.getElementById('allocation-rows').innerHTML = rows || '<div class="loading">No positions yet</div>';
}

function renderHistory(entries) {
  const snapshots = entries.filter(e => e.event === 'portfolio_snapshot' && e.total_value > 0);
  const byDay = {};
  snapshots.forEach(s => {
    const day = s.timestamp.slice(0,10);
    byDay[day] = s;
  });
  const days = Object.values(byDay).sort((a,b) => a.timestamp.localeCompare(b.timestamp));

  if (days.length >= 2) {
    mkValueChart(
      days.map(d => fmtDateShort(d.timestamp)),
      days.map(d => d.total_value),
    );
    const allSymbols = [...new Set(days.flatMap(d => Object.keys(d.drift_from_target || {})))];
    const driftData = {};
    allSymbols.forEach(sym => {
      driftData[sym] = days.map(d => d.drift_from_target?.[sym] ?? null);
    });
    mkDriftChart(days.map(d => fmtDateShort(d.timestamp)), driftData);
  } else {
    document.querySelector('.chart-wrap').innerHTML    = '<div class="loading">Not enough history yet — data builds after your first few cycles.</div>';
    document.querySelector('.chart-wrap-sm').innerHTML = '<div class="loading">Not enough history yet.</div>';
  }

  const proposals = entries.filter(e => e.event === 'dynamic_allocation_proposed' || e.event === 'ai_allocation_proposed').slice(0, 10);
  const ul = document.getElementById('contributions');
  if (!proposals.length) {
    ul.innerHTML = '<li class="loading">No contributions yet</li>';
  } else {
    ul.innerHTML = proposals.map(p => {
      const parts = Object.entries(p.allocations)
        .map(([sym, amt]) => `<span>${sym} ${fmt(amt)}</span>`).join('  ');
      const reason = p.allocation_reasoning || p.reasoning || '';
      return `<li class="contribution-item">
        <div class="contrib-left">
          <div class="contrib-date">${fmtTs(p.timestamp)}</div>
          <div class="contrib-alloc">${parts}</div>
          <div class="contrib-reasoning">${reason}</div>
        </div>
        <div class="contrib-right">${fmt(p.new_cash)}</div>
      </li>`;
    }).join('');
  }

  const recent = entries.slice(0, 20);
  const eventDot = {
    portfolio_snapshot:           'gray',
    dynamic_allocation_proposed:  'purple',
    ai_allocation_proposed:       'purple',
    fixed_counterfactual_logged:  'orange',
    orders_placed:                'green',
    market_data_fetched:          'blue',
    contribution_error:           'red',
  };
  const eventLabel = e => {
    switch(e.event) {
      case 'portfolio_snapshot':             return `Snapshot — ${fmt(e.total_value)}`;
      case 'dynamic_allocation_proposed':    return `Dynamic: ${Object.entries(e.allocations).map(([s,a])=>s+' '+fmt(a)).join(', ')}`;
      case 'ai_allocation_proposed':         return `AI proposed ${Object.entries(e.allocations).map(([s,a])=>s+' '+fmt(a)).join(', ')}`;
      case 'fixed_counterfactual_logged':    return `Fixed counterfactual logged`;
      case 'orders_placed':                  return `Orders placed — ${e.receipts?.map(r=>r.symbol).join(', ')}`;
      case 'market_data_fetched':            return 'Market data fetched';
      case 'contribution_error':             return `Error: ${e.error}`;
      default:                               return e.event.replace(/_/g,' ');
    }
  };
  document.getElementById('event-log').innerHTML = recent.map(e => `
    <li class="event-item">
      <div class="event-dot ${eventDot[e.event] || 'gray'}"></div>
      <div class="event-time">${fmtTs(e.timestamp)}</div>
      <div class="event-text">${eventLabel(e)}</div>
    </li>`).join('');
}

async function loadAll() {
  document.getElementById('refresh-btn').textContent = '↻ …';
  try {
    const [portfolio, health, audit] = await Promise.all([
      fetch('/portfolio').then(r => r.json()),
      fetch('/health').then(r => r.json()),
      fetch('/audit').then(r => r.json()),
    ]);
    renderPortfolio(portfolio, health);
    renderHistory(audit);
    document.getElementById('last-updated').textContent =
      'Updated ' + new Date().toLocaleTimeString('en-US',{hour:'numeric',minute:'2-digit',second:'2-digit'});
  } catch(err) {
    document.getElementById('status-bar').innerHTML =
      `<span class="pill red">⚠ Failed to load: ${err.message}</span>`;
  }
  document.getElementById('refresh-btn').textContent = '↻ Refresh';
}

loadAll();
setInterval(loadAll, 60_000);
</script>
</body>
</html>"""
