"""Trading-session rules for TAIFEX index futures.

All datetimes are naive Asia/Taipei wall-clock (Shioaji delivers naive local time).

* Day session   08:45 – 13:45   -> trading date = same calendar day
* Night session 15:00 – 05:00(+1) -> trading date = NEXT trading day after the start day
  (Friday night belongs to Monday).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Iterable, Optional

DAY_START = time(8, 45)
DAY_END = time(13, 45)
NIGHT_START = time(15, 0)
NIGHT_END = time(5, 0)
SPOT_START = time(9, 0)
SPOT_END = time(13, 30)
# ticks stamped inside the closing minute (e.g. 13:45:00.xxx closing auction) still belong
# to the session; anything later is outside
GRACE = timedelta(seconds=59)


def is_trading_day(d: date, holidays: Iterable[date] = ()) -> bool:
    return d.weekday() < 5 and d not in set(holidays)


def next_trading_day(d: date, holidays: Iterable[date] = ()) -> date:
    hs = set(holidays)
    n = d + timedelta(days=1)
    while not is_trading_day(n, hs):
        n += timedelta(days=1)
    return n


def prev_trading_day(d: date, holidays: Iterable[date] = ()) -> date:
    hs = set(holidays)
    n = d - timedelta(days=1)
    while not is_trading_day(n, hs):
        n -= timedelta(days=1)
    return n


@dataclass(frozen=True)
class SessionInfo:
    kind: str  # "day" | "night"
    trading_date: date
    start: datetime
    end: datetime

    @property
    def key(self) -> str:
        return f"{self.trading_date.isoformat()}-{'D' if self.kind == 'day' else 'N'}"

    @property
    def label(self) -> str:
        return "日盤" if self.kind == "day" else "夜盤"

    @property
    def chart_date(self) -> date:
        """Calendar day the session starts on; 日全盤 = day session D + night session from D 15:00."""
        return self.start.date()

    def bar_index(self, dt: datetime, minutes: int) -> int:
        span = self.end - self.start
        n_bars = max(1, int(span.total_seconds() // (minutes * 60)))
        idx = int((dt - self.start).total_seconds() // (minutes * 60))
        return max(0, min(idx, n_bars - 1))

    def bar_start(self, dt: datetime, minutes: int) -> datetime:
        return self.start + timedelta(minutes=minutes * self.bar_index(dt, minutes))

    def n_bars(self, minutes: int) -> int:
        return max(1, int((self.end - self.start).total_seconds() // (minutes * 60)))


def day_session(d: date) -> SessionInfo:
    return SessionInfo("day", d, datetime.combine(d, DAY_START), datetime.combine(d, DAY_END))


def night_session(start_day: date, holidays: Iterable[date] = ()) -> SessionInfo:
    return SessionInfo(
        "night",
        next_trading_day(start_day, holidays),
        datetime.combine(start_day, NIGHT_START),
        datetime.combine(start_day + timedelta(days=1), NIGHT_END),
    )


def session_of(dt: datetime, holidays: Iterable[date] = ()) -> Optional[SessionInfo]:
    """Return the session a timestamp belongs to, or None (outside trading hours)."""
    hs = set(holidays)
    d = dt.date()
    t = dt.time()
    if is_trading_day(d, hs):
        s = day_session(d)
        if s.start <= dt <= s.end + GRACE:
            return s
        if t >= NIGHT_START:
            return night_session(d, hs)
    # early morning part of a night session that started yesterday
    y = d - timedelta(days=1)
    if is_trading_day(y, hs):
        s = night_session(y, hs)
        if dt <= s.end + GRACE:
            return s
    return None


def next_session(dt: datetime, holidays: Iterable[date] = ()) -> SessionInfo:
    """The next session starting strictly after dt (used for countdown while closed)."""
    hs = set(holidays)
    d = dt.date() - timedelta(days=1)
    for _ in range(15):
        if is_trading_day(d, hs):
            for s in (day_session(d), night_session(d, hs)):
                if s.start > dt:
                    return s
        d += timedelta(days=1)
    raise RuntimeError("no session found")  # pragma: no cover


def last_session(dt: datetime, holidays: Iterable[date] = ()) -> SessionInfo:
    """Current session if inside one, else the most recently finished one."""
    s = session_of(dt, holidays)
    if s:
        return s
    hs = set(holidays)
    d = dt.date()
    for _ in range(15):
        if is_trading_day(d, hs):
            for s in (night_session(d, hs), day_session(d)):
                if s.end <= dt:
                    return s
        d -= timedelta(days=1)
    raise RuntimeError("no session found")  # pragma: no cover


def spot_bar_index(dt: datetime, minutes: int = 5) -> Optional[int]:
    """Index of a TSE spot 5-minute bar from 09:00 (None outside 09:00–13:30)."""
    start = datetime.combine(dt.date(), SPOT_START)
    end = datetime.combine(dt.date(), SPOT_END)
    if dt < start or dt > end + GRACE:
        return None
    n = int((end - start).total_seconds() // (minutes * 60))
    return max(0, min(int((dt - start).total_seconds() // (minutes * 60)), n - 1))
