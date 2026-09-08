/* Forex Signal Scanner - tabbed SPA frontend */
"use strict";

/* =====================================================================
 * State
 * ===================================================================== */
const state = {
  category: "major",
  pairs: null,          // {major, cross, exotic, all}
  results: [],          // last scan results
  strategies: [],       // enabled strategy names (scanner tab)
  allStrategies: [],    // all strategy names
  autoTimer: null,
  autoMs: 60000,
  chart: null,          // lightweight-charts instance
  chartSeries: null,
  chartLoaded: false,   // whether chart data was loaded once
  modalChart: null,     // lightweight-charts instance in modal
  modalSeries: null,
  modalResult: null,    // ScanResult dict backing the modal
  modalTab: "chart",
  demoSide: "BUY",
  botState: null,
  clockTimer: null,
};

/* =====================================================================
 * Helpers
 * ===================================================================== */
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

function escapeHtml(value) {
  const s = String(value == null ? "" : value);
  const div = document.createElement("div");
  div.textContent = s;
  return div.innerHTML;
}

const fmtPrice = (v) => (v == null || Number.isNaN(Number(v)) ? "-" : Number(v).toFixed(5));
const fmtPips = (v) => (v == null || Number.isNaN(Number(v)) ? "-" : Number(v).toFixed(1));
const fmtPnl = (v) => (v == null || Number.isNaN(Number(v)) ? "-" : (v >= 0 ? "+" : "") + Number(v).toFixed(2));
const fmtPct = (v) => (v == null || Number.isNaN(Number(v)) ? "-" : Number(v).toFixed(1) + "%");
const fmtMoney = (v) => (v == null || Number.isNaN(Number(v)) ? "-" : "$" + Number(v).toLocaleString(undefined, { maximumFractionDigits: 2 }));

function pnlClass(v) {
  if (v == null || Number.isNaN(Number(v))) return "";
  return v > 0 ? "pos" : v < 0 ? "neg" : "";
}

function actionBadge(action) {
  const cls = (action || "NEUTRAL").toUpperCase();
  return `<span class="badge ${cls}">${escapeHtml(cls)}</span>`;
}

function shortTime(iso) {
  if (!iso) return "-";
  const s = String(iso).replace("T", " ").replace("Z", "").replace(/\.\d+/, "");
  return s.length >= 16 ? s.slice(0, 16) : s;
}

/* ---------- API ---------- */
async function apiGet(url) {
  const resp = await fetch(url);
  if (!resp.ok) {
    let detail = resp.statusText;
    try { detail = (await resp.json()).detail || detail; } catch (_) { /* ignore */ }
    throw new Error(`${resp.status}: ${detail}`);
  }
  return resp.json();
}

async function apiPost(url, body) {
  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  if (!resp.ok) {
    let detail = resp.statusText;
    try { detail = (await resp.json()).detail || detail; } catch (_) { /* ignore */ }
    throw new Error(`${resp.status}: ${detail}`);
  }
  return resp.json();
}

function setText(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}

function setHtml(id, html) {
  const el = document.getElementById(id);
  if (el) el.innerHTML = html;
}

/* =====================================================================
 * Tabs
 * ===================================================================== */
function switchTab(name) {
  $$(".tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
  $$(".panel").forEach((p) => p.classList.toggle("active", p.id === `panel-${name}`));
  if (name === "chart") {
    if (state.chart) {
      state.chart.applyOptions({ width: $("#chart-container").clientWidth });
    } else if (typeof LightweightCharts !== "undefined") {
      initChart();
    }
    if (!state.chartLoaded) loadChart();
  }
  if (name === "demo") refreshDemo();
  if (name === "oanda") refreshOanda();
  if (name === "bot") loadBotState();
  if (name === "clock") refreshClock();
}

$("#tabbar").addEventListener("click", (e) => {
  const btn = e.target.closest(".tab");
  if (btn) switchTab(btn.dataset.tab);
});

/* =====================================================================
 * Global: health + clock tick
 * ===================================================================== */
async function initHealth() {
  try {
    const h = await apiGet("/api/health");
    state.allStrategies = h.strategies || [];
    const pill = $("#api-status");
    pill.textContent = `API online · ${state.allStrategies.length} strategies`;
    pill.classList.add("ok");
  } catch (err) {
    const pill = $("#api-status");
    pill.textContent = "API offline";
    pill.classList.add("bad");
  }
}

function tickClock() {
  const now = new Date();
  const hh = String(now.getUTCHours()).padStart(2, "0");
  const mm = String(now.getUTCMinutes()).padStart(2, "0");
  const ss = String(now.getUTCSeconds()).padStart(2, "0");
  setText("utc-clock", `${hh}:${mm}:${ss} UTC`);
}
setInterval(tickClock, 1000);
tickClock();

/* =====================================================================
 * SCANNER TAB
 * ===================================================================== */
const CONFIG_FIELDS = [
  ["ema_fast", "EMA Fast", 20],
  ["ema_slow", "EMA Slow", 50],
  ["rsi_period", "RSI Period", 14],
  ["macd_fast", "MACD Fast", 12],
  ["macd_slow", "MACD Slow", 26],
  ["macd_signal", "MACD Signal", 9],
  ["bb_period", "BB Period", 20],
  ["bb_std", "BB Std Dev", 2.0],
  ["stoch_k", "Stoch %K", 14],
  ["stoch_d", "Stoch %D", 3],
  ["adx_period", "ADX Period", 14],
  ["adx_threshold", "ADX Threshold", 25.0],
  ["zz_deviation", "ZigZag Dev %", 0.8],
  ["sl_atr_mult", "SL ATR Mult", 1.5],
  ["tp_atr_mult", "TP ATR Mult", 2.5],
];

async function loadPairs() {
  const data = await apiGet("/api/pairs");
  state.pairs = data;
  renderPairSelect();
  renderChartPairs();
  renderDemoPairs();
  renderBtPairs();
}

function currentCategoryPairs() {
  if (!state.pairs) return [];
  if (state.category === "all") return state.pairs.all;
  return state.pairs[state.category] || [];
}

function renderPairSelect() {
  const sel = $("#pairs");
  sel.innerHTML = "";
  for (const p of currentCategoryPairs()) {
    const opt = document.createElement("option");
    opt.value = p;
    opt.textContent = p;
    sel.appendChild(opt);
  }
}

function buildPairsParam() {
  const sel = $("#pairs");
  const manual = Array.from(sel.selectedOptions).map((o) => o.value.trim().toUpperCase()).filter(Boolean);
  return manual.length ? manual : currentCategoryPairs();
}

function collectConfig() {
  const cfg = {};
  for (const [key] of CONFIG_FIELDS) {
    const input = $(`#cfg-${key}`);
    if (!input) continue;
    const raw = input.value.trim();
    if (raw === "") continue;
    const num = Number(raw);
    if (!Number.isNaN(num)) cfg[key] = num;
  }
  return cfg;
}

function collectStrategies() {
  return state.strategies;
}

function renderStrategyToggles() {
  const wrap = $("#strategy-toggles");
  if (!state.allStrategies.length) return;
  state.strategies = state.allStrategies.slice();
  wrap.innerHTML = state.allStrategies.map((name) => `
    <label class="toggle">
      <input type="checkbox" data-strategy="${escapeHtml(name)}" checked />
      <span>${escapeHtml(name)}</span>
    </label>`).join("");
  wrap.querySelectorAll("input[data-strategy]").forEach((input) => {
    input.addEventListener("change", () => {
      const name = input.dataset.strategy;
      if (input.checked) state.strategies.push(name);
      else state.strategies = state.strategies.filter((s) => s !== name);
      input.closest(".toggle").classList.toggle("off", !input.checked);
    });
  });
}

function renderConfigFields() {
  const wrap = $("#config-fields");
  wrap.innerHTML = CONFIG_FIELDS.map(([key, label, def]) => `
    <div class="config-item">
      <label for="cfg-${key}">${escapeHtml(label)}</label>
      <input id="cfg-${key}" type="number" step="any" value="${def}" />
    </div>`).join("");
}

function scanParams() {
  const params = new URLSearchParams();
  params.set("pairs", buildPairsParam().join(","));
  params.set("interval", $("#interval").value);
  params.set("period", $("#period").value);
  const cfg = collectConfig();
  for (const [k, v] of Object.entries(cfg)) params.set(k, v);
  const strats = collectStrategies();
  if (strats.length && strats.length < state.allStrategies.length) params.set("strategies", strats.join(","));
  return params;
}

function renderResults(data) {
  state.results = data.results || [];
  const wrap = $("#results-wrap");
  const empty = $("#empty-state");
  const body = $("#results-body");

  // Summary stats
  const buys = state.results.filter((r) => r.action === "BUY").length;
  const sells = state.results.filter((r) => r.action === "SELL").length;
  const neutrals = state.results.filter((r) => r.action === "NEUTRAL").length;
  setHtml("result-stats", `
    <span class="chip">${state.results.length} pairs</span>
    <span class="chip buy">▲ ${buys} buy</span>
    <span class="chip sell">▼ ${sells} sell</span>
    <span class="chip neutral">● ${neutrals} neutral</span>
  `);

  if (!state.results.length) {
    wrap.classList.add("hidden");
    empty.classList.remove("hidden");
    return;
  }
  wrap.classList.remove("hidden");
  empty.classList.add("hidden");

  body.innerHTML = state.results.map((r) => {
    const rr = r.rr_ratio != null ? r.rr_ratio.toFixed(2) : "-";
    return `
    <tr>
      <td class="mono">${escapeHtml(r.pair)}</td>
      <td class="mono">${fmtPrice(r.price)}</td>
      <td>${actionBadge(r.action)}</td>
      <td>
        <span class="strength-bar"><div class="${(r.action || "NEUTRAL").toLowerCase().slice(0, 1)}" style="width:${Math.round((r.strength || 0) * 100)}%"></div></span>
        <span class="strength-val">${((r.strength || 0) * 100).toFixed(0)}%</span>
      </td>
      <td class="mono">${r.stop_loss == null ? "-" : fmtPrice(r.stop_loss)}</td>
      <td class="mono">${r.take_profit == null ? "-" : fmtPrice(r.take_profit)}</td>
      <td class="mono">${rr}</td>
      <td class="votes">
        <span class="b">${r.buy_votes || 0}▲</span>
        <span class="s">${r.sell_votes || 0}▼</span>
        <span class="n">${r.neutral_votes || 0}●</span>
      </td>
      <td class="reasons">${escapeHtml((r.reasons || []).join(" · "))}</td>
      <td><button class="btn sm" data-detail="${escapeHtml(r.pair)}">Details</button></td>
    </tr>`;
  }).join("");

  body.querySelectorAll("button[data-detail]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const r = state.results.find((x) => x.pair === btn.dataset.detail);
      if (r) openModal(r);
    });
  });
}

async function runScan() {
  const loading = $("#scan-loading");
  const error = $("#scan-error");
  loading.classList.remove("hidden");
  error.classList.add("hidden");
  try {
    const data = await apiGet(`/api/scan?${scanParams().toString()}`);
    renderResults(data);
    setText("scan-time", `scanned ${shortTime(data.scanned_at)} · ${data.interval}`);
    if (data.failed && data.failed.length) {
      error.textContent = `Could not fetch: ${data.failed.join(", ")}`;
      error.classList.remove("hidden");
    }
  } catch (err) {
    error.textContent = err.message;
    error.classList.remove("hidden");
  } finally {
    loading.classList.add("hidden");
  }
}

$("#btn-scan").addEventListener("click", runScan);
$("#btn-refresh").addEventListener("click", runScan);

$("#category").addEventListener("click", (e) => {
  const btn = e.target.closest(".seg");
  if (!btn) return;
  state.category = btn.dataset.cat;
  $$("#category .seg").forEach((s) => s.classList.toggle("active", s === btn));
  renderPairSelect();
});

$("#auto-refresh").addEventListener("click", (e) => {
  const btn = e.target.closest(".seg");
  if (!btn) return;
  state.autoMs = Number(btn.dataset.ms);
  $$("#auto-refresh .seg").forEach((s) => s.classList.toggle("active", s === btn));
  if (state.autoTimer) { clearInterval(state.autoTimer); state.autoTimer = null; }
  if (state.autoMs > 0) {
    state.autoTimer = setInterval(() => { if ($("#panel-scanner").classList.contains("active")) runScan(); }, state.autoMs);
  }
});

/* =====================================================================
 * CHART TAB (lightweight-charts candlestick)
 * ===================================================================== */
function renderChartPairs() {
  const sel = $("#chart-pair");
  sel.innerHTML = "";
  if (!state.pairs) return;
  for (const p of state.pairs.all) {
    const opt = document.createElement("option");
    opt.value = p;
    opt.textContent = p;
    sel.appendChild(opt);
  }
}

function initChart() {
  if (state.chart) return;
  if (typeof LightweightCharts === "undefined") {
    setText("chart-status", "chart library failed to load — check network/console");
    return;
  }
  const container = $("#chart-container");
  state.chart = LightweightCharts.createChart(container, {
    width: container.clientWidth,
    height: 460,
    layout: { background: { type: "solid", color: "transparent" }, textColor: "#aab0cc", fontFamily: "'IBM Plex Mono', monospace" },
    grid: { vertLines: { color: "#14142a" }, horzLines: { color: "#14142a" } },
    crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
    timeScale: { borderColor: "#1e1e32", timeVisible: true, secondsVisible: false },
    rightPriceScale: { borderColor: "#1e1e32" },
  });
  state.chartSeries = state.chart.addCandlestickSeries({
    upColor: "#00ff88", downColor: "#ff4466", borderVisible: false,
    wickUpColor: "#00ff88", wickDownColor: "#ff4466",
  });
}

function chartTime(ts) {
  // Backend times look like "2026-09-08 13:00:00"; parse as UTC
  const s = String(ts).replace(" ", "T");
  const d = new Date(s.endsWith("Z") || /[+-]\d\d:\d\d$/.test(s) ? s : s + "Z");
  return Math.floor(d.getTime() / 1000);
}

async function loadChart() {
  const pair = $("#chart-pair").value;
  const interval = $("#chart-interval").value;
  const period = $("#chart-period").value;
  if (!pair) return;
  const status = $("#chart-status");
  status.textContent = "loading…";
  try {
    initChart();
    if (!state.chart) {
      status.textContent = "chart unavailable — library did not load";
      return;
    }
    state.chartLoaded = true;
    const data = await apiGet(`/api/pair/${pair}/chart?interval=${interval}&period=${period}&limit=400`);
    const ohlcv = data.ohlcv;
    const candles = [];
    for (let i = 0; i < ohlcv.time.length; i++) {
      const t = chartTime(ohlcv.time[i]);
      const o = Number(ohlcv.open[i]), h = Number(ohlcv.high[i]), l = Number(ohlcv.low[i]), c = Number(ohlcv.close[i]);
      if ([t, o, h, l, c].some((x) => Number.isNaN(x))) continue;
      candles.push({ time: t, open: o, high: h, low: l, close: c });
    }
    state.chartSeries.setData(candles);
    state.chart.timeScale().fitContent();
    status.textContent = `${pair} · ${candles.length} candles · ${interval}`;
  } catch (err) {
    status.textContent = `error: ${err.message}`;
  }
}

$("#btn-chart-load").addEventListener("click", loadChart);
$("#chart-pair").addEventListener("change", loadChart);
$("#chart-interval").addEventListener("change", loadChart);
$("#chart-period").addEventListener("change", loadChart);

/* =====================================================================
 * DEMO TAB (paper trading)
 * ===================================================================== */
function renderDemoPairs() {
  const sel = $("#demo-pair");
  sel.innerHTML = "";
  if (!state.pairs) return;
  for (const p of state.pairs.all) {
    const opt = document.createElement("option");
    opt.value = p;
    opt.textContent = p;
    sel.appendChild(opt);
  }
}

async function refreshDemo() {
  try {
    const acc = await apiGet("/api/demo/account");
    setText("demo-mode", acc.mode || "paper");
    setText("demo-balance", fmtMoney(acc.balance));
    setText("demo-equity", fmtMoney(acc.equity));
    setText("demo-upnl", fmtMoney(acc.unrealized_pnl));
    setText("demo-open", acc.open_count);
    setText("demo-closed", acc.closed_count);
    setText("demo-winrate", acc.win_rate == null ? "-" : acc.win_rate.toFixed(1) + "%");

    const upnlEl = $("#demo-upnl");
    upnlEl.classList.remove("pos", "neg");
    if (acc.unrealized_pnl > 0) upnlEl.classList.add("pos");
    else if (acc.unrealized_pnl < 0) upnlEl.classList.add("neg");

    setHtml("demo-positions", (acc.open_positions || []).map((p) => `
      <tr>
        <td class="mono">${escapeHtml(p.id)}</td>
        <td class="mono">${escapeHtml(p.pair)}</td>
        <td>${actionBadge(p.side)}</td>
        <td class="mono">${Number(p.units).toLocaleString()}</td>
        <td class="mono">${fmtPrice(p.open_price)}</td>
        <td class="mono ${pnlClass(p.unrealized_pnl)}">${fmtPnl(p.unrealized_pnl)}</td>
        <td><button class="btn sm danger" data-close="${escapeHtml(p.id)}">Close</button></td>
      </tr>`).join(""));

    $$("#demo-positions button[data-close]").forEach((btn) => {
      btn.addEventListener("click", () => closeDemoPosition(btn.dataset.close));
    });

    setHtml("demo-history", (acc.history || []).map((t) => `
      <tr>
        <td class="mono">${escapeHtml(shortTime(t.close_time))}</td>
        <td class="mono">${escapeHtml(t.pair)}</td>
        <td>${actionBadge(t.side)}</td>
        <td class="mono">${fmtPrice(t.open_price)}</td>
        <td class="mono">${fmtPrice(t.close_price)}</td>
        <td class="mono ${pnlClass(t.pnl_pips)}">${fmtPips(t.pnl_pips)}</td>
        <td class="mono ${pnlClass(t.pnl)}">${fmtPnl(t.pnl)}</td>
      </tr>`).join(""));
  } catch (err) {
    setText("demo-balance", "err");
    showMsg("demo-msg", `Failed to load account: ${err.message}`, "error");
  }
}

function showMsg(id, text, tone) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = text;
  el.classList.remove("hidden", "ok", "error");
  if (tone) el.classList.add(tone);
}

$("#demo-side-buy").addEventListener("click", () => {
  state.demoSide = "BUY";
  $("#demo-side-buy").classList.add("active");
  $("#demo-side-sell").classList.remove("active");
});
$("#demo-side-sell").addEventListener("click", () => {
  state.demoSide = "SELL";
  $("#demo-side-sell").classList.add("active");
  $("#demo-side-buy").classList.remove("active");
});

async function openDemoPosition() {
  const pair = $("#demo-pair").value;
  const units = Number($("#demo-units").value) || 10000;
  const price = $("#demo-entry").value ? Number($("#demo-entry").value) : 0;
  const sl = $("#demo-sl").value ? Number($("#demo-sl").value) : null;
  const tp = $("#demo-tp").value ? Number($("#demo-tp").value) : null;
  const payload = { pair, side: state.demoSide, units, price };
  if (sl) payload.sl = sl;
  if (tp) payload.tp = tp;
  try {
    await apiPost("/api/demo/order", payload);
    showMsg("demo-msg", `Opened ${state.demoSide} ${pair}`, "ok");
    $("#demo-entry").value = "";
    refreshDemo();
  } catch (err) {
    showMsg("demo-msg", err.message, "error");
  }
}
$("#btn-demo-open").addEventListener("click", openDemoPosition);

async function closeDemoPosition(id) {
  try {
    await apiPost("/api/demo/close", { id });
    showMsg("demo-msg", `Closed ${id}`, "ok");
    refreshDemo();
  } catch (err) {
    showMsg("demo-msg", err.message, "error");
  }
}

$("#btn-demo-reset").addEventListener("click", async () => {
  try {
    await apiPost("/api/demo/reset", {});
    showMsg("demo-msg", "Account reset", "ok");
    refreshDemo();
  } catch (err) {
    showMsg("demo-msg", err.message, "error");
  }
});

/* =====================================================================
 * OANDA TAB
 * ===================================================================== */
async function refreshOanda() {
  try {
    const [acc, quotes] = await Promise.all([
      apiGet("/api/oanda-account"),
      apiGet("/api/oanda-prices"),
    ]);
    setText("oanda-mode", acc.mode || "paper");
    setText("oanda-env", acc.env || "practice");
    setText("oanda-balance", fmtMoney(acc.balance));
    setText("oanda-equity", fmtMoney(acc.equity));
    setText("oanda-upnl", fmtMoney(acc.unrealized_pnl));
    setText("oanda-winrate", acc.win_rate == null ? "-" : acc.win_rate.toFixed(1) + "%");

    const q = quotes.quotes || {};
    setHtml("oanda-quotes", Object.entries(q).map(([pair, quote]) => `
      <div class="quote-card">
        <div class="quote-pair mono">${escapeHtml(pair)}</div>
        <div class="quote-mid mono">${fmtPrice(quote.mid)}</div>
        <div class="quote-side mono">B ${fmtPrice(quote.bid)} · A ${fmtPrice(quote.ask)}</div>
      </div>`).join(""));

    setHtml("oanda-positions", (acc.open_positions || []).map((p) => `
      <tr>
        <td class="mono">${escapeHtml(p.id)}</td>
        <td class="mono">${escapeHtml(p.pair)}</td>
        <td>${actionBadge(p.side)}</td>
        <td class="mono">${Number(p.units).toLocaleString()}</td>
        <td class="mono">${fmtPrice(p.open_price)}</td>
        <td class="mono">${fmtPrice(p.current_price)}</td>
        <td class="mono ${pnlClass(p.unrealized_pnl)}">${fmtPnl(p.unrealized_pnl)}</td>
        <td><button class="btn sm danger" data-close="${escapeHtml(p.id)}">Close</button></td>
      </tr>`).join(""));

    $$("#oanda-positions button[data-close]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        try {
          await apiPost("/api/oanda-close", { id: btn.dataset.close });
          refreshOanda();
        } catch (err) {
          showMsg("demo-msg", err.message, "error");
        }
      });
    });

    const monthly = await apiGet("/api/demo/monthly");
    setHtml("oanda-monthly", (monthly.months || []).map((m) => `
      <tr>
        <td class="mono">${escapeHtml(m.month)}</td>
        <td class="mono">${m.trades}</td>
        <td class="mono pos">${m.wins}</td>
        <td class="mono neg">${m.losses}</td>
        <td class="mono">${m.win_rate == null ? "-" : m.win_rate.toFixed(1) + "%"}</td>
        <td class="mono ${pnlClass(m.net_pnl)}">${fmtPnl(m.net_pnl)}</td>
      </tr>`).join(""));
  } catch (err) {
    setText("oanda-balance", "err");
  }
}

/* =====================================================================
 * BOT TAB
 * ===================================================================== */
function renderBotToggles(s) {
  const wrap = $("#bot-strategies");
  wrap.innerHTML = (s.strategies || []).map((name) => {
    const enabled = s.enabled && s.enabled[name] !== false;
    return `<label class="toggle ${enabled ? "" : "off"}">
      <input type="checkbox" data-bot-strategy="${escapeHtml(name)}" ${enabled ? "checked" : ""} />
      <span>${escapeHtml(name)}</span>
    </label>`;
  }).join("");
  wrap.querySelectorAll("input[data-bot-strategy]").forEach((input) => {
    input.addEventListener("change", () => {
      const action = input.checked ? "resume_strategy" : "pause_strategy";
      apiPost("/api/bot-state", { action, strategy: input.dataset.botStrategy })
        .then(renderBotState)
        .catch((err) => { setText("bot-log", `err: ${err.message}`); });
    });
  });
}

function renderBotLog(s) {
  const box = $("#bot-log");
  box.innerHTML = (s.log || []).slice().reverse().map((l) => `
    <div class="log-line ${escapeHtml(l.level)}">
      <span class="mono log-time">${escapeHtml(l.time)}</span>
      <span>${escapeHtml(l.message)}</span>
    </div>`).join("");
  box.scrollTop = 0;
}

function renderBotState(s) {
  state.botState = s;
  const running = !!s.running;
  const pill = $("#bot-state-pill");
  pill.textContent = running ? "running" : "stopped";
  pill.classList.toggle("ok", running);
  pill.classList.toggle("bad", !running);
  renderBotToggles(s);
  renderBotLog(s);
  setText("bot-min-score", s.min_score != null ? s.min_score : 12);
  const last = s.last_run;
  if (last && last.best_signal) {
    setHtml("bot-last-signal", `<span class="badge ${last.best_signal.action}">${escapeHtml(last.best_signal.action)}</span> ${escapeHtml(last.best_signal.pair)} · score ${last.best_signal.score} @ ${fmtPrice(last.best_signal.price)}`);
  } else {
    setText("bot-last-signal", last ? "no actionable signal" : "—");
  }
  setHtml("bot-history", (s.signal_history || []).slice().reverse().map((h) => `
    <tr>
      <td class="mono">${escapeHtml(shortTime(h.time))}</td>
      <td class="mono">${escapeHtml(h.pair)}</td>
      <td>${actionBadge(h.action)}</td>
      <td class="mono">${h.score != null ? h.score.toFixed(1) : "-"}</td>
    </tr>`).join(""));
}

async function loadBotState() {
  try {
    const s = await apiGet("/api/bot-state");
    renderBotState(s);
  } catch (err) {
    setText("bot-state-pill", "err");
  }
}

$("#btn-bot-run").addEventListener("click", async () => {
  const btn = $("#btn-bot-run");
  btn.disabled = true;
  btn.textContent = "Running…";
  try {
    const s = await apiPost("/api/bot-run", {
      interval: "1h",
      period: "1mo",
      ...collectConfig(),
    });
    renderBotState(s);
  } catch (err) {
    setText("bot-log", `err: ${err.message}`);
  } finally {
    btn.disabled = false;
    btn.textContent = "▶ Run Cycle";
  }
});

$("#btn-bot-reset").addEventListener("click", async () => {
  try {
    const s = await apiPost("/api/bot-state", { action: "reset" });
    renderBotState(s);
  } catch (err) { /* ignore */ }
});

$("#btn-bot-save").addEventListener("click", async () => {
  const enabled = {};
  if (state.botState && state.botState.strategies) {
    state.botState.strategies.forEach((name) => {
      const input = $(`input[data-bot-strategy="${CSS.escape(name)}"]`);
      enabled[name] = input ? input.checked : true;
    });
  }
  try {
    const s = await apiPost("/api/bot-state", {
      action: "save_config",
      enabled,
      min_score: Number($("#bot-min-score").value) || 12,
    });
    renderBotState(s);
  } catch (err) { /* ignore */ }
});

/* =====================================================================
 * BACKTEST TAB
 * ===================================================================== */
function renderBtPairs() {
  const sel = $("#bt-pair");
  sel.innerHTML = "";
  if (!state.pairs) return;
  for (const p of state.pairs.all) {
    const opt = document.createElement("option");
    opt.value = p;
    opt.textContent = p;
    sel.appendChild(opt);
  }
}

function drawEquityCurve(curve) {
  const wrap = $("#bt-equity");
  if (!curve || curve.length < 2) {
    wrap.innerHTML = '<div class="empty">Not enough trades to draw an equity curve.</div>';
    return;
  }
  const W = 900, H = 260, pad = 24;
  const vals = curve.map((p) => Number(p.equity));
  const min = Math.min(0, ...vals);
  const max = Math.max(0, ...vals);
  const range = max - min || 1;
  const pts = curve.map((p, i) => {
    const x = pad + (i / (curve.length - 1)) * (W - pad * 2);
    const y = H - pad - ((Number(p.equity) - min) / range) * (H - pad * 2);
    return [x, y];
  });
  const poly = pts.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const zeroY = H - pad - ((0 - min) / range) * (H - pad * 2);
  const positive = vals[vals.length - 1] >= 0;
  const color = positive ? "#00ff88" : "#ff4466";
  wrap.innerHTML = `
    <svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" class="equity-svg">
      <line x1="${pad}" y1="${zeroY.toFixed(1)}" x2="${W - pad}" y2="${zeroY.toFixed(1)}" stroke="#1e1e32" stroke-dasharray="4 4" />
      <polygon points="${poly} ${pts[pts.length - 1][0].toFixed(1)},${H - pad} ${pts[0][0].toFixed(1)},${H - pad}" fill="${color}" opacity="0.12" />
      <polyline points="${poly}" fill="none" stroke="${color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" />
      <text x="${W - pad}" y="${pad - 6}" fill="${color}" font-size="12" text-anchor="end" font-family="monospace">${(vals[vals.length - 1] >= 0 ? "+" : "") + vals[vals.length - 1].toFixed(1)} pips</text>
    </svg>`;
}

async function runBacktest() {
  const loading = $("#bt-loading");
  const error = $("#bt-error");
  const results = $("#bt-results");
  loading.classList.remove("hidden");
  error.classList.add("hidden");
  results.classList.add("hidden");
  try {
    const params = new URLSearchParams();
    params.set("pair", $("#bt-pair").value);
    params.set("interval", $("#bt-interval").value);
    params.set("period", $("#bt-period").value);
    params.set("max_candles", $("#bt-candles").value);
    const cfg = collectConfig();
    for (const [k, v] of Object.entries(cfg)) params.set(k, v);

    const data = await apiGet(`/api/backtest?${params.toString()}`);
    const s = data.stats || {};
    const v = data.verdict || { label: "-", tone: "neutral", detail: "" };

    setHtml("bt-verdict", `
      <div class="verdict-badge ${v.tone}">${escapeHtml(v.label)}</div>
      <div class="verdict-detail">${escapeHtml(v.detail)}</div>
      <div class="verdict-meta mono">${escapeHtml(data.pair)} · ${data.candles_used} candles · ${escapeHtml(data.interval)}</div>`);

    setText("bt-trades", s.trades != null ? s.trades : "-");
    setText("bt-winrate", s.win_rate == null ? "-" : s.win_rate.toFixed(1) + "%");
    setText("bt-avgwin", s.avg_win_pips == null ? "-" : fmtPips(s.avg_win_pips));
    setText("bt-avgloss", s.avg_loss_pips == null ? "-" : fmtPips(s.avg_loss_pips));
    setText("bt-ev", s.expected_value == null ? "-" : fmtPips(s.expected_value));
    setText("bt-lwin", s.largest_win == null ? "-" : fmtPips(s.largest_win));
    setText("bt-lloss", s.largest_loss == null ? "-" : fmtPips(s.largest_loss));
    setText("bt-totalpips", s.total_pips == null ? "-" : (s.total_pips >= 0 ? "+" : "") + Number(s.total_pips).toFixed(1));
    setText("bt-pf", s.profit_factor == null ? "-" : Number(s.profit_factor).toFixed(2));

    drawEquityCurve(data.equity_curve);

    setHtml("bt-trades", (data.trades || []).slice().reverse().map((t) => `
      <tr>
        <td class="mono">${escapeHtml(shortTime(t.entry_time))}</td>
        <td>${actionBadge(t.side)}</td>
        <td class="mono">${fmtPrice(t.entry)}</td>
        <td class="mono">${fmtPrice(t.exit)}</td>
        <td class="mono">${escapeHtml(shortTime(t.exit_time))}</td>
        <td class="mono ${pnlClass(t.pnl_pips)}">${fmtPips(t.pnl_pips)}</td>
        <td class="mono">${t.bars_held}</td>
      </tr>`).join(""));

    results.classList.remove("hidden");
  } catch (err) {
    error.textContent = err.message;
    error.classList.remove("hidden");
  } finally {
    loading.classList.add("hidden");
  }
}
$("#btn-backtest-run").addEventListener("click", runBacktest);

/* =====================================================================
 * CLOCK TAB (market sessions + calendar)
 * ===================================================================== */
function sessionSegment(name, openH, closeH, color, openNow) {
  // Render a session as one or two segments across a 24h timeline.
  const start = (openH / 24) * 100;
  const len = ((closeH - openH + 24) % 24 || 24) / 24 * 100;
  const segs = [];
  if (openH < closeH || openH === closeH) {
    segs.push({ left: start, width: len });
  } else {
    segs.push({ left: start, width: (24 - openH) / 24 * 100 });
    segs.push({ left: 0, width: (closeH / 24) * 100 });
  }
  return segs.map((seg) => `
    <div class="session-seg" style="left:${seg.left.toFixed(2)}%;width:${seg.width.toFixed(2)}%;background:${color};${openNow ? "" : "opacity:.35"}" title="${name} ${openH}:00-${closeH}:00 UTC"></div>`).join("");
}

function renderSessionTimeline(sessions, utcHhmm) {
  const wrap = $("#session-timeline");
  const labels = Array.from({ length: 25 }, (_, i) => i).map((h) => {
    const hh = String(h % 24).padStart(2, "0");
    return `<span class="tl-label mono">${hh}</span>`;
  }).join("");
  const segs = (sessions || []).map((s) => {
    const [oh, ch] = [Number(s.open), Number(s.close)];
    return sessionSegment(s.name, oh, ch, s.color, s.open_now);
  }).join("");
  const [hh, mm] = String(utcHhmm || "").split(":").map(Number);
  const nowPct = (hh * 60 + (mm || 0)) / (24 * 60) * 100;
  wrap.innerHTML = `
    <div class="tl-labels">${labels}</div>
    <div class="tl-track">
      ${segs}
      <div class="tl-now" style="left:${nowPct.toFixed(2)}%"></div>
    </div>
    <div class="tl-legend">${(sessions || []).map((s) => `
      <span class="tl-legend-item"><i style="background:${s.color}"></i>${escapeHtml(s.name)}</span>`).join("")}</div>`;
}

function renderSessionList(sessions) {
  const wrap = $("#session-list");
  wrap.innerHTML = (sessions || []).map((s) => `
    <div class="session-item ${s.open_now ? "open" : ""}">
      <span class="session-dot" style="background:${s.color}"></span>
      <span class="session-name">${escapeHtml(s.name)}</span>
      <span class="session-time mono">${escapeHtml(s.open_utc)} – ${escapeHtml(s.close_utc)} UTC</span>
      <span class="pill ${s.open_now ? "ok" : "dim"}">${s.open_now ? "open" : "closed"}</span>
    </div>`).join("");
}

async function refreshClock() {
  try {
    const [clock, cal] = await Promise.all([
      apiGet("/api/clock"),
      apiGet("/api/calendar?days=7"),
    ]);
    setText("clock-utc", `UTC ${clock.utc_hhmm}`);
    setText("clock-weekday", clock.weekday || "-");
    const ne = clock.next_event;
    setText("clock-next", ne ? `${ne.currency} · ${ne.event} (${ne.time_utc})` : "none");
    renderSessionTimeline(clock.sessions, clock.utc_hhmm);
    renderSessionList(clock.sessions);
    setHtml("calendar-body", (cal.events || []).map((ev) => `
      <tr class="${ev.is_today ? "today" : ""}">
        <td class="mono">${escapeHtml(ev.date)}${ev.is_today ? ' <span class="pill ok">today</span>' : ""}</td>
        <td class="mono">${escapeHtml(ev.currency)}</td>
        <td>${escapeHtml(ev.event)}</td>
        <td class="mono">${escapeHtml(ev.time_utc)}</td>
      </tr>`).join(""));
  } catch (err) {
    setText("clock-utc", "err");
  }
}

function tickClockTab() {
  const now = new Date();
  const hh = String(now.getUTCHours()).padStart(2, "0");
  const mm = String(now.getUTCMinutes()).padStart(2, "0");
  const ss = String(now.getUTCSeconds()).padStart(2, "0");
  setText("clock-time", `${hh}:${mm}:${ss}`);
  if ($("#panel-clock").classList.contains("active")) setText("clock-utc", `UTC ${hh}:${mm}`);
}
setInterval(tickClockTab, 1000);
tickClockTab();

/* =====================================================================
 * DETAIL MODAL (chart / breakdown / json)
 * ===================================================================== */
function openModal(result) {
  state.modalResult = result;
  state.modalTab = "chart";
  setText("modal-title", `${result.pair} — Signal Details`);
  $$("#modal-tabs .mtab").forEach((t) => t.classList.toggle("active", t.dataset.mtab === "chart"));
  renderModalTab("chart");
  $("#modal").classList.remove("hidden");
  document.body.classList.add("modal-open");
}

function renderModalTab(tab) {
  const body = $("#modal-body");
  const r = state.modalResult;
  if (!r) return;
  state.modalTab = tab;
  $$("#modal-tabs .mtab").forEach((t) => t.classList.toggle("active", t.dataset.mtab === tab));

  if (tab === "chart") {
    body.innerHTML = `<div id="modal-chart-container" class="chart-container"></div>`;
    loadModalChart(r);
  } else if (tab === "breakdown") {
    body.innerHTML = `
      <div class="breakdown">
        <div class="field-row"><label>Pair</label><span class="mono">${escapeHtml(r.pair)}</span></div>
        <div class="field-row"><label>Action</label><span>${actionBadge(r.action)}</span></div>
        <div class="field-row"><label>Strength</label><span class="mono">${((r.strength || 0) * 100).toFixed(0)}%</span></div>
        <div class="field-row"><label>Price</label><span class="mono">${fmtPrice(r.price)}</span></div>
        <div class="field-row"><label>Stop Loss</label><span class="mono">${r.stop_loss == null ? "-" : fmtPrice(r.stop_loss)}</span></div>
        <div class="field-row"><label>Take Profit</label><span class="mono">${r.take_profit == null ? "-" : fmtPrice(r.take_profit)}</span></div>
        <div class="field-row"><label>R:R Ratio</label><span class="mono">${r.rr_ratio == null ? "-" : r.rr_ratio.toFixed(2)}</span></div>
        <div class="field-row"><label>Votes</label><span class="votes"><span class="b">${r.buy_votes || 0}▲</span> <span class="s">${r.sell_votes || 0}▼</span> <span class="n">${r.neutral_votes || 0}●</span></span></div>
        <h4 class="mt">Signal Breakdown</h4>
        <table class="table">
          <thead><tr><th>Strategy</th><th>Signal</th><th>Strength</th><th>Reasons</th></tr></thead>
          <tbody>${(r.signals || []).map((sig) => `
            <tr>
              <td class="mono">${escapeHtml(sig.strategy)}</td>
              <td>${actionBadge(sig.action)}</td>
              <td class="mono">${((sig.strength || 0) * 100).toFixed(0)}%</td>
              <td class="reasons">${escapeHtml((sig.reasons || []).join(" · "))}</td>
            </tr>`).join("")}</tbody>
        </table>
      </div>`;
  } else if (tab === "json") {
    body.innerHTML = `<pre class="json-view">${escapeHtml(JSON.stringify(r, null, 2))}</pre>`;
  }
}

function loadModalChart(result) {
  const container = document.getElementById("modal-chart-container");
  if (!container || typeof LightweightCharts === "undefined") return;
  if (state.modalChart) {
    try { state.modalChart.remove(); } catch (_) { /* ignore */ }
    state.modalChart = null;
  }
  state.modalChart = LightweightCharts.createChart(container, {
    width: container.clientWidth,
    height: 360,
    layout: { background: { type: "solid", color: "transparent" }, textColor: "#aab0cc", fontFamily: "'IBM Plex Mono', monospace" },
    grid: { vertLines: { color: "#14142a" }, horzLines: { color: "#14142a" } },
    crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
    timeScale: { borderColor: "#1e1e32", timeVisible: true, secondsVisible: false },
    rightPriceScale: { borderColor: "#1e1e32" },
  });
  state.modalSeries = state.modalChart.addCandlestickSeries({
    upColor: "#00ff88", downColor: "#ff4466", borderVisible: false,
    wickUpColor: "#00ff88", wickDownColor: "#ff4466",
  });
  apiGet(`/api/pair/${result.pair}/chart?interval=1h&period=3mo&limit=200`)
    .then((data) => {
      const ohlcv = data.ohlcv;
      const candles = [];
      for (let i = 0; i < ohlcv.time.length; i++) {
        const t = chartTime(ohlcv.time[i]);
        const o = Number(ohlcv.open[i]), h = Number(ohlcv.high[i]), l = Number(ohlcv.low[i]), c = Number(ohlcv.close[i]);
        if ([t, o, h, l, c].some((x) => Number.isNaN(x))) continue;
        candles.push({ time: t, open: o, high: h, low: l, close: c });
      }
      state.modalSeries.setData(candles);
      state.modalChart.timeScale().fitContent();
    })
    .catch(() => { container.innerHTML = '<div class="empty">Chart unavailable</div>'; });
}

$("#modal-tabs").addEventListener("click", (e) => {
  const tab = e.target.closest(".mtab");
  if (tab) renderModalTab(tab.dataset.mtab);
});
$("#modal-close").addEventListener("click", () => {
  $("#modal").classList.add("hidden");
  document.body.classList.remove("modal-open");
});
$("#modal").addEventListener("click", (e) => {
  if (e.target.id === "modal") {
    $("#modal").classList.add("hidden");
    document.body.classList.remove("modal-open");
  }
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    $("#modal").classList.add("hidden");
    document.body.classList.remove("modal-open");
  }
});

/* =====================================================================
 * BOOTSTRAP
 * ===================================================================== */
async function init() {
  try {
    await Promise.all([initHealth(), loadPairs()]);
  } catch (_) { /* handled inside */ }
  renderStrategyToggles();
  renderConfigFields();
  if ($("#pairs").options.length) runScan();
}

init();
