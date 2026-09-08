# Forex Scanner Web App — User Guide

How to use the dashboard, understand the signals, and get the most out of the 8-strategy consensus engine.

---

## 1. Opening the app

**Live on Vercel:** open `https://forex-scanner.vercel.app` in your browser.
(If you see a Vercel login page, you need to disable Deployment Protection: Vercel dashboard → project `forex-scanner` → Settings → Deployment Protection → turn off Vercel Authentication.)

**Run locally (optional):**
```bash
cd C:\Users\DELL\Desktop\forex-scanner
pip install -r requirements-web.txt
python run_web.py
```
Then open `http://127.0.0.1:8000`.

---

## 2. Dashboard layout

| Area | What it does |
|---|---|
| **Top bar** | App name, API status dot (green = connected), last scan time, **Refresh** button |
| **Left sidebar — Scan Settings** | Interval, period, pair category, manual pairs, auto-refresh, **Run Scan** button |
| **Left sidebar — Strategy Settings** | On/off toggles for the 8 strategies + 15 risk/config fields |
| **Main area — Market Scan** | Results table: one row per pair |

On first load, the app checks the API, loads all 36 pairs, and **auto-runs a scan** of the default category (Major).

---

## 3. Scan Settings (sidebar, top card)

### Interval — timeframe of each candle
| Option | Best for |
|---|---|
| `1m`, `5m`, `15m` | Scalping / intraday |
| `30m`, `1h` | Day trading |
| `4h`, `1d` | Swing / position trading |

> Signals change as the timeframe changes — always pick the one matching your trading style. `1h` is the default.

### Period — how much history to analyze
`5d`, `1mo` (default), `3mo`, `6mo`, `1y`, `2y`, `5y`.
Longer periods = more context for S/R levels and Ichimoku, but slower to fetch.

### Pair category
- **Major** — 7 pairs (EURUSD, GBPUSD, USDJPY, …) — most liquid, most reliable data
- **Cross** — 21 pairs (EURGBP, GBPJPY, …)
- **Exotic** — 8 pairs (USDTRY, EURTRY, …) — sparser Yahoo data
- **All** — all 36

### Pairs (manual override)
Type comma-separated pairs to scan only those, e.g. `EURUSD,GBPUSD,USDJPY`.
**This overrides the category selection.** Leave it empty to use the category.

### Auto refresh
Off / 1 min / 5 min (default) / 10 min / 30 min — auto re-scans on a timer. Handy for watching live.

### Run Scan
Executes the scan with the current settings. The **Refresh** button in the top bar does the same.

---

## 4. Reading the results table

| Column | Meaning |
|---|---|
| **Pair** | Currency pair (click the row for full detail) |
| **Price** | Latest price (5 decimals) |
| **Signal** | **BUY** (green), **SELL** (red), or **NEUTRAL** (yellow) — the consensus action |
| **Strength** | 0.0 – 1.0 how confident the consensus is (weighted by each strategy's vote strength) |
| **SL** | Stop-loss level (ATR-based risk management) |
| **TP** | Take-profit level |
| **R:R** | Risk-to-reward ratio (TP distance ÷ SL distance) |
| **Votes** | e.g. `3B / 2S / 3N` → 3 strategies bullish, 2 bearish, 3 neutral |
| **Key Reasons** | Short summary, e.g. `3/8 strategies bullish` |

**How to pick winners:**
- Prefer **BUY/SELL** with **strength ≥ 0.6**.
- More votes on your side = stronger consensus (e.g. `5B/0S/3N` beats `3B/2S/3N`).
- Only trade pairs with a sensible **R:R ≥ 1.5** (the default TP/SL setup gives ~2.5 ATR vs 1.5 ATR).

---

## 5. Detail panel (click any row)

A modal opens with 3 tabs:

### Tab 1 — Chart
- Candlestick chart (TradingView Lightweight Charts) with volume.
- Indicator overlays: **EMA 20** (blue), **EMA 50** (gold), **Bollinger Bands** (grey), **Ichimoku** (tenkan orange, kijun purple, cloud green/red).
- The last candle is where the signal was generated — check it visually against the overlays.

### Tab 2 — Strategy Breakdown
- **Risk panel** — 8 cards: current price, action, strength, votes, SL, TP, R:R, and candle count.
- **Individual strategy signals** — each of the 8 strategies with its own action, strength, and the *reasons* it fired (e.g. `RSI(14) = 42.1 — neutral zone`, `Bullish %K cross below 30`). This tells you *why* the consensus is what it is.

### Tab 3 — Raw JSON
The full API response for that pair — useful for developers or logging.

---

## 6. Strategy Settings (sidebar, bottom card)

### Strategy toggles
Turn strategies on/off. The consensus (BUY/SELL/NEUTRAL) is computed **only from enabled strategies**. Examples:
- Want only trend strategies? Keep **MA Crossover**, **Trend Continuation**, **Ichimoku Cloud** on; turn off the mean-reversion ones.
- Compare: run with all 8, then with only momentum ones — see how the signal changes.

### Risk & Config fields (the 15 knobs)
| Field | Default | What it does |
|---|---|---|
| EMA Fast | 20 | Fast EMA period (MA Crossover) |
| EMA Slow | 50 | Slow EMA period (MA Crossover) |
| RSI Period | 14 | RSI lookback (RSI Mean Reversion) |
| MACD Fast / Slow / Signal | 12 / 26 / 9 | MACD parameters |
| BB Period / Std Dev | 20 / 2.0 | Bollinger Bands |
| Stoch %K / %D | 14 / 3 | Stochastic oscillator |
| ADX Period / Threshold | 14 / 25.0 | Trend strength (Trend Continuation) |
| ZigZag Dev % | 0.8 | S/R pivot sensitivity — lower = more levels (Support / Resistance) |
| SL ATR Multiplier | 1.5 | Stop-loss distance in ATR units |
| TP ATR Multiplier | 2.5 | Take-profit distance in ATR units (drives R:R) |

> Change SL/TP multipliers to match your risk appetite. E.g. SL 2.0 / TP 3.0 for wider stops with bigger targets.

---

## 7. Recommended workflow (daily)

1. Open the app, set **Interval** to your trading timeframe.
2. Start with **Major** pairs (cleanest data).
3. Click **Run Scan**.
4. Scan the table for **BUY/SELL** with **strength ≥ 0.6** and **R:R ≥ 1.5**.
5. Click those rows → check the **Chart** tab (is price respecting the EMA/Bollinger setup?) and **Breakdown** tab (are the reasons sensible?).
6. Only trade pairs where the chart agrees with the breakdown.
7. Turn on **Auto refresh (5 min)** if you're watching live.
8. When the market regime changes, flip strategy toggles — e.g. in a strong trend, disable mean-reversion strategies.

---

## 8. Common questions

**Why is a pair NEUTRAL?** Fewer than half the enabled strategies agree, or their strengths are weak (e.g. ADX low = ranging market).

**Why does the same pair give different signals on 1h vs 4h?** Different timeframes have different trends — that's normal and expected.

**Why is an exotic pair missing / erroring?** Yahoo has sparse or no data for some exotics. Use a shorter period (`1mo`) or stick to major/cross.

**Is the app real-time?** It fetches live Yahoo data on each scan. Auto-refresh keeps it current. There's a 5-minute server cache to avoid Yahoo rate limits — scans are instant after the first one per pair.

**Can I share the link?** Only after you disable Deployment Protection in Vercel (see step 1).
