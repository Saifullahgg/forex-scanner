"""
Market sessions clock and a small high-impact news calendar.

The clock computes the four classic FX sessions (Sydney, Tokyo, London, New
York) as UTC time ranges and marks which are currently open. The calendar is a
static, low-volume list of high-impact events so the Clock / Bot tabs have
real data without needing a paid news feed. Dates are rolling (recomputed per
request relative to "today") so the demo always shows upcoming events.
"""

from datetime import date, datetime, timedelta, timezone
from typing import Dict, List


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# (name, open_hour_utc, close_hour_utc, color)
SESSIONS = [
    ("Sydney", 22, 7, "#4488ff"),
    ("Tokyo", 0, 9, "#ffd700"),
    ("London", 7, 16, "#00ff88"),
    ("New York", 12, 21, "#ff4466"),
]

# Roughly quarterly high-impact events per currency.
_EVENTS = [
    ("FOMC Policy Decision", "USD", 3),
    ("FOMC Policy Decision", "USD", 6),
    ("FOMC Policy Decision", "USD", 9),
    ("FOMC Policy Decision", "USD", 12),
    ("Non-Farm Payrolls", "USD", 3),
    ("Non-Farm Payrolls", "USD", 6),
    ("Non-Farm Payrolls", "USD", 9),
    ("Non-Farm Payrolls", "USD", 12),
    ("ECB Interest Rate Decision", "EUR", 2),
    ("ECB Interest Rate Decision", "EUR", 5),
    ("ECB Interest Rate Decision", "EUR", 8),
    ("ECB Interest Rate Decision", "EUR", 11),
    ("Bank of England Rate Decision", "GBP", 2),
    ("Bank of England Rate Decision", "GBP", 5),
    ("Bank of England Rate Decision", "GBP", 8),
    ("Bank of England Rate Decision", "GBP", 11),
    ("BOJ Policy Rate", "JPY", 1),
    ("BOJ Policy Rate", "JPY", 4),
    ("BOJ Policy Rate", "JPY", 7),
    ("BOJ Policy Rate", "JPY", 10),
    ("RBA Cash Rate", "AUD", 2),
    ("RBA Cash Rate", "AUD", 5),
    ("RBA Cash Rate", "AUD", 8),
    ("RBA Cash Rate", "AUD", 11),
    ("BOC Rate Decision", "CAD", 1),
    ("BOC Rate Decision", "CAD", 4),
    ("BOC Rate Decision", "CAD", 7),
    ("BOC Rate Decision", "CAD", 10),
    ("RBNZ Official Cash Rate", "NZD", 2),
    ("RBNZ Official Cash Rate", "NZD", 5),
    ("RBNZ Official Cash Rate", "NZD", 8),
    ("RBNZ Official Cash Rate", "NZD", 11),
    ("SNB Rate Decision", "CHF", 3),
    ("SNB Rate Decision", "CHF", 6),
    ("SNB Rate Decision", "CHF", 9),
    ("SNB Rate Decision", "CHF", 12),
]


def market_clock() -> dict:
    """Return the current UTC time and open/closed session info."""
    now = _utcnow()
    utc_minutes = now.hour * 60 + now.minute

    sessions = []
    for name, open_h, close_h, color in SESSIONS:
        if open_h < close_h:
            is_open = open_h * 60 <= utc_minutes < close_h * 60
        else:  # wraps past midnight
            is_open = utc_minutes >= open_h * 60 or utc_minutes < close_h * 60
        sessions.append(
            {
                "name": name,
                "open": open_h,
                "close": close_h,
                "color": color,
                "open_utc": f"{open_h:02d}:00",
                "close_utc": f"{close_h:02d}:00",
                "open_now": is_open,
            }
        )

    # 24h timeline: label every 3 hours in UTC.
    timeline = [f"{h:02d}:00" for h in range(0, 24, 3)]
    next_event = None
    for event in rolling_calendar(days=7):
        if event["dt_utc"] > now.isoformat():
            next_event = event
            break

    return {
        "utc_now": now.isoformat(),
        "weekday": now.strftime("%A"),
        "day_of_week": now.weekday(),
        "utc_hhmm": f"{now.hour:02d}:{now.minute:02d}",
        "sessions": sessions,
        "timeline": timeline,
        "next_event": next_event,
    }


def rolling_calendar(days: int = 7) -> List[dict]:
    """Rolling high-impact calendar from today for the next N days."""
    today = date.today()
    rows: List[dict] = []
    for i in range(days):
        day = today + timedelta(days=i)
        weekday = day.strftime("%A")
        for title, currency, month in _EVENTS:
            if month != day.month:
                continue
            event_dt = datetime(
                day.year, day.month, day.day, 13, 0, tzinfo=timezone.utc
            )
            rows.append(
                {
                    "date": day.isoformat(),
                    "weekday": weekday,
                    "time_utc": "13:00",
                    "dt_utc": event_dt.isoformat(),
                    "currency": currency,
                    "event": title,
                    "impact": "high",
                    "is_today": i == 0,
                }
            )
    rows.sort(key=lambda r: r["dt_utc"])
    return rows
