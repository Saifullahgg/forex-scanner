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

## Project structure

```
forex-scanner/
├── cli.py                  # Command-line entry point
├── requirements.txt
├── README.md
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
