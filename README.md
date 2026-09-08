# 📈 Forex Signal Generator & Market Scanner

A Python-based market scanner that fetches live forex OHLCV data, computes
technical indicators, runs multiple trading strategies, and aggregates the
results into **BUY / SELL / NEUTRAL** signals for each currency pair.

> ⚠️ **Disclaimer**: This tool is for **educational and research purposes only**.
> It does **not** constitute financial advice. Forex trading involves substantial
> risk of loss. Always do your own research and consult a licensed financial
> advisor before trading.

---

## Features

- **Live data** via [yfinance](https://github.com/ranaroussi/yfinance) (free, no API key)
- **8 built-in strategies**:
  | Strategy | Logic |
  |---|---|
  | MA Crossover | EMA fast/slow golden & death crosses |
  | RSI Mean Reversion | Buy oversold / sell overbought |
  | MACD | Line/signal crosses + histogram momentum |
  | Bollinger Bounce | Band touches with %b confirmation |
  | Stochastic | %K/%D crosses in overbought/oversold zones |
  | Trend Continuation | ADX filter + EMA50 trend direction |
  | Support / Resistance | ZigZag swing points + level testing |
  | Ichimoku Cloud | TK cross + price/cloud position + chikou confirmation |
- **Consensus engine** — requires 2+ aligned signals before firing a trade signal
- **ATR-based risk management** — auto-computed Stop Loss / Take Profit and R:R ratio for every BUY/SELL signal
- **Rich CLI output** — color-coded tables and per-strategy breakdowns
- **Offline demo mode** — synthetic data, no internet needed
- **JSON output** — easy to pipe into other tools
- **Predefined pair categories** — majors, crosses, exotics, all

---

## Installation

Requires **Python 3.9+**.

```bash
cd forex-scanner
pip install -r requirements.txt
```

---

## Usage

### Scan the major pairs (default)

```bash
python cli.py
```

### Scan on a different timeframe

```bash
python cli.py --interval 4h
python cli.py --interval 15m --period 5d
```

### Scan specific pairs

```bash
python cli.py --pairs EURUSD,GBPJPY,AUDUSD --interval 1h
```

### Scan a category

```bash
python cli.py --category major
python cli.py --category cross
python cli.py --category all
```

### Per-strategy detail

```bash
python cli.py --detail
```

### Machine-readable JSON output

```bash
python cli.py --json
```

### Offline demo (no internet)

```bash
python cli.py --demo
```

---

## Example output

```
┌──────────┬───────────┬─────────┬──────────┬──────────┬────────┬────────────┬──────────────────────────┐
│ Pair     │    Price  │ Signal  │ Strength │ SL       │ TP     │ R:R        │ Key Reasons               │
├──────────┼───────────┼─────────┼──────────┼──────────┼────────┼────────────┼──────────────────────────┤
│ EURUSD   │ 1.08432  │ BUY     │ 0.62     │ 1.08210  │ 1.08860│ 1.67       │ 4/8 strategies bullish    │
│ GBPUSD   │ 1.27115  │ SELL    │ 0.58     │ 1.27380  │ 1.26690│ 1.67       │ 4/8 strategies bearish    │
│ USDJPY   │ 150.422  │ NEUTRAL │ 0.11     │ -        │ -      │ -          │ No clear consensus        │
└──────────┴───────────┴─────────┴──────────┴──────────┴────────┴────────────┴──────────────────────────┘
```

The **Stop Loss** (SL) and **Take Profit** (TP) are placed `sl_atr_mult` (default 1.5×)
and `tp_atr_mult` (default 2.5×) away from entry price using the latest ATR(14).
The **R:R ratio** is `reward / risk` and only appears for actionable signals.

---

## Web app (FastAPI)

The same analysis engine is exposed as a tabbed single-page web app with
**7 tabs**, all running against the FastAPI backend:

| Tab | What it does |
|---|---|
| **Scanner** | Live consensus scan across all pairs with filters, strategy toggles, and auto-refresh |
| **Chart** | Candlestick chart with EMA / Bollinger / Ichimoku overlays + risk panel |
| **Demo Trading** | Paper-trading: open/close positions, live P&L, equity, monthly history |
| **OANDA** | OANDA-ready account/order view (falls back to paper mode until API keys are set) |
| **Bot** | Strategy weights, enable/pause/resume toggles, run state, and signal log |
| **Backtest** | Replay historical candles, run a strategy, view stats + equity curve |
| **Market Clock** | Session times, market open/closed status, and upcoming economic events |

### Run locally

```bash
pip install -r requirements.txt
python run_web.py                 # -> http://127.0.0.1:8000
python run_web.py --port 8080     # custom port
```

### API endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/` | Tabbed SPA dashboard UI |
| GET | `/api/health` | Status + enabled strategy names |
| GET | `/api/pairs` | Pairs grouped by Major / Cross / Exotic |
| GET | `/api/scan` | Run a scan; returns `ScanResult.to_dict()` per pair |
| GET | `/api/pair/{pair}/chart` | OHLCV + indicator series for charting |
| GET | `/api/clock` | Market clock: UTC time, session status, session timeline |
| GET | `/api/calendar` | Upcoming economic events for the next N days |
| GET | `/api/backtest` | Backtest a strategy over historical candles (stats + equity curve) |
| GET | `/api/demo/account` | Paper-trading account, open positions, history |
| GET | `/api/demo/positions` | Open paper positions |
| POST | `/api/demo/order` | Open a paper trade `{pair, side, units}` |
| POST | `/api/demo/close` | Close a paper trade by position id (e.g. `T0001`) |
| POST | `/api/demo/reset` | Reset the paper account |
| GET | `/api/demo/monthly` | Monthly P&L history |
| GET | `/api/oanda-account` | OANDA account (paper fallback until configured) |
| POST | `/api/oanda-order` | Place an OANDA market order |
| POST | `/api/oanda-close` | Close an OANDA position |
| GET | `/api/oanda-prices` | Live quotes for requested pairs |
| GET | `/api/bot-state` | Bot config: enabled strategies, weights, run state, log |
| POST | `/api/bot-state` | Bot actions: `save_config` / `reset` / `pause_strategy` / `resume_strategy` / `close_trade` |
| POST | `/api/bot-run` | Trigger a bot run cycle |

`/api/scan` accepts `pairs` (comma-separated), `interval`, `period`,
`strategies` (comma-separated names to filter), and any engine config key
(`ema_fast`, `sl_atr_mult`, `adx_threshold`, ...).

Example:

```bash
curl "http://127.0.0.1:8000/api/scan?pairs=EURUSD,GBPUSD&interval=1h&period=1mo"
```

### Deploy to Vercel

The project is configured for serverless deployment:

```bash
# 1. Install Vercel CLI (once)
npm i -g vercel

# 2. From the project root
vercel --prod
```

- [`vercel.json`](vercel.json) routes all traffic to the ASGI app via the
  catch-all rewrite to `api/index.py`, so every route works on Vercel.
- `webapp/static/` is bundled into the serverless function so the dashboard
  UI and assets are served from the same origin.
- yfinance runs inside the function; scans hit the live Yahoo Finance API.
  Keep auto-refresh moderate to stay within free-tier rate limits.
- CORS is not needed — frontend and API share one origin on Vercel.

---

## Project structure

```
forex-scanner/
├── cli.py                  # Command-line entry point
├── run_web.py              # Web app launcher (uvicorn)
├── requirements.txt        # CLI + web dependencies
├── requirements-web.txt    # Web-only deps (fastapi, uvicorn)
├── README.md
├── vercel.json             # Vercel serverless config (catch-all -> api/index.py)
├── api/
│   └── index.py            # Vercel ASGI entry (imports webapp.app)
├── webapp/
│   ├── __init__.py
│   ├── app.py              # FastAPI app: all /api routes (7-tab SPA backend)
│   ├── bot.py              # Bot engine: strategy weights, run state, signal log (RLock)
│   ├── trading.py          # PaperTrader: demo positions, history, monthly P&L
│   ├── backtest.py         # Backtest replay: candles -> stats + equity curve
│   ├── market.py           # Market clock: sessions, calendar events
│   ├── oanda.py            # OANDA-ready client (paper fallback until keys set)
│   ├── cache.py            # Thread-safe TTL cache for Yahoo rate-limit protection
│   └── static/
│       ├── index.html      # Tabbed SPA shell (7 tabs)
│       ├── style.css       # Dark trading theme
│       └── app.js          # Tabs + scanner/chart/demo/oanda/bot/backtest/clock logic
├── scanner/
│   ├── __init__.py
│   ├── data_provider.py    # yfinance data fetching
│   ├── indicators.py       # RSI, MACD, Bollinger, ATR, ADX, Stoch, ZigZag, Ichimoku...
│   ├── strategies.py       # 8 trading strategies
│   └── engine.py           # Indicator computation + consensus aggregation + SL/TP
└── tests/
    ├── conftest.py         # Shared fixtures (synthetic OHLCV)
    ├── test_indicators.py  # Indicator unit tests
    ├── test_strategies.py  # Strategy unit tests
    └── test_engine.py      # Engine / consensus / risk tests
```

## Running the tests

```bash
python -m pytest tests/ -v
```

---

## How it works

1. **Fetch** — pull OHLCV candles for each pair (`yfinance`)
2. **Indicators** — compute EMA, RSI, MACD, Bollinger, Stochastic, ADX, ZigZag, Ichimoku
3. **Strategies** — each strategy returns a `Signal(action, strength, reasons)`
4. **Consensus** — aggregate votes; require ≥2 aligned strategies for BUY/SELL
5. **Risk** — derive Stop Loss / Take Profit from ATR(14) for actionable signals
6. **Report** — rich table sorted by signal strength + optional JSON

---

## Caveats

- yfinance forex data is delayed and not broker-grade. Use it for research only.
- The scanner looks at the **last closed candle**; backfill warm-up is automatic.
- Indicators use Wilder-style smoothing where applicable (RSI, ATR, ADX).
- Pip distances in the S/R strategy assume 4-digit quoting (adjust for JPY).

---

## License

MIT — use at your own risk. Not financial advice.
