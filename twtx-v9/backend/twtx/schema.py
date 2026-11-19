"""WebSocket / REST JSON schema. MUST stay identical to ``frontend/src/schema.ts``
(enforced by tests/test_schema.py, which compares interface fields one-to-one).
"""
from __future__ import annotations

from typing import List, Literal, Optional, TypedDict, Union


class SessionStatus(TypedDict):
    kind: Optional[str]
    label: str
    key: str
    trading_date: str
    countdown_label: str
    countdown_s: int
    open: bool


class ServiceHealth(TypedDict):
    port: int
    ok: bool


class StoreHealth(TypedDict):
    port: int
    ok: bool
    rows: int
    pending: int


class Status(TypedDict):
    feed_connected: bool
    feed_text: str
    tick_age_s: Optional[float]
    driver_lag_s: Optional[float]
    calc_ms: float
    api: ServiceHealth
    engine: ServiceHealth
    store: StoreHealth
    regime: str
    queue: int


class QuoteCard(TypedDict):
    code: Optional[str]
    price: Optional[float]
    change: Optional[float]
    change_pct: Optional[float]
    volume: int
    ref: Optional[float]


class TxfCard(QuoteCard):
    open: Optional[float]
    high: Optional[float]
    low: Optional[float]
    range_pos: Optional[float]
    amplitude: Optional[float]
    amplitude_pct: Optional[float]


class NextCard(QuoteCard):
    spread: Optional[float]


class BasisCard(TypedDict):
    basis: Optional[float]
    label: Optional[str]
    spot: Optional[float]
    spot_ref: Optional[float]
    spot_amount_e8: Optional[float]
    underlying: Optional[float]


class VwapCard(TypedDict):
    vwap: Optional[float]
    dev_pct: Optional[float]
    self_vwap: Optional[float]
    check_diff: Optional[float]


class VolumeCard(TypedDict):
    total: int
    ratio5: Optional[float]
    bar_volume: Optional[int]


class V3Card(TypedDict):
    verdict: str
    net: float
    n_available: int
    n_items: int


class Quotes(TypedDict):
    txf: TxfCard
    mxf: QuoteCard
    tmf: QuoteCard
    next: NextCard
    basis: BasisCard
    vwap: VwapCard
    volume: VolumeCard
    v3: V3Card


class FlowProduct(TypedDict):
    session: str
    tx_delta: int
    tx_buy: int
    tx_sell: int
    vo_delta: int
    vo_buy: int
    vo_sell: int
    io_delta: Optional[int]
    bid_total: Optional[int]
    ask_total: Optional[int]
    buy_ratio: Optional[float]
    buy_ratio_exchange: Optional[float]
    scale_tx: float
    scale_vo: float
    scale_io: float
    scale_ratio: float
    session_volume: int
    ewma_delta: float


class Flow(TypedDict):
    badge: str
    txf: FlowProduct
    mxf: FlowProduct
    tmf: FlowProduct


class MaRow(TypedDict):
    n: int
    value: Optional[float]
    slope: Optional[float]


class Boll(TypedDict):
    upper: float
    mid: float
    lower: float
    width: float
    pct_b: float
    prev_width: Optional[float]


class Macd(TypedDict):
    dif: float
    dea: float
    osc: float
    osc_prev: float


class Tech(TypedDict):
    ma5: List[MaRow]
    ma5_label: str
    ma60: List[MaRow]
    ma60_close: Optional[float]
    ma60_label: str
    boll: Optional[Boll]
    macd: Optional[Macd]


class Level(TypedDict):
    key: str
    label: str
    price: float
    dist: Optional[float]


class PatternCell(TypedDict):
    t: str
    color: Literal["up", "down", "doji"]
    pattern: Optional[str]
    bias: int
    body_ratio: float


class PatternHit(TypedDict):
    tf: str
    t: str
    pattern: str


class Patterns(TypedDict):
    k5: List[PatternCell]
    k60: List[PatternCell]
    kS: List[PatternCell]
    latest: Optional[PatternHit]


class Opening8Bar(TypedDict):
    t: str
    close: Optional[float]
    vs_prev: Optional[float]


class Opening8(TypedDict, total=False):
    available: bool
    key: Optional[str]
    name: str
    tendency: str
    desc: str
    date: str
    prev_close: Optional[float]
    bars: List[Opening8Bar]


class V3Item(TypedDict):
    key: str
    group: str
    label: str
    direction: int
    strength: int
    value: Optional[float]
    display: str
    text: str
    voting: bool
    available: bool


class V3Group(TypedDict):
    key: str
    name: str
    score: float
    available: bool
    n_voting: int
    n_available: int
    items: List[V3Item]


class V3(TypedDict):
    net: float
    verdict: str
    sentence: str
    consistency: float
    bull: int
    bear: int
    neutral: int
    n_available: int
    n_items: int
    groups_available: int
    n_groups: int
    groups: List[V3Group]


class Snapshot(TypedDict):
    ts: str
    mode: str
    session: SessionStatus
    status: Status
    quotes: Quotes
    flow: Flow
    tech: Tech
    levels: List[Level]
    patterns: Patterns
    opening8: Opening8
    v3: V3


class KBar(TypedDict):
    t: int  # Taipei wall clock encoded as UTC epoch seconds
    o: float
    h: float
    l: float
    c: float
    v: int
    closed: bool
    code: str


# "from" is a Python keyword, so Rollover uses the functional TypedDict syntax
Rollover = TypedDict("Rollover", {"t": int, "from": str, "to": str})


class ChartPayload(TypedDict, total=False):
    date: Optional[str]
    dates: List[str]
    prev: Optional[str]
    next: Optional[str]
    bars: List[KBar]
    night_start: Optional[int]
    rollovers: List[Rollover]


class SnapshotMsg(TypedDict):
    type: Literal["snapshot"]
    data: Snapshot


class KBarMsg(TypedDict):
    type: Literal["kbar"]
    data: KBar


WsMessage = Union[SnapshotMsg, KBarMsg]
