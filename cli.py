"""Command-line interface for the Forex Signal Scanner."""

import argparse
import json
import random
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from scanner import ALL_PAIRS, CROSS_PAIRS, EXOTIC_PAIRS, MAJOR_PAIRS, Scanner
from scanner.data_provider import fetch_many

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table

    HAS_RICH = True
except ImportError:  # pragma: no cover
    HAS_RICH = False


BANNER = r"""
  ______                     _____            _
 |  ____|                   / ____|          (_)
 | |__  ___  ___ _ __ ___  | (___   ___ _ __  _  __ _
 |  __|/ _ \/ _ \ '_ ` _ \  \___ \ / _ \ '_ \| |/ _` |
 | |__| (_) |  __/ | | | | | ____) |  __/ | | | | (_| |
 |_____\___/ \___|_| |_| |_||_____/ \___|_| |_|_|\__,_|
        Forex Signal Generator & Market Scanner
"""


def make_synthetic_data(pair: str, n: int = 500, seed: int = None) -> pd.DataFrame:
    """
    Generate realistic-looking synthetic OHLCV data for demo/testing
    when no internet connection or API access is available.
    """
    if seed is not None:
        random.seed(seed)
        np.random.seed(seed)

    base_price = 1.08 if "USD" in pair and not pair.startswith("USD") else 0.9
    if pair.endswith("JPY"):
        base_price = 145.0
    elif pair == "USDJPY":
        base_price = 150.0
    elif pair.startswith("USD"):
        base_price = 0.9
    elif pair in ("USDTRY",):
        base_price = 32.0

    vol = base_price * 0.0008  # ~8 pips at 4 digits
    if pair.endswith("JPY") or pair == "USDJPY":
        vol = base_price * 0.0008

    drift = 0.0
    dates = pd.date_range(end=datetime.now(timezone.utc), periods=n, freq="h")

    # Regime-switching random walk (trending + ranging phases)
    returns = []
    regime = 1
    for i in range(n):
        if i % 120 == 0:
            regime = random.choice([-1, 0, 1]) * random.uniform(0.4, 1.2)
        r = np.random.normal(drift + regime * 0.0002, vol / base_price)
        returns.append(r)

    closes = base_price * np.exp(np.cumsum(returns))
    opens = np.concatenate([[closes[0]], closes[:-1]])
    highs = np.maximum(opens, closes) * (1 + np.abs(np.random.normal(0, 0.0004, n)))
    lows = np.minimum(opens, closes) * (1 - np.abs(np.random.normal(0, 0.0004, n)))
    volumes = np.random.randint(500, 5000, n).astype(float)

    return pd.DataFrame(
        {"Open": opens, "High": highs, "Low": lows, "Close": closes, "Volume": volumes},
        index=dates,
    )


def format_signal(action: str) -> str:
    """Return colored/plain text for an action."""
    if action == "BUY":
        return "[bold green]BUY[/bold green]" if HAS_RICH else "BUY"
    if action == "SELL":
        return "[bold red]SELL[/bold red]" if HAS_RICH else "SELL"
    return "[yellow]NEUTRAL[/yellow]" if HAS_RICH else "NEUTRAL"


def build_table(results, console: Console) -> Table:
    """Build a rich table of scan results sorted by signal strength."""
    table = Table(title="Forex Market Scan", show_lines=True)
    table.add_column("Pair", style="cyan", justify="left")
    table.add_column("Price", justify="right")
    table.add_column("Signal", justify="center")
    table.add_column("Strength", justify="right")
    table.add_column("SL", justify="right")
    table.add_column("TP", justify="right")
    table.add_column("Votes (B/S/N)", justify="center")
    table.add_column("Key Reasons", style="dim", max_width=50)

    def sort_key(r):
        order = {"BUY": 2, "SELL": 1, "NEUTRAL": 0}
        return (order[r.overall.action], r.overall.strength)

    for res in sorted(results, key=sort_key, reverse=True):
        reasons = "; ".join(res.overall.reasons[:3])
        sl = f"{res.stop_loss:.5f}" if res.stop_loss is not None else "-"
        tp = f"{res.take_profit:.5f}" if res.take_profit is not None else "-"
        table.add_row(
            res.pair,
            f"{res.price:.5f}",
            format_signal(res.overall.action),
            f"{res.overall.strength:.2f}",
            sl,
            tp,
            f"{res.buy_votes}/{res.sell_votes}/{res.neutral_votes}",
            reasons,
        )
    return table


def print_detail(result, console: Console):
    """Print a detailed per-pair signal breakdown."""
    if not HAS_RICH:
        print(json.dumps(result.to_dict(), indent=2))
        return

    lines = [f"Price: [bold]{result.price:.5f}[/bold]"]
    lines.append(f"Overall: {format_signal(result.overall.action)} "
                 f"(strength [bold]{result.overall.strength:.2f}[/bold])")
    if result.stop_loss is not None and result.take_profit is not None:
        lines.append(f"Stop Loss: [bold]{result.stop_loss:.5f}[/bold] | "
                     f"Take Profit: [bold]{result.take_profit:.5f}[/bold] | "
                     f"R:R [bold]{result.rr_ratio}[/bold]")
    lines.append("")
    lines.append("Individual strategies:")
    for name, sig in result.individual:
        action_txt = format_signal(sig.action)
        lines.append(f"  {action_txt:<14} {name:<24} strength={sig.strength:.2f}")
        for r in sig.reasons:
            lines.append(f"      [dim]- {r}[/dim]")
    console.print(Panel("\n".join(lines), title=f"[bold]{result.pair}[/bold]"))


def run_scan(pairs, interval, period, verbose=False, detail=False, json_out=False):
    """Fetch data, run the scanner, and present results."""
    console = Console()
    scanner = Scanner()

    print(BANNER)
    console.print(f"[bold]Scanning {len(pairs)} pairs[/bold] "
                  f"(interval={interval}, period={period})\n")

    data = fetch_many(pairs, interval=interval, period=period)

    available = {k: v for k, v in data.items() if v is not None}
    failed = [k for k, v in data.items() if v is None]

    if not available:
        console.print("[bold red]No data available. Try the demo mode: "
                      "python cli.py --demo[/bold red]")
        sys.exit(1)

    results = scanner.scan_many(available)

    if failed:
        console.print(f"[yellow]Could not fetch data for: {', '.join(failed)}[/yellow]\n")

    if json_out:
        print(json.dumps([r.to_dict() for r in results], indent=2))
        return

    console.print(build_table(results, console))

    if detail:
        console.print("\n[bold]Detailed analysis:[/bold]")
        for r in results:
            print_detail(r, console)

    # Summary
    buys = [r for r in results if r.overall.action == "BUY"]
    sells = [r for r in results if r.overall.action == "SELL"]
    console.print(
        Panel(
            f"[green]{len(buys)} BUY[/green] | [red]{len(sells)} SELL[/red] | "
            f"[yellow]{len(results) - len(buys) - len(sells)} NEUTRAL[/yellow] "
            f"of {len(results)} pairs scanned",
            title="Summary",
        )
    )


def run_demo():
    """Run the scanner against synthetic data (offline demo)."""
    console = Console()
    scanner = Scanner()

    print(BANNER)
    console.print("[bold]DEMO MODE[/bold] - using synthetic data "
                  "(no internet required)\n")

    pairs = MAJOR_PAIRS + ["EURJPY", "GBPJPY", "AUDJPY"]
    data = {}
    for i, pair in enumerate(pairs):
        data[pair] = make_synthetic_data(pair, seed=100 + i)

    results = scanner.scan_many(data)
    console.print(build_table(results, console))

    console.print("\n[bold]Detailed analysis (top signals):[/bold]")
    order = {"BUY": 2, "SELL": 1, "NEUTRAL": 0}
    top = sorted(results, key=lambda r: (order[r.overall.action], r.overall.strength), reverse=True)[:4]
    for r in top:
        print_detail(r, console)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="forex-scanner",
        description="Forex Signal Generator & Market Scanner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Example:\n"
               "  python cli.py                    # scan major pairs (1h)\n"
               "  python cli.py --interval 4h      # scan on 4-hour candles\n"
               "  python cli.py --pairs EURUSD,GBPJPY --period 3mo\n"
               "  python cli.py --demo             # offline synthetic demo\n"
               "  python cli.py --detail --json    # detailed JSON output",
    )
    parser.add_argument(
        "--pairs",
        default=",".join(MAJOR_PAIRS),
        help="Comma-separated list of pairs (e.g. EURUSD,GBPUSD)",
    )
    parser.add_argument("--interval", default="1h",
                        choices=["1m", "5m", "15m", "30m", "1h", "4h", "1d"],
                        help="Candle interval (default: 1h)")
    parser.add_argument("--period", default="1mo",
                        choices=["5d", "1mo", "3mo", "6mo", "1y", "2y", "5y"],
                        help="Lookback period (default: 1mo)")
    parser.add_argument("--category", default=None,
                        choices=["major", "cross", "exotic", "all"],
                        help="Scan a predefined category of pairs")
    parser.add_argument("--demo", action="store_true",
                        help="Run offline demo with synthetic data")
    parser.add_argument("--detail", action="store_true",
                        help="Print per-strategy detail for each pair")
    parser.add_argument("--json", action="store_true",
                        help="Output results as JSON")
    parser.add_argument("--verbose", action="store_true",
                        help="Verbose output (strategy errors etc.)")

    args = parser.parse_args(argv)

    if args.demo:
        run_demo()
        return

    if args.category:
        mapping = {
            "major": MAJOR_PAIRS,
            "cross": CROSS_PAIRS,
            "exotic": EXOTIC_PAIRS,
            "all": ALL_PAIRS,
        }
        pairs = mapping[args.category]
    else:
        pairs = [p.strip().upper() for p in args.pairs.split(",") if p.strip()]

    if not pairs:
        parser.error("No currency pairs specified")

    run_scan(pairs, args.interval, args.period,
             verbose=args.verbose, detail=args.detail, json_out=args.json)


if __name__ == "__main__":
    main()
