"""Order-flow deltas per product per session (TxDelta / VoDelta / IoDelta / 主動買比).

* TxDelta = count(tick_type==1) − count(tick_type==2)          (tick_type 0 ignored)
* VoDelta = Σvol(tick_type==1) − Σvol(tick_type==2)           (opening-auction first tick excluded)
* IoDelta = latest BidAsk bid_total_vol − ask_total_vol
* 主動買比 = 外盤量 / (外盤量 + 內盤量), 外盤 = ask_side_total_vol, 內盤 = bid_side_total_vol,
  with the opening-auction contribution removed by baselining after the first tick.

Gauge scales are the session extreme of |value| and only grow; everything resets on a
session change (日 ↔ 夜).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from .ticks import BUY, SELL, BidAsk, Tick

MIN_SCALE = {"tx": 20.0, "vo": 50.0, "io": 50.0, "ratio": 5.0}


@dataclass
class FlowState:
    session: str = ""
    n_ticks: int = 0
    tx_buy: int = 0
    tx_sell: int = 0
    vo_buy: int = 0
    vo_sell: int = 0
    io_delta: Optional[int] = None
    bid_total: Optional[int] = None
    ask_total: Optional[int] = None
    ask_base: int = 0
    bid_base: int = 0
    ask_side: int = 0
    bid_side: int = 0
    session_volume: int = 0
    opening_excluded_vol: int = 0
    ewma_delta: float = 0.0
    ewma_last_ts: Optional[float] = None
    scale: dict = field(default_factory=lambda: dict(MIN_SCALE))

    @property
    def tx_delta(self) -> int:
        return self.tx_buy - self.tx_sell

    @property
    def vo_delta(self) -> int:
        return self.vo_buy - self.vo_sell

    @property
    def buy_ratio(self) -> Optional[float]:
        """主動買比 % = 外盤量 ÷ (外盤量 + 內盤量), opening auction excluded (self-counted)."""
        tot = self.vo_buy + self.vo_sell
        return self.vo_buy / tot * 100 if tot > 0 else None

    @property
    def buy_ratio_exchange(self) -> Optional[float]:
        """Cross-check from the exchange cumulative fields:
        ask_side_total_vol = 外盤 (主動買), bid_side_total_vol = 內盤 (主動賣)."""
        a = self.ask_side - self.ask_base
        b = self.bid_side - self.bid_base
        return a / (a + b) * 100 if (a + b) > 0 else None


class FlowTracker:
    def __init__(self, exclude_opening: bool = True, ewma_half_life_s: float = 1800.0):
        self.exclude_opening = exclude_opening
        self.half_life = ewma_half_life_s
        self.s = FlowState()

    def reset(self, session_key: str) -> None:
        self.s = FlowState(session=session_key)

    def _grow(self, k: str, v: Optional[float]) -> None:
        if v is None:
            return
        if abs(v) > self.s.scale[k]:
            self.s.scale[k] = abs(v)

    def on_tick(self, t: Tick, session_key: str) -> None:
        if t.simtrade:
            return
        if session_key != self.s.session:
            self.reset(session_key)
        s = self.s
        s.n_ticks += 1
        s.session_volume += t.volume
        s.ask_side, s.bid_side = t.ask_side_total_vol, t.bid_side_total_vol
        first = s.n_ticks == 1
        if first:
            if self.exclude_opening:
                # opening auction match: baseline cumulative side volumes AFTER it
                s.ask_base, s.bid_base = t.ask_side_total_vol, t.bid_side_total_vol
                s.opening_excluded_vol = t.volume
            else:
                # the exchange totals already include this tick
                s.ask_base = s.bid_base = 0
        # counts (TxDelta) always include every classified tick
        if t.tick_type == BUY:
            s.tx_buy += 1
        elif t.tick_type == SELL:
            s.tx_sell += 1
        # volumes (VoDelta) skip the opening auction
        if not (first and self.exclude_opening):
            signed = 0
            if t.tick_type == BUY:
                s.vo_buy += t.volume
                signed = t.volume
            elif t.tick_type == SELL:
                s.vo_sell += t.volume
                signed = -t.volume
            ts = t.dt.timestamp()
            if s.ewma_last_ts is not None and self.half_life > 0:
                s.ewma_delta *= math.exp(-math.log(2) * max(0.0, ts - s.ewma_last_ts) / self.half_life)
            s.ewma_last_ts = ts
            s.ewma_delta += signed
        self._grow("tx", s.tx_delta)
        self._grow("vo", s.vo_delta)
        r = s.buy_ratio
        if r is not None:
            self._grow("ratio", r - 50)

    def on_bidask(self, b: BidAsk, session_key: str) -> None:
        if b.simtrade:
            return
        if session_key != self.s.session:
            self.reset(session_key)
        self.s.bid_total, self.s.ask_total = b.bid_total_vol, b.ask_total_vol
        self.s.io_delta = b.io_delta
        self._grow("io", self.s.io_delta)

    def snapshot(self) -> dict:
        s = self.s
        return {
            "session": s.session,
            "tx_delta": s.tx_delta,
            "tx_buy": s.tx_buy,
            "tx_sell": s.tx_sell,
            "vo_delta": s.vo_delta,
            "vo_buy": s.vo_buy,
            "vo_sell": s.vo_sell,
            "io_delta": s.io_delta,
            "bid_total": s.bid_total,
            "ask_total": s.ask_total,
            "buy_ratio": s.buy_ratio,
            "buy_ratio_exchange": s.buy_ratio_exchange,
            "scale_tx": s.scale["tx"],
            "scale_vo": s.scale["vo"],
            "scale_io": s.scale["io"],
            "scale_ratio": s.scale["ratio"],
            "session_volume": s.session_volume,
            "ewma_delta": s.ewma_delta,
        }
