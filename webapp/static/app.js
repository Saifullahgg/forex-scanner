/* Forex Scanner Dashboard - frontend logic */

"use strict";

/* ---------- State ---------- */
const state = {
  category: "major",
  pairs: null,          // full pair list from /api/pairs
  results: [],          // last scan results
  strategies: [],       // enabled strategy names
  allStrategies: [],    // all strategy names from /api/health
  autoRefreshTimer: null,
  chart: null,
  chartData: null,
  currentPair: null,
};

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
  ["sl_atr_mult", "SL ATR Multiplier", 1.5],
  ["tp_atr_mult", "TP ATR Multiplier", 2.5],
];

/* ---------- DOM helpers ---------- */
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));
function escapeHtml(value) {
  const s = String(value == null ? "" : value);
  const div = document.createElement("div");
  div.textContent = s;
  return div.innerHTML;
}
const fmtPrice = (v) => (v == null ? "-" : Number(v).toFixed(5));

function showLoading(on) {
  $("#loading").classList.toggle("hidden", !on);
}
function showError(msg) {
  const el = $("#error");
  if (msg) { el.textContent = msg; el.classList.remove("hidden"); }
  else { el.classList.add("hidden"); }
}

/* ---------- API ---------- */
async function apiGet(url) {
  const resp = await fetch(url);
  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const data = await resp.json();
      detail = data.detail || detail;
    } catch (_) { /* ignore */ }
    throw new Error(`${resp.status}: ${detail}`);
  }
  return resp.json();
}

async function loadPairs() {
  const data = await apiGet("/api/pairs");
  state.pairs = data;
  return data;
}

function buildPairsParam() {
  const cat = state.category;
  const list = state.pairs
    ? (cat === "all" ? state.pairs.all : state.pairs[cat])
    : [];
  const manual = $("#pairs").value
    .split(",")
    .map((s) => s.trim().toUpperCase())
    .filter(Boolean);
  return manual.length ? manual : list;
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

function buildScanUrl() {
  const params = new URLSearchParams();
  params.set("pairs", buildPairsParam().join(","));
  params.set("interval", $("#interval").value);
  params.set("period", $("#period").value);
  if (state.strategies.length && state.strategies.length < state.allStrategies.length) {
    params.set("strategies", state.strategies.join(","));
  }
  const cfg = collectConfig();
  for (const [k, v] of Object.entries(cfg)) params.set(k, String(v));
  return `/api/scan?${params.toString()}`;
}

async function runScan() {
  const url = buildScanUrl();
  showError(null);
  showLoading(true);
  $("#btn-scan").disabled = true;
  try {
    const data = await apiGet(url);
    state.results = data.results || [];
    $("#scan-time").textContent = `Scanned ${new Date(data.scanned_at).toLocaleTimeString()}`;
    renderTable();
  } catch (err) {
    showError(err.message);
  } finally {
    showLoading(false);
    $("#btn-scan").disabled = false;
  }
}

/* ---------- Rendering: table ---------- */
function renderTable() {
  const body = $("#results-body");
  const count = $("#result-count");
  const empty = $("#empty-state");
  body.innerHTML = "";

  if (!state.results.length) {
    empty.classList.remove("hidden");
    count.textContent = "";
    return;
  }
  empty.classList.add("hidden");
  count.textContent = `${state.results.length} pair(s)`;

  for (const r of state.results) {
    const tr = document.createElement("tr");
    const actionCls = r.action.toLowerCase();
    const barCls = actionCls === "buy" ? "b" : actionCls === "sell" ? "s" : "n";

    const strengthHtml = `
      <span class="strength-bar"><div class="${barCls}" style="width:${(r.strength * 100).toFixed(0)}%"></div></span>
      <span class="strength-val">${(r.strength * 100).toFixed(0)}%</span>`;

    tr.innerHTML = `
      <td><strong>${escapeHtml(r.pair)}</strong></td>
      <td>${fmtPrice(r.price)}</td>
      <td><span class="badge ${escapeHtml(r.action)}">${escapeHtml(r.action)}</span></td>
      <td>${strengthHtml}</td>
      <td>${fmtPrice(r.stop_loss)}</td>
      <td>${fmtPrice(r.take_profit)}</td>
      <td>${r.rr_ratio == null ? "-" : r.rr_ratio}</td>
      <td class="votes">
        <span class="b">B ${r.buy_votes}</span> &middot;
        <span class="s">S ${r.sell_votes}</span> &middot;
        <span class="n">N ${r.neutral_votes}</span>
      </td>
      <td class="reasons">${escapeHtml((r.reasons || []).join("; "))}</td>`;

    tr.addEventListener("click", () => openDetail(r));
    body.appendChild(tr);
  }
}

/* ---------- Strategy toggles ---------- */
function renderStrategyToggles() {
  const wrap = $("#strategy-toggles");
  wrap.innerHTML = "";
  state.strategies = state.allStrategies.slice();

  for (const name of state.allStrategies) {
    const label = document.createElement("label");
    label.className = "toggle";
    label.innerHTML = `<input type="checkbox" checked /> ${escapeHtml(name)}`;
    const box = label.querySelector("input");
    box.addEventListener("change", () => {
      if (box.checked) state.strategies.push(name);
      else state.strategies = state.strategies.filter((s) => s !== name);
      label.classList.toggle("off", !box.checked);
    });
    wrap.appendChild(label);
  }
}

/* ---------- Config fields ---------- */
function renderConfigFields() {
  const wrap = $("#config-fields");
  let html = '<div class="config-grid">';
  for (const [key, label, def] of CONFIG_FIELDS) {
    html += `
      <div class="config-item">
        <label for="cfg-${key}">${escapeHtml(label)}</label>
        <input id="cfg-${key}" type="number" step="any" value="${def}" />
      </div>`;
  }
  html += "</div>";
  wrap.innerHTML = html;
}

/* ---------- Category selection ---------- */
function setupCategory() {
  $$("#category button").forEach((btn) => {
    btn.addEventListener("click", () => {
      $$("#category button").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      state.category = btn.dataset.cat;
      const manual = $("#pairs").value.trim();
      if (!manual) runScan();
    });
  });
}

/* ---------- Auto refresh ---------- */
function setupAutoRefresh() {
  $("#auto-refresh").addEventListener("change", () => {
    clearInterval(state.autoRefreshTimer);
    state.autoRefreshTimer = null;
    const seconds = Number($("#auto-refresh").value);
    if (seconds > 0) {
      state.autoRefreshTimer = setInterval(runScan, seconds * 1000);
    }
  });
}

/* ---------- Detail modal ---------- */
function openDetail(result) {
  state.currentPair = result;
  $("#modal-title").textContent = `${result.pair} — ${result.action}`;
  renderRiskPanel(result);
  renderBreakdown(result);
  $("#json-view").textContent = JSON.stringify(result, null, 2);
  $("#modal").classList.remove("hidden");
  switchTab("chart");
  loadChart();
}

function closeModal() {
  $("#modal").classList.add("hidden");
  if (state.chart) {
    state.chart.remove();
    state.chart = null;
  }
}

function renderRiskPanel(r) {
  const values = [
    ["Action", r.action, r.action.toLowerCase()],
    ["Strength", `${(r.strength * 100).toFixed(0)}%`, r.action.toLowerCase()],
    ["Stop Loss", fmtPrice(r.stop_loss), r.action.toLowerCase()],
    ["Take Profit", fmtPrice(r.take_profit), r.action.toLowerCase()],
    ["Risk : Reward", r.rr_ratio == null ? "-" : `1 : ${r.rr_ratio}`, r.action.toLowerCase()],
    ["Buy Votes", r.buy_votes, "buy"],
    ["Sell Votes", r.sell_votes, "sell"],
    ["Neutral Votes", r.neutral_votes, "neutral"],
  ];
  $("#risk-panel").innerHTML = values
    .map(([label, value, cls]) => `
      <div class="risk-card">
        <div class="label">${escapeHtml(label)}</div>
        <div class="value ${escapeHtml(cls)}">${escapeHtml(value)}</div>
      </div>`)
    .join("");
}

function renderBreakdown(r) {
  const body = $("#breakdown-body");
  body.innerHTML = (r.signals || [])
    .map((s) => `
      <tr>
        <td><strong>${escapeHtml(s.strategy)}</strong></td>
        <td><span class="badge ${escapeHtml(s.action)}">${escapeHtml(s.action)}</span></td>
        <td>${(s.strength * 100).toFixed(0)}%</td>
        <td class="reasons-cell">${escapeHtml((s.reasons || []).join("; "))}</td>
      </tr>`)
    .join("");
}

function switchTab(name) {
  $$(".tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
  $("#tab-chart").classList.toggle("hidden", name !== "chart");
  $("#tab-breakdown").classList.toggle("hidden", name !== "breakdown");
  $("#tab-json").classList.toggle("hidden", name !== "json");
}

/* ---------- Chart ---------- */
async function loadChart() {
  const pair = state.currentPair.pair;
  const url = `/api/pair/${encodeURIComponent(pair)}/chart?interval=${$("#interval").value}&period=${$("#period").value}`;
  let data;
  try {
    data = await apiGet(url);
  } catch (err) {
    $("#chart").innerHTML = `<div class="error">Chart failed: ${escapeHtml(err.message)}</div>`;
    return;
  }
  state.chartData = data;
  drawChart();
}

function drawChart() {
  const container = $("#chart");
  container.innerHTML = "";
  if (state.chart) { state.chart.remove(); state.chart = null; }

  const d = state.chartData;
  const times = d.ohlcv.time.map((t) => new Date(t));

  const chart = LightweightCharts.createChart(container, {
    layout: { background: { type: "solid", color: "#161b22" }, textColor: "#8b949e" },
    grid: { vertLines: { color: "#21262d" }, horzLines: { color: "#21262d" } },
    timeScale: { timeVisible: true, secondsVisible: false },
    width: container.clientWidth || 900,
    height: 420,
  });
  state.chart = chart;

  const candleSeries = chart.addCandlestickSeries({
    upColor: "#2ea043", downColor: "#f85149",
    borderUpColor: "#2ea043", borderDownColor: "#f85149",
    wickUpColor: "#2ea043", wickDownColor: "#f85149",
  });
  const candles = d.ohlcv.time.map((t, i) => ({
    time: times[i].getTime() / 1000,
    open: d.ohlcv.open[i],
    high: d.ohlcv.high[i],
    low: d.ohlcv.low[i],
    close: d.ohlcv.close[i],
  }));
  candleSeries.setData(candles);

  const overlayColors = {
    ema_20: "#58a6ff",
    ema_50: "#d29922",
    "bb_20_2.0_upper": "#8b949e",
    "bb_20_2.0_lower": "#8b949e",
    "bb_20_2.0_middle": "#6e7681",
    ich_tenkan: "#f0883e",
    ich_kijun: "#bc8cff",
    ich_senkou_a: "#3fb950",
    ich_senkou_b: "#ff7b72",
  };

  for (const [key, values] of Object.entries(d.indicators)) {
    if (values.every((v) => v == null)) continue;
    const color = overlayColors[key];
    if (!color) continue; // only plot a curated set of overlays
    const points = [];
    for (let i = 0; i < values.length; i++) {
      if (values[i] != null) {
        points.push({ time: times[i].getTime() / 1000, value: values[i] });
      }
    }
    if (points.length < 2) continue;
    const line = chart.addLineSeries({
      color, lineWidth: 1, priceLineVisible: false, lastValueVisible: false,
    });
    line.setData(points);
  }

  window.addEventListener("resize", () => {
    if (state.chart) state.chart.applyOptions({ width: container.clientWidth || 900 });
  });
}

/* ---------- Modal wiring ---------- */
function setupModal() {
  $("#modal-close").addEventListener("click", closeModal);
  $("#modal").addEventListener("click", (e) => {
    if (e.target === $("#modal")) closeModal();
  });
  $$(".tab").forEach((tab) => {
    tab.addEventListener("click", () => switchTab(tab.dataset.tab));
  });
}

/* ---------- Init ---------- */
async function init() {
  setupCategory();
  setupAutoRefresh();
  setupModal();
  renderConfigFields();
  $("#btn-scan").addEventListener("click", runScan);
  $("#btn-refresh").addEventListener("click", runScan);
  $("#pairs").addEventListener("change", runScan);
  $("#interval").addEventListener("change", runScan);
  $("#period").addEventListener("change", runScan);

  try {
    const health = await apiGet("/api/health");
    state.allStrategies = health.strategies || [];
    renderStrategyToggles();
    $("#api-status").classList.add("online");
    $("#api-status").classList.remove("offline");
  } catch (err) {
    showError(`API unreachable: ${escapeHtml(err.message)}`);
    return;
  }

  try {
    await loadPairs();
    const manual = $("#pairs").value.trim();
    if (!manual) runScan();
  } catch (err) {
    showError(`Failed to load pairs: ${escapeHtml(err.message)}`);
  }
}

document.addEventListener("DOMContentLoaded", init);
