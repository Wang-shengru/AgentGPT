"""Field mapping between Shioaji TickFOPv1 / BidAskFOPv1 / Ticks and the engine's internal records.

!!! Direction conventions (the easiest place to get this wrong) !!!

* ``tick_type == 1`` : trade at the ASK price  -> 外盤 -> 主動買 (aggressive buy)
* ``tick_type == 2`` : trade at the BID price  -> 內盤 -> 主動賣 (aggressive sell)
* ``tick_type == 0`` : undetermined           -> not counted in any delta
* ``ask_side_total_vol`` : cumulative volume traded at the ask  = 外盤量 = 主動買量
* ``bid_side_total_vol`` : cumulative volume traded at the bid  = 內盤量 = 主動賣量
* ``simtrade == True``   : 試撮 (pre-open simulated match) -> discarded everywhere
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Any, List, Optional

BUY = 1
SELL = 2
NONE = 0


def _f(x: Any) -> float:
    if x is None or x == "":
        return 0.0
    return float(x)


def _tick_type(x: Any) -> int:
    """Shioaji may hand an int, an IntEnum or a TickType enum ("Buy"/"Sell"/"None")."""
    if isinstance(x, (int, float)):
        return int(x)
    v = getattr(x, "value", x)
    if isinstance(v, (int, float)):
        return int(v)
    s = str(v).lower()
    if "buy" in s:
        return BUY
    if "sell" in s:
        return SELL
    try:
        return int(s)
    except ValueError:
        return NONE


@dataclass(slots=True)
class Tick:
    """Engine-internal tick (one trade)."""

    code: str
    dt: datetime
    close: float
    volume: int
    total_volume: int
    tick_type: int
    bid_side_total_vol: int  # 內盤累計 (主動賣)
    ask_side_total_vol: int  # 外盤累計 (主動買)
    avg_price: float
    underlying_price: float
    open: float
    high: float
    low: float
    simtrade: bool = False
    product: str = ""  # TXF / MXF / TMF / TXF2

    @property
    def is_buy(self) -> bool:
        return self.tick_type == BUY

    @property
    def is_sell(self) -> bool:
        return self.tick_type == SELL


@dataclass(slots=True)
class BidAsk:
    code: str
    dt: datetime
    bid_total_vol: int
    ask_total_vol: int
    bid_price: List[float]
    bid_volume: List[int]
    ask_price: List[float]
    ask_volume: List[int]
    simtrade: bool = False
    product: str = ""

    @property
    def io_delta(self) -> int:
        """IoDelta 委買賣差 = 五檔委買總量 − 五檔委賣總量."""
        return int(self.bid_total_vol) - int(self.ask_total_vol)


@dataclass(slots=True)
class IndexQuote:
    code: str
    dt: datetime
    close: float
    reference: float  # 昨收
    open: float
    high: float
    low: float
    amount_sum: float  # 累計成交金額（原始單位）


def tick_from_fop_v1(t: Any, product: str = "") -> Tick:
    """Map a ``shioaji.TickFOPv1`` (or an object with identical fields) to :class:`Tick`."""
    return Tick(
        code=str(t.code),
        dt=t.datetime,
        close=_f(t.close),
        volume=int(t.volume),
        total_volume=int(t.total_volume),
        tick_type=_tick_type(t.tick_type),
        bid_side_total_vol=int(t.bid_side_total_vol),
        ask_side_total_vol=int(t.ask_side_total_vol),
        avg_price=_f(t.avg_price),
        underlying_price=_f(t.underlying_price),
        open=_f(t.open),
        high=_f(t.high),
        low=_f(t.low),
        simtrade=bool(t.simtrade),
        product=product,
    )


def bidask_from_fop_v1(b: Any, product: str = "") -> BidAsk:
    return BidAsk(
        code=str(b.code),
        dt=b.datetime,
        bid_total_vol=int(b.bid_total_vol),
        ask_total_vol=int(b.ask_total_vol),
        bid_price=[_f(x) for x in b.bid_price],
        bid_volume=[int(x) for x in b.bid_volume],
        ask_price=[_f(x) for x in b.ask_price],
        ask_volume=[int(x) for x in b.ask_volume],
        simtrade=bool(getattr(b, "simtrade", False)),
        product=product,
    )


def index_from_quote_idx_v1(q: Any) -> IndexQuote:
    return IndexQuote(
        code=str(q.code),
        dt=q.datetime,
        close=_f(q.close),
        reference=_f(getattr(q, "reference", 0)),
        open=_f(q.open),
        high=_f(q.high),
        low=_f(q.low),
        amount_sum=_f(getattr(q, "amount_sum", 0) or 0),
    )


def ts_to_local(ts: int) -> datetime:
    """Shioaji history ``ts`` is ns since epoch with Taipei wall-clock encoded as UTC."""
    from datetime import timezone

    return datetime.fromtimestamp(ts / 1e9, tz=timezone.utc).replace(tzinfo=None)


def ticks_from_history(h: Any, code: str, product: str) -> List[Tick]:
    """Map ``api.ticks(...)`` (columnar ``Ticks``) to engine ticks.

    History has no cumulative side volumes / avg_price; those are rebuilt here so the
    downstream engine sees the same shape as live TickFOPv1.
    """
    out: List[Tick] = []
    tot = buy = sell = 0
    amt = 0.0
    o = hi = lo = None
    for i, ts in enumerate(h.ts):
        px = float(h.close[i])
        vol = int(h.volume[i])
        tt = _tick_type(h.tick_type[i]) if getattr(h, "tick_type", None) else NONE
        tot += vol
        amt += px * vol
        if tt == BUY:
            buy += vol
        elif tt == SELL:
            sell += vol
        o = px if o is None else o
        hi = px if hi is None else max(hi, px)
        lo = px if lo is None else min(lo, px)
        out.append(
            Tick(code, ts_to_local(int(ts)), px, vol, tot, tt, sell, buy,
                 amt / tot if tot else px, 0.0, o, hi, lo, False, product)
        )
    return out


# --------------------------------------------------------------------------------------
# Mock objects: field-for-field identical to shioaji 1.7.x TickFOPv1 / BidAskFOPv1
# (prices are ``str`` exactly like the installed stub declares).
# --------------------------------------------------------------------------------------
@dataclass
class MockTickFOPv1:
    exchange: str
    code: str
    date: date
    time: time
    datetime: datetime
    open: str
    close: str
    high: str
    low: str
    underlying_price: str
    bid_side_total_vol: int
    ask_side_total_vol: int
    avg_price: str
    amount: str
    total_amount: str
    volume: int
    total_volume: int
    tick_type: int
    chg_type: int
    price_chg: str
    pct_chg: str
    simtrade: bool

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


@dataclass
class MockBidAskFOPv1:
    exchange: str
    code: str
    date: date
    time: time
    datetime: datetime
    bid_total_vol: int
    ask_total_vol: int
    bid_price: List[str]
    bid_volume: List[int]
    diff_bid_vol: List[int]
    ask_price: List[str]
    ask_volume: List[int]
    diff_ask_vol: List[int]
    first_derived_bid_price: str
    first_derived_ask_price: str
    first_derived_bid_vol: int
    first_derived_ask_vol: int
    underlying_price: str
    simtrade: bool

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


@dataclass
class MockQuoteIdxV1:
    exchange: str
    code: str
    date: date
    time: time
    datetime: datetime
    reference: str
    open: str
    high: str
    low: str
    close: str
    amount_sum: Optional[str]
    amount: Optional[str]
    volume: Optional[int] = None
    vol_sum: Optional[int] = None
    count: Optional[int] = None
    limit_up_count: Optional[int] = None
    raise_count: Optional[int] = None
    flat_count: Optional[int] = None
    fall_count: Optional[int] = None
    limit_down_count: Optional[int] = None
