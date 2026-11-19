"""Mock market: generates TickFOPv1 / BidAskFOPv1 / QuoteIdxV1-identical objects.

* Runs on a virtual clock: when the real Taipei clock is inside a session the virtual clock
  equals it; otherwise it replays the most recent day session from 10:52, so the screen is
  always moving. When a session ends the clock jumps to the next session start.
* Generates ``MOCK_HISTORY_DAYS`` trading days of history so long MAs (60K 380ma) are
  available, landed through the same TickStore path as live data.
"""
from __future__ import annotations

import asyncio
import math
import random
import time as _time
from datetime import date, datetime, timedelta
from typing import Callable, Iterator, List, Optional, Tuple
from zoneinfo import ZoneInfo

from ..contracts import near_code, next_code
from ..session import (SPOT_END, SPOT_START, SessionInfo, day_session, is_trading_day, next_session,
                       night_session, prev_trading_day, session_of)
from ..ticks import MockBidAskFOPv1, MockQuoteIdxV1, MockTickFOPv1

TPE = ZoneInfo("Asia/Taipei")
Emit = Callable[[str, str, object], None]  # (kind, product, obj)


def taipei_now() -> datetime:
    return datetime.now(TPE).replace(tzinfo=None)


class _Book:
    """Per-product cumulative session state."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.total = 0
        self.bid_side = 0  # 內盤
        self.ask_side = 0  # 外盤
        self.amount = 0.0
        self.o: Optional[float] = None
        self.h = -math.inf
        self.l = math.inf
        self.prev_close: Optional[float] = None


class MockMarket:
    PRODUCTS = ("TXF", "MXF", "TMF", "TXF2")

    def __init__(self, seed: int = 9, holidays=(), base: float = 27500.0):
        self.rng = random.Random(seed)
        self.holidays = frozenset(holidays)
        self.fair = base
        self.drift = 0.0
        self.regime_left = 0.0
        self.basis = 18.0
        self.spread2 = -42.0
        self.books = {p: _Book() for p in self.PRODUCTS}
        self.session_key: Optional[str] = None
        self.last_px = {p: base for p in self.PRODUCTS}
        self.spot = base - self.basis
        self.spot_ref = self.spot
        self.spot_amount = 0.0
        self.spot_o = self.spot_h = self.spot_l = self.spot
        self.spot_day: Optional[date] = None
        self.last_dt: Optional[datetime] = None

    # ---------------------------------------------------------------- price process
    def _evolve(self, dt_s: float) -> None:
        self.regime_left -= dt_s
        if self.regime_left <= 0:
            self.regime_left = self.rng.uniform(1200, 4200)
            self.drift = self.rng.gauss(0, 0.012)  # points per second
        vol = 0.9 * math.sqrt(max(dt_s, 0.05))
        self.fair += self.drift * dt_s + self.rng.gauss(0, vol)
        self.basis += self.rng.gauss(0, 0.05 * math.sqrt(max(dt_s, 0.05))) - 0.0005 * (self.basis - 15) * dt_s
        self.spread2 += self.rng.gauss(0, 0.03) - 0.0005 * (self.spread2 + 42) * dt_s

    def _on_session(self, s: SessionInfo) -> bool:
        if s.key != self.session_key:
            self.session_key = s.key
            for p, b in self.books.items():
                b.prev_close = self.last_px[p]
                b.reset()
                b.prev_close = self.last_px[p]
            return True
        return False

    # ---------------------------------------------------------------- objects
    def _tick(self, product: str, code: str, dt: datetime, px: float, vol: int, tt: int, sim: bool = False,
              underlying: float = 0.0) -> MockTickFOPv1:
        b = self.books[product]
        if not sim:
            b.total += vol
            b.amount += px * vol
            if tt == 1:
                b.ask_side += vol
            elif tt == 2:
                b.bid_side += vol
            b.o = px if b.o is None else b.o
            b.h, b.l = max(b.h, px), min(b.l, px)
            self.last_px[product] = px
        ref = b.prev_close or px
        chg = px - ref
        return MockTickFOPv1(
            exchange="TAIFEX", code=code, date=dt.date(), time=dt.time(), datetime=dt,
            open=f"{(b.o if b.o is not None else px):.0f}", close=f"{px:.0f}",
            high=f"{(b.h if b.h > -math.inf else px):.0f}", low=f"{(b.l if b.l < math.inf else px):.0f}",
            underlying_price=f"{underlying:.2f}",
            bid_side_total_vol=b.bid_side, ask_side_total_vol=b.ask_side,
            avg_price=f"{(b.amount / b.total if b.total else px):.2f}",
            amount=f"{px * vol:.0f}", total_amount=f"{b.amount:.0f}",
            volume=vol, total_volume=b.total, tick_type=tt,
            chg_type=1 if chg > 0 else 5 if chg < 0 else 3,
            price_chg=f"{chg:.0f}", pct_chg=f"{(chg / ref * 100 if ref else 0):.2f}", simtrade=sim,
        )

    def _bidask(self, code: str, dt: datetime, px: float, bias: float) -> MockBidAskFOPv1:
        r = self.rng
        bv = [max(1, int(r.gauss(18 + 8 * bias, 7))) for _ in range(5)]
        av = [max(1, int(r.gauss(18 - 8 * bias, 7))) for _ in range(5)]
        return MockBidAskFOPv1(
            exchange="TAIFEX", code=code, date=dt.date(), time=dt.time(), datetime=dt,
            bid_total_vol=sum(bv), ask_total_vol=sum(av),
            bid_price=[f"{px - 1 - i:.0f}" for i in range(5)], bid_volume=bv, diff_bid_vol=[0] * 5,
            ask_price=[f"{px + i:.0f}" for i in range(5)], ask_volume=av, diff_ask_vol=[0] * 5,
            first_derived_bid_price="0", first_derived_ask_price="0", first_derived_bid_vol=0,
            first_derived_ask_vol=0, underlying_price=f"{self.spot:.2f}", simtrade=False,
        )

    def _spot_quote(self, dt: datetime) -> Optional[MockQuoteIdxV1]:
        t = dt.time()
        if not (SPOT_START <= t <= SPOT_END):
            return None
        if self.spot_day != dt.date():
            self.spot_day = dt.date()
            self.spot_ref = self.spot
            self.spot_amount = 0.0
            self.spot_o = self.spot_h = self.spot_l = self.spot = self.fair - self.basis
        self.spot = self.fair - self.basis
        self.spot_h, self.spot_l = max(self.spot_h, self.spot), min(self.spot_l, self.spot)
        self.spot_amount += self.rng.uniform(0.4e8, 1.2e8)
        return MockQuoteIdxV1(
            exchange="TSE", code="001", date=dt.date(), time=dt.time(), datetime=dt,
            reference=f"{self.spot_ref:.2f}", open=f"{self.spot_o:.2f}", high=f"{self.spot_h:.2f}",
            low=f"{self.spot_l:.2f}", close=f"{self.spot:.2f}", amount_sum=f"{self.spot_amount:.0f}", amount=None,
        )

    def step(self, dt: datetime, emit: Emit, density: float = 1.0, full: bool = True) -> None:
        """Advance the market to ``dt`` and emit whatever happened."""
        s = session_of(dt, self.holidays)
        dt_s = 1.0 if self.last_dt is None else max(0.0, (dt - self.last_dt).total_seconds())
        self.last_dt = dt
        self._evolve(min(dt_s, 600))
        if s is None:
            # pre-open trial matching 08:30–08:45: simtrade ticks that must be ignored downstream
            if dt.time() >= datetime.strptime("08:30", "%H:%M").time() and dt.time() < day_session(dt.date()).start.time() \
                    and self.rng.random() < 0.2 * density:
                emit("tick", "TXF", self._tick("TXF", near_code("TXF", dt.date()), dt, round(self.fair), 1, 0, sim=True))
            return
        td = s.trading_date
        codes = {"TXF": near_code("TXF", td), "MXF": near_code("MXF", td), "TMF": near_code("TMF", td),
                 "TXF2": next_code("TXF", td)}
        new = self._on_session(s)
        q = self._spot_quote(dt)
        if q is not None and self.rng.random() < 0.6:
            emit("index", "IDX", q)
        under = self.spot
        px = float(round(self.fair))
        if new:
            # opening auction: one large match, tick_type 0
            for p in self.PRODUCTS:
                base_px = px + (round(self.spread2) if p == "TXF2" else 0)
                emit("tick", p, self._tick(p, codes[p], dt, base_px, self.rng.randint(300, 900) if p == "TXF" else
                                           self.rng.randint(50, 400), 0, underlying=under))
            return
        move = px - self.last_px["TXF"]
        bias = max(-1.0, min(1.0, self.drift * 60))
        p_buy = 0.5 + (0.3 if move > 0 else -0.3 if move < 0 else 0) + 0.1 * bias
        plan = (("TXF", 0.9), ("MXF", 0.7), ("TMF", 0.45), ("TXF2", 0.12)) if full else (("TXF", 1.0),)
        for p, prob in plan:
            if self.rng.random() > prob * density:
                continue
            ppx = px + (round(self.spread2) if p == "TXF2" else self.rng.choice((0, 0, 0, -1, 1)) if p != "TXF" else 0)
            u = self.rng.random()
            tt = 1 if u < p_buy * 0.95 else 2 if u < 0.95 else 0
            vol = max(1, int(self.rng.expovariate(1 / (4 if p == "TXF" else 6 if p == "MXF" else 3))))
            if self.rng.random() < 0.01:
                vol *= self.rng.randint(5, 25)
            if not full:
                vol *= 4  # sparse history ticks carry the volume of ~4 live ticks
            emit("tick", p, self._tick(p, codes[p], dt, ppx, vol, tt, underlying=under))
            if full and p != "TXF2" and self.rng.random() < 0.8:
                emit("bidask", p, self._bidask(codes[p], dt, ppx, bias + (0.4 if tt == 1 else -0.4 if tt == 2 else 0)))


def _sessions_between(start: datetime, end: datetime, holidays) -> List[SessionInfo]:
    out = []
    d = start.date() - timedelta(days=1)
    while d <= end.date():
        for s in (day_session(d), night_session(d, holidays)):
            if d.weekday() < 5 and d not in holidays and s.end > start and s.start < end:
                out.append(s)
        d += timedelta(days=1)
    return sorted(out, key=lambda s: s.start)


class MockFeed:
    name = "mock"

    def __init__(self, settings, emit: Emit):
        self.settings = settings
        self.emit = emit
        self.holidays = settings.holidays
        self.market = MockMarket(settings.mock_seed, self.holidays)
        real = taipei_now()
        if session_of(real, self.holidays):
            self.v0 = real
        else:
            d = real.date()
            while not is_trading_day(d, self.holidays) or day_session(d).start + timedelta(hours=2, minutes=7) > real:
                d -= timedelta(days=1)
            self.v0 = day_session(d).start + timedelta(hours=2, minutes=7)
        self.real0 = _time.monotonic()
        self.connected = False
        self._task: Optional[asyncio.Task] = None
        self._jump = timedelta(0)

    # virtual clock --------------------------------------------------------------------
    def now(self) -> datetime:
        el = (_time.monotonic() - self.real0) * self.settings.mock_speed
        return self.v0 + timedelta(seconds=el) + self._jump

    def history(self) -> Iterator[Tuple[str, str, object]]:
        """Synthetic history from N trading days back up to v0 (sparser ticks for speed)."""
        d = self.v0.date()
        for _ in range(self.settings.mock_history_days):
            d = prev_trading_day(d, self.holidays)
        start = datetime.combine(d, datetime.min.time())
        buf: List[Tuple[str, str, object]] = []

        def put(kind, product, obj):
            buf.append((kind, product, obj))

        for s in _sessions_between(start, self.v0, self.holidays):
            # include a few pre-open simtrade ticks before day sessions
            if s.kind == "day":
                pre = s.start - timedelta(minutes=10)
                for k in range(6):
                    self.market.step(pre + timedelta(minutes=k), put, density=5)
            t = s.start
            end = min(s.end, self.v0)
            recent = (self.v0 - s.start) < timedelta(hours=30)
            while t <= end:
                self.market.step(t, put, density=1.0, full=recent)
                t += timedelta(seconds=self.market.rng.uniform(1.5, 4.0) if recent else self.market.rng.uniform(6, 14))
                if len(buf) > 5000:
                    yield from buf
                    buf.clear()
        yield from buf

    async def start(self) -> None:
        self.connected = True
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()

    async def _run(self) -> None:
        while True:
            now = self.now()
            if session_of(now, self.holidays) is None:
                # jump over the closed gap (keep 15 minutes of pre-open simtrade only for day)
                ns = next_session(now, self.holidays)
                self._jump += (ns.start - now)
                continue
            self.market.step(now, self.emit)
            await asyncio.sleep(self.market.rng.uniform(0.25, 1.1) / self.settings.mock_speed)
