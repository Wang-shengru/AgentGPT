"""K-bar reconstruction from landed ticks (never from broker K lines).

Bars are aligned to the session start (day 08:45, night 15:00). A tick stamped in the
closing minute (13:45:xx / 05:00:xx) is folded into the last bar of the session.
``tf`` is minutes (5, 60) or ``"S"`` for one bar per session (日/夜K).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from typing import Iterable, List, Optional, Tuple, Union

from .session import SessionInfo, session_of
from .ticks import BUY, SELL, Tick

TF = Union[int, str]


@dataclass(slots=True)
class Bar:
    t: datetime  # bar start (Taipei wall clock)
    o: float
    h: float
    l: float
    c: float
    v: int = 0
    buy_cnt: int = 0
    sell_cnt: int = 0
    buy_vol: int = 0
    sell_vol: int = 0
    session: str = ""  # SessionInfo.key
    closed: bool = False
    code: str = ""  # contract code, e.g. TXFK6 (rollover marker)

    def add(self, t: Tick) -> None:
        px = t.close
        self.h = max(self.h, px)
        self.l = min(self.l, px)
        self.c = px
        self.v += t.volume
        if t.tick_type == BUY:
            self.buy_cnt += 1
            self.buy_vol += t.volume
        elif t.tick_type == SELL:
            self.sell_cnt += 1
            self.sell_vol += t.volume

    def to_json(self) -> dict:
        d = asdict(self)
        d["t"] = epoch_local(self.t)
        return d


def epoch_local(dt: datetime) -> int:
    """Taipei wall-clock encoded as UTC epoch seconds (what the chart expects)."""
    from datetime import timezone

    return int(dt.replace(tzinfo=timezone.utc).timestamp())


class BarSeries:
    """Ordered bars of one timeframe for one product, across sessions."""

    def __init__(self, tf: TF, holidays: Iterable[date] = (), max_bars: int = 20000):
        self.tf = tf
        self.holidays = frozenset(holidays)
        self.bars: List[Bar] = []
        self.max_bars = max_bars

    def _bar_start(self, s: SessionInfo, dt: datetime) -> datetime:
        if self.tf == "S":
            return s.start
        return s.bar_start(dt, int(self.tf))

    def on_tick(self, t: Tick, s: Optional[SessionInfo] = None) -> Tuple[Optional[Bar], bool]:
        """Feed one tick. Returns (current bar, opened_new_bar). Ignores simtrade/out-of-session."""
        if t.simtrade:
            return None, False
        s = s or session_of(t.dt, self.holidays)
        if s is None:
            return None, False
        start = self._bar_start(s, t.dt)
        last = self.bars[-1] if self.bars else None
        if last is not None and last.t == start:
            last.add(t)
            return last, False
        if last is not None and start < last.t:
            return None, False  # out-of-order tick older than current bar: drop
        if last is not None:
            last.closed = True
        b = Bar(start, t.close, t.close, t.close, t.close, 0, session=s.key, code=t.code)
        b.add(t)
        self.bars.append(b)
        if len(self.bars) > self.max_bars:
            del self.bars[: len(self.bars) - self.max_bars]
        return b, True

    def close_through(self, now: datetime) -> None:
        """Mark the last bar closed once wall-clock time has passed its end."""
        if not self.bars or self.bars[-1].closed:
            return
        b = self.bars[-1]
        s = session_of(b.t, self.holidays)
        if s is None:
            b.closed = True
            return
        end = s.end if self.tf == "S" else b.t + timedelta(minutes=int(self.tf))
        if end >= s.end:
            end = s.end + timedelta(seconds=60)  # closing-auction minute belongs to the last bar
        if now >= end:
            b.closed = True

    def closes(self) -> List[float]:
        return [b.c for b in self.bars]

    def closed_bars(self) -> List[Bar]:
        return [b for b in self.bars if b.closed]

    def in_window(self, start: datetime, end: datetime) -> List[Bar]:
        return [b for b in self.bars if start <= b.t < end]


def build_bars(ticks: Iterable[Tick], tf: TF, holidays: Iterable[date] = ()) -> List[Bar]:
    s = BarSeries(tf, holidays)
    for t in ticks:
        s.on_tick(t)
    for b in s.bars[:-1]:
        b.closed = True
    return s.bars


def aggregate_bars(bars: List[Bar], tf: TF, holidays: Iterable[date] = ()) -> List[Bar]:
    """Aggregate finer bars (e.g. 1-minute broker bars used only for reconciliation)."""
    out: List[Bar] = []
    hs = frozenset(holidays)
    for b in bars:
        s = session_of(b.t, hs)
        if s is None:
            continue
        start = s.start if tf == "S" else s.bar_start(b.t, int(tf))
        if out and out[-1].t == start:
            o = out[-1]
            o.h, o.l, o.c, o.v = max(o.h, b.h), min(o.l, b.l), b.c, o.v + b.v
        else:
            out.append(Bar(start, b.o, b.h, b.l, b.c, b.v, session=s.key, closed=True))
    return out
