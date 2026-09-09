"""Tests for the market clock / session / calendar module (webapp/market.py)."""

from datetime import datetime, timezone

from webapp.market import SESSIONS, _utcnow, market_clock, rolling_calendar


def test_utcnow_is_timezone_aware():
    now = _utcnow()
    assert now.tzinfo is not None
    assert now.utcoffset() == timezone.utc.utcoffset(None)


def test_sessions_cover_classic_fx_sessions():
    names = [s[0] for s in SESSIONS]
    assert names == ["Sydney", "Tokyo", "London", "New York"]


def test_market_clock_shape():
    clock = market_clock()
    assert "utc_now" in clock
    assert "weekday" in clock
    assert "day_of_week" in clock
    assert "utc_hhmm" in clock
    assert "sessions" in clock
    assert "timeline" in clock
    assert "next_event" in clock
    assert len(clock["sessions"]) == 4
    assert clock["timeline"] == [
        "00:00", "03:00", "06:00", "09:00", "12:00", "15:00",
        "18:00", "21:00",
    ]


def test_market_clock_session_keys():
    clock = market_clock()
    for session in clock["sessions"]:
        assert set(session.keys()) == {
            "name", "open", "close", "color", "open_utc", "close_utc", "open_now",
        }
        assert session["open_utc"] == f"{session['open']:02d}:00"
        assert session["close_utc"] == f"{session['close']:02d}:00"


def test_session_open_flags_match_current_utc_time():
    """Each session's open_now flag must match the current UTC clock."""
    now = _utcnow()
    utc_minutes = now.hour * 60 + now.minute
    clock = market_clock()
    by_name = {s["name"]: s for s in clock["sessions"]}
    for name, open_h, close_h, _color in SESSIONS:
        if open_h < close_h:
            expected = open_h * 60 <= utc_minutes < close_h * 60
        else:  # wraps past midnight
            expected = utc_minutes >= open_h * 60 or utc_minutes < close_h * 60
        assert by_name[name]["open_now"] is expected, name


def test_market_never_fully_closed():
    """FX trades ~24/5: at least one session is always open on a weekday."""
    now = _utcnow()
    if now.weekday() < 5:
        clock = market_clock()
        assert any(s["open_now"] for s in clock["sessions"])


def test_session_wraparound_logic():
    """Sydney opens at 22:00 UTC and closes 07:00 UTC (past midnight)."""
    clock = market_clock()
    by_name = {s["name"]: s for s in clock["sessions"]}
    sydney = by_name["Sydney"]
    assert sydney["open"] == 22 and sydney["close"] == 7


def test_next_event_is_in_future_and_iso():
    clock = market_clock()
    if clock["next_event"] is not None:
        event_dt = datetime.fromisoformat(clock["next_event"]["dt_utc"])
        now = datetime.now(timezone.utc)
        assert event_dt.tzinfo is not None
        assert event_dt > now


def test_rolling_calendar_length_and_shape():
    rows = rolling_calendar(days=7)
    assert len(rows) > 0
    first = rows[0]
    assert set(first.keys()) == {
        "date", "weekday", "time_utc", "dt_utc", "currency", "event", "impact", "is_today",
    }
    assert first["impact"] == "high"
    assert first["time_utc"] == "13:00"


def test_rolling_calendar_sorted_and_upcoming():
    rows = rolling_calendar(days=7)
    dt_values = [r["dt_utc"] for r in rows]
    assert dt_values == sorted(dt_values)
    # Only events whose month matches one of the next 7 days' months appear,
    # so rows must be non-empty for at least a year-long window.
    assert len(rolling_calendar(days=400)) > len(rows)


def test_rolling_calendar_today_flag():
    rows = rolling_calendar(days=1)
    assert all(r["is_today"] for r in rows)


def test_rolling_calendar_all_rows_within_window():
    from datetime import date, timedelta

    today = date.today()
    for r in rolling_calendar(days=5):
        d = date.fromisoformat(r["date"])
        assert today <= d <= today + timedelta(days=4)
