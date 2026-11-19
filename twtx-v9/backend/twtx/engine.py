"""Data engine: consumes the feed queue, lands ticks, rebuilds bars, computes everything and
produces the 1-second snapshot + per-tick K-bar increments for the WebSocket.
"""
from __future__ import annotations

import asyncio
import logging
import statistics
import time
from collections import deque
from datetime import date, datetime, timedelta
from typing import Any, Awaitable, Callable, Deque, Dict, List, Optional, Tuple

from . import indicators as ind
from . import opening8, patterns, scoring
from .flow import FlowTracker
from .kbar import Bar, BarSeries, epoch_local
from .session import (SPOT_START, SessionInfo, day_session, last_session, next_session, session_of,
                      spot_bar_index)
from .storage import TickStore
from .ticks import (BUY, SELL, BidAsk, IndexQuote, Tick, bidask_from_fop_v1, index_from_quote_idx_v1,
                    tick_from_fop_v1)

log = logging.getLogger("twtx.engine")

MA5 = (3, 12, 60, 180, 228, 300)
MA60 = (5, 25, 95, 380)
PRODUCTS = ("TXF", "MXF", "TMF", "TXF2")


def r(x: Optional[float], nd: int = 2) -> Optional[float]:
    return None if x is None else round(float(x), nd)


class ProductState:
    def __init__(self, product: str, exclude_opening: bool):
        self.product = product
        self.last: Optional[Tick] = None
        self.flow = FlowTracker(exclude_opening)
        self.session_key = ""
        self.s_open: Optional[float] = None
        self.s_high: Optional[float] = None
        self.s_low: Optional[float] = None
        self.session_volume = 0
        # closes of finished sessions: key -> (kind, open, high, low, close, trading_date)
        self.sessions: Dict[str, Tuple[str, float, float, float, float, date]] = {}
        self.vwap = ind.VwapCalc()

    def on_session(self, s: SessionInfo) -> None:
        if s.key != self.session_key:
            if self.session_key and self.last is not None and self.s_open is not None:
                k = self.session_key
                self.sessions[k] = ("day" if k.endswith("D") else "night", self.s_open, self.s_high, self.s_low,
                                    self.last.close, date.fromisoformat(k[:10]))
            self.session_key = s.key
            self.s_open = self.s_high = self.s_low = None
            self.session_volume = 0
            self.vwap.reset()

    def ref_day(self, current_key: str) -> Optional[Tuple]:
        """Most recently completed DAY session before the current one (昨高/昨低/昨收)."""
        best = None
        for k, v in self.sessions.items():
            if v[0] == "day" and k < current_key:
                if best is None or k > best[0]:
                    best = (k, v)
        return best[1] if best else None


class Engine:
    def __init__(self, settings, store: TickStore, params: Optional[dict] = None):
        self.settings = settings
        self.store = store
        self.holidays = settings.holidays
        self.params = params or scoring.load_params(settings.scoring_params_file)
        self.queue: asyncio.Queue = asyncio.Queue()
        self.p: Dict[str, ProductState] = {k: ProductState(k, settings.exclude_opening_auction) for k in PRODUCTS}
        self.b5 = BarSeries(5, self.holidays)
        self.b60 = BarSeries(60, self.holidays)
        self.bS = BarSeries("S", self.holidays)
        self.mxf5 = BarSeries(5, self.holidays, 400)
        self.recent: Deque[Tuple[datetime, int, int]] = deque()  # TXF (dt, tick_type, vol) last 5 minutes
        self.spot: Optional[IndexQuote] = None
        self.spot_bars: Dict[date, List[Optional[Bar]]] = {}
        self.spot_ref: Dict[date, float] = {}
        self.feed: Any = None
        self.now_fn: Callable[[], datetime] = datetime.now
        self.last_tick_mono: Optional[float] = None
        self.last_lag = 0.0
        self.worker_alive = 0.0
        self.listeners: List[Callable[[dict], Awaitable[None]]] = []
        self.history_mode = False
        self.started_mono = time.monotonic()
        self.vwap_check: Optional[float] = None

    # ------------------------------------------------------------------ feed side
    def emit(self, kind: str, product: str, obj: Any) -> None:
        """Called by feeds (on the loop thread). Only enqueue."""
        self.queue.put_nowait((kind, product, obj, time.monotonic()))

    # ------------------------------------------------------------------ processing
    def handle(self, kind: str, product: str, obj: Any, land: bool = True) -> Optional[Bar]:
        if kind == "tick":
            t = obj if isinstance(obj, Tick) else tick_from_fop_v1(obj, product)
            t.product = product
            return self.on_tick(t, land)
        if kind == "bidask":
            b = obj if isinstance(obj, BidAsk) else bidask_from_fop_v1(obj, product)
            self.on_bidask(b, product)
        elif kind == "index":
            q = obj if isinstance(obj, IndexQuote) else index_from_quote_idx_v1(obj)
            self.on_index(q, land)
        return None

    def on_tick(self, t: Tick, land: bool = True) -> Optional[Bar]:
        s = session_of(t.dt, self.holidays)
        if land and s is not None:
            self.store.put_tick(s.trading_date, t)  # land every tick (simtrade flagged)
        elif land and t.simtrade:
            self.store.put_tick(t.dt.date(), t)
        if t.simtrade or s is None:
            return None  # 試撮 / out of session: never enters calculations or bars
        ps = self.p[t.product]
        ps.on_session(s)
        if ps.last is not None and t.dt < ps.last.dt - timedelta(seconds=1):
            return None  # stale/out of order (dedup vs backfill)
        ps.last = t
        ps.s_open = t.close if ps.s_open is None else ps.s_open
        ps.s_high = t.close if ps.s_high is None else max(ps.s_high, t.close)
        ps.s_low = t.close if ps.s_low is None else min(ps.s_low, t.close)
        ps.session_volume += t.volume
        ps.vwap.add(t.close, t.volume)
        if t.product != "TXF2":
            ps.flow.on_tick(t, s.key)
        if not self.history_mode:
            self.last_tick_mono = time.monotonic()
        if t.product == "MXF":
            self.mxf5.on_tick(t, s)
        if t.product != "TXF":
            return None
        self.recent.append((t.dt, t.tick_type, t.volume))
        cutoff = t.dt - timedelta(minutes=5)
        while self.recent and self.recent[0][0] < cutoff:
            self.recent.popleft()
        bar, _ = self.b5.on_tick(t, s)
        self.b60.on_tick(t, s)
        self.bS.on_tick(t, s)
        return bar

    def on_bidask(self, b: BidAsk, product: str) -> None:
        if b.simtrade:
            return
        s = session_of(b.dt, self.holidays)
        if s is None:
            return
        ps = self.p.get(product)
        if ps is not None and product != "TXF2":
            ps.flow.on_bidask(b, s.key)

    def on_index(self, q: IndexQuote, land: bool = True) -> None:
        if q.close <= 0:
            return
        if land:
            self.store.put_index(q.dt.date(), q)
        self.spot = q
        d = q.dt.date()
        if q.reference > 0:
            self.spot_ref[d] = q.reference
        idx = spot_bar_index(q.dt)
        if idx is None:
            return
        bars = self.spot_bars.setdefault(d, [None] * 54)
        b = bars[idx]
        if b is None:
            bars[idx] = Bar(datetime.combine(d, SPOT_START) + timedelta(minutes=5 * idx), q.close, q.close, q.close, q.close)
        else:
            b.h, b.l, b.c = max(b.h, q.close), min(b.l, q.close), q.close

    # ------------------------------------------------------------------ loops
    async def worker(self) -> None:
        while True:
            item = await self.queue.get()
            batch = [item]
            while not self.queue.empty() and len(batch) < 2000:
                batch.append(self.queue.get_nowait())
            changed: Optional[Bar] = None
            for kind, product, obj, enq in batch:
                try:
                    bar = self.handle(kind, product, obj)
                    if bar is not None:
                        changed = bar
                except Exception:  # pragma: no cover
                    log.exception("tick processing failed")
                self.last_lag = time.monotonic() - enq
            self.worker_alive = time.monotonic()
            if changed is not None:
                await self.broadcast({"type": "kbar", "data": self.bar_json(changed)})

    async def snapshot_loop(self) -> None:
        while True:
            t0 = time.monotonic()
            try:
                snap = self.snapshot()
                snap["status"]["calc_ms"] = round((time.monotonic() - t0) * 1000, 1)
                await self.broadcast({"type": "snapshot", "data": snap})
            except Exception:  # pragma: no cover
                log.exception("snapshot failed")
            await asyncio.sleep(max(0.05, 1.0 - (time.monotonic() - t0)))

    async def flush_loop(self) -> None:
        while True:
            await asyncio.sleep(0.5)
            await asyncio.to_thread(self.store.flush)

    async def broadcast(self, msg: dict) -> None:
        for fn in list(self.listeners):
            try:
                await fn(msg)
            except Exception:
                pass

    # ------------------------------------------------------------------ helpers
    def now(self) -> datetime:
        return self.now_fn()

    def bar_json(self, b: Bar) -> dict:
        return {"t": epoch_local(b.t), "o": b.o, "h": b.h, "l": b.l, "c": b.c, "v": b.v, "closed": b.closed,
                "code": b.code}

    def current_session(self) -> SessionInfo:
        return last_session(self.now(), self.holidays)

    def chart_dates(self) -> List[str]:
        ds = sorted({session_of(b.t, self.holidays).chart_date.isoformat() for b in self.bS.bars
                     if session_of(b.t, self.holidays)})
        return ds[-self.settings.keep_days:]

    def chart(self, d: Optional[str]) -> dict:
        dates = self.chart_dates()
        if not dates:
            return {"date": d, "bars": [], "dates": [], "night_start": None, "rollovers": []}
        if not d or d not in dates:
            d = dates[-1]
        day = date.fromisoformat(d)
        start = datetime.combine(day, day_session(day).start.time())
        end = start + timedelta(hours=20, minutes=16)
        bars = self.b5.in_window(start, end)
        rolls = []
        for i in range(1, len(self.b5.bars)):
            a, b = self.b5.bars[i - 1], self.b5.bars[i]
            if a.code and b.code and a.code[:3] == b.code[:3] and a.code != b.code and start <= b.t < end:
                rolls.append({"t": epoch_local(b.t), "from": a.code, "to": b.code})
        night = datetime.combine(day, datetime.strptime("15:00", "%H:%M").time())
        i = dates.index(d)
        return {
            "date": d,
            "dates": dates,
            "prev": dates[i - 1] if i > 0 else None,
            "next": dates[i + 1] if i + 1 < len(dates) else None,
            "bars": [self.bar_json(b) for b in bars],
            "night_start": epoch_local(night) if any(b.t >= night for b in bars) else None,
            "rollovers": rolls,
        }

    def _vol_ratio(self, s: SessionInfo, now: datetime) -> Optional[float]:
        if not self.b5.bars:
            return None
        cur = self.b5.bars[-1]
        if cur.session != s.key:
            return None
        slot = s.bar_index(cur.t, 5)
        hist: Dict[str, int] = {}
        for b in reversed(self.b5.bars[:-1]):
            if b.session == s.key or not b.session.endswith(s.key[-1]):
                continue
            ss = session_of(b.t, self.holidays)
            if ss and ss.bar_index(b.t, 5) == slot:
                hist[b.session] = b.v
                if len(hist) >= self.settings.volume_ratio_days:
                    break
        if not hist:
            return None
        avg = sum(hist.values()) / len(hist)
        frac = 1.0 if cur.closed else min(1.0, max(0.2, (now - cur.t).total_seconds() / 300))
        return cur.v / (avg * frac) if avg else None

    def _pattern_feature(self, series: BarSeries, lookback: int) -> Optional[dict]:
        closed = series.closed_bars()
        if len(closed) < 5:
            return None
        cells = patterns.strip(closed, 12)
        hit = None
        for c in reversed(cells[-lookback:]):
            if c["pattern"]:
                hit = c
                break
        return hit or {"pattern": None, "bias": 0, "body_ratio": 0.0}

    # ------------------------------------------------------------------ snapshot
    def snapshot(self) -> dict:
        now = self.now()
        for series in (self.b5, self.b60, self.bS):
            series.close_through(now)
        live_s = session_of(now, self.holidays)
        s = live_s or last_session(now, self.holidays)
        txf = self.p["TXF"]
        last = txf.last
        px = last.close if last else None
        ref = txf.ref_day(s.key)
        ref_close = ref[4] if ref else None

        def card(prod: str) -> dict:
            ps = self.p[prod]
            lt = ps.last
            rf = ps.ref_day(s.key)
            rc = rf[4] if rf else None
            c = lt.close if lt else None
            return {
                "code": lt.code if lt else (self.feed.display_codes.get(prod) if self.feed and hasattr(self.feed, "display_codes") else None),
                "price": c,
                "change": r(c - rc, 0) if (c is not None and rc) else None,
                "change_pct": r((c - rc) / rc * 100, 2) if (c is not None and rc) else None,
                "volume": ps.session_volume,
                "ref": rc,
            }

        closes5 = self.b5.closes()
        closes60 = self.b60.closes()
        ma5 = {n: ind.sma(closes5, n) for n in MA5}
        sl5 = {n: ind.sma_slope(closes5, n) for n in MA5}
        ma60 = {n: ind.sma(closes60, n) for n in MA60}
        sl60 = {n: ind.sma_slope(closes60, n) for n in MA60}
        bb = ind.bollinger(closes5, 20, 2)
        mac = ind.macd(closes5)
        vwap_ex = last.avg_price if (last and last.avg_price) else None
        vwap_self = txf.vwap.value
        vwap = vwap_ex or vwap_self
        self.vwap_check = (vwap_ex - vwap_self) if (vwap_ex and vwap_self) else None
        hi, lo = txf.s_high, txf.s_low
        range_pos = ((px - lo) / (hi - lo)) if (px is not None and hi is not None and hi > lo) else (0.5 if px else None)

        # flow
        fl = {k: self.p[k].flow.snapshot() for k in ("TXF", "MXF", "TMF")}

        def pct(a: int, b: int) -> Optional[float]:
            return (a - b) / (a + b) * 100 if (a + b) > 0 else None

        f_txf = fl["TXF"]
        rb = sum(1 for _, tt, _ in self.recent if tt == BUY)
        rs = sum(1 for _, tt, _ in self.recent if tt == SELL)
        rbv = sum(v for _, tt, v in self.recent if tt == BUY)
        rsv = sum(v for _, tt, v in self.recent if tt == SELL)
        r5_tx = pct(rb, rs)
        sess_pcts = [pct(b.buy_cnt, b.sell_cnt) for b in self.b5.bars if b.session == s.key and b.closed]
        sess_pcts = [x for x in sess_pcts if x is not None]
        med = statistics.median(sess_pcts) if len(sess_pcts) >= 3 else None
        r5_rel = (r5_tx - med) if (r5_tx is not None and med is not None) else None

        features = {
            "price": px,
            "m5_12": ma5[12],
            "m5_180": ma5[180],
            "m5_180_slope": sl5[180],
            "m5_60_slopes3": [ind.sma_slope(closes5[: len(closes5) - k] if k else closes5, 60) for k in range(3)],
            "h60_25_slope": sl60[25],
            "macd": mac,
            "boll": bb,
            "vwap": vwap,
            "range_pos": range_pos if txf.session_key == s.key else None,
            "tx_pct": pct(f_txf["tx_buy"], f_txf["tx_sell"]),
            "recent5_tx_rel": r5_rel,
            "weighted_vol": (f_txf["ewma_delta"] / f_txf["session_volume"] * 100) if f_txf["session_volume"] else None,
            "vo_pct": pct(f_txf["vo_buy"], f_txf["vo_sell"]),
            "recent5_vo_pct": pct(rbv, rsv),
            "mxf_tx_pct": pct(fl["MXF"]["tx_buy"], fl["MXF"]["tx_sell"]),
            "tmf_tx_pct": pct(fl["TMF"]["tx_buy"], fl["TMF"]["tx_sell"]),
            "pat5": self._pattern_feature(self.b5, self.params.get("pattern_lookback", 3)),
            "pat60": self._pattern_feature(self.b60, self.params.get("pattern_lookback", 3)),
        }
        v3 = scoring.score(features, self.params)

        # flow badge
        votes = [x for x in (f_txf["tx_delta"], f_txf["vo_delta"], f_txf["io_delta"] or 0,
                             (f_txf["buy_ratio"] or 50) - 50) if x]
        sgn = sum(1 if x > 0 else -1 for x in votes)
        flow_badge = "偏多" if sgn >= 2 else "偏空" if sgn <= -2 else "中性"

        # key levels
        levels: List[dict] = []

        def lv(key: str, label: str, val: Optional[float]) -> None:
            if val is not None:
                levels.append({"key": key, "label": label, "price": r(val, 1)})

        lv("h60_95", "60K 95ma", ma60[95])
        lv("h60_380", "60K 380ma", ma60[380])
        if ref:
            c = ind.cdp(ref[2], ref[3], ref[4])
            for k in ("AH", "NH", "CDP", "NL", "AL"):
                lv(f"cdp_{k}", f"CDP {k}" if k != "CDP" else "CDP", c[k])
            lv("prev_high", "昨高", ref[2])
            lv("prev_low", "昨低", ref[3])
            lv("prev_close", "昨收", ref[4])
        if txf.session_key == s.key:
            lv("high", "今日高", hi)
            lv("low", "今日低", lo)
            lv("open", "開盤", txf.s_open)
        if bb:
            lv("bb_up", "布林上", bb["upper"])
            lv("bb_mid", "布林中", bb["mid"])
            lv("bb_dn", "布林下", bb["lower"])
        lv("vwap", "VWAP", vwap)
        for n in (60, 180, 228, 300):
            lv(f"m5_{n}", f"5K {n}ma", ma5[n])
        lv("h60_25", "60K 25ma", ma60[25])
        if px is not None:
            levels.append({"key": "price", "label": "現價", "price": px})
        levels.sort(key=lambda x: (-x["price"], 0 if x["key"] == "price" else 1))
        for x in levels:
            x["dist"] = r(x["price"] - px, 1) if px is not None else None

        # spot / basis
        sp = self.spot
        spot_px = sp.close if sp else None
        underlying = last.underlying_price if (last and last.underlying_price) else None
        basis_ref = spot_px or underlying
        basis = r(px - basis_ref, 2) if (px is not None and basis_ref) else None

        # opening eight
        o8d = max(self.spot_bars) if self.spot_bars else None
        o8_bars = []
        o8 = opening8.classify(None, [])
        if o8d is not None:
            bars = self.spot_bars[o8d]
            cut = datetime.combine(o8d, SPOT_START) + timedelta(minutes=15)
            done = [b for b in bars[:3] if b is not None]
            prev_c = self.spot_ref.get(o8d)
            ready = len(done) == 3 and (now >= cut or now.date() > o8d)
            o8 = opening8.classify(prev_c, [b.c for b in done] if ready else [b.c for b in done][: max(0, len(done) - 1)])
            o8_bars = [{"t": b.t.strftime("%H:%M"), "close": r(b.c, 2), "vs_prev": r(b.c - prev_c, 2) if prev_c else None}
                       for b in done]
            o8.update({"date": o8d.isoformat(), "prev_close": r(prev_c, 2), "bars": o8_bars})

        # pattern strips
        strips = {
            "k5": patterns.strip(self.b5.bars, 12),
            "k60": patterns.strip(self.b60.bars, 12),
            "kS": patterns.strip(self.bS.bars, 12),
        }
        latest_hit = None
        for name, key in (("日/夜K", "kS"), ("60K", "k60"), ("5K", "k5")):
            h = patterns.latest_hit(strips[key])
            if h:
                latest_hit = {"tf": name, "t": h["t"], "pattern": h["pattern"]}
                break

        # status
        mono = time.monotonic()
        tick_age = (mono - self.last_tick_mono) if self.last_tick_mono else None
        if live_s:
            remain = (live_s.end - now).total_seconds()
            sess_label, countdown_label = live_s.label, "收盤倒數"
        else:
            ns = next_session(now, self.holidays)
            remain = (ns.start - now).total_seconds()
            sess_label, countdown_label = "休市", f"{ns.label}開盤倒數"
        st = self.store.status()
        feed_ok = bool(self.feed and getattr(self.feed, "connected", False))
        cur_bar = self.b5.bars[-1] if self.b5.bars else None
        snap = {
            "ts": now.strftime("%Y-%m-%d %H:%M:%S"),
            "mode": self.settings.mode,
            "session": {
                "kind": s.kind if live_s else None,
                "label": sess_label,
                "key": s.key,
                "trading_date": s.trading_date.isoformat(),
                "countdown_label": countdown_label,
                "countdown_s": max(0, int(remain)),
                "open": live_s is not None,
            },
            "status": {
                "feed_connected": feed_ok,
                "feed_text": getattr(self.feed, "status_text", "ok") if self.feed else "none",
                "tick_age_s": r(tick_age, 1),
                "driver_lag_s": r(self.last_lag, 2),
                "calc_ms": 0.0,
                "api": {"port": self.settings.api_port, "ok": True},
                "engine": {"port": self.settings.engine_port, "ok": (mono - self.worker_alive) < 10 or self.queue.empty()},
                "store": {"port": self.settings.store_port, "ok": st["error"] is None and (st["flush_age"] or 0) < 5,
                          "rows": st["rows"], "pending": st["pending"]},
                "regime": scoring.regime(v3["net"], bb["width"] if bb else None, bb["prev_width"] if bb else None),
                "queue": self.queue.qsize(),
            },
            "quotes": {
                "txf": {
                    **card("TXF"),
                    "open": txf.s_open,
                    "high": hi,
                    "low": lo,
                    "range_pos": r(range_pos * 100 if range_pos is not None else None, 1),
                    "amplitude": r(hi - lo, 0) if (hi is not None and lo is not None) else None,
                    "amplitude_pct": r((hi - lo) / ref_close * 100, 2) if (hi is not None and lo is not None and ref_close) else None,
                },
                "mxf": card("MXF"),
                "tmf": card("TMF"),
                "next": {**card("TXF2"), "spread": r(self.p["TXF2"].last.close - px, 0)
                         if (self.p["TXF2"].last and px is not None) else None},
                "basis": {
                    "basis": basis,
                    "label": None if basis is None else ("正價差" if basis > 0 else "逆價差" if basis < 0 else "平價"),
                    "spot": r(spot_px, 2),
                    "spot_ref": r(sp.reference, 2) if sp else None,
                    "spot_amount_e8": r(sp.amount_sum / self.settings.spot_amount_divisor, 1) if sp and sp.amount_sum else None,
                    "underlying": r(underlying, 2),
                },
                "vwap": {
                    "vwap": r(vwap, 2),
                    "dev_pct": r((px - vwap) / vwap * 100, 3) if (px is not None and vwap) else None,
                    "self_vwap": r(vwap_self, 2),
                    "check_diff": r(self.vwap_check, 3),
                },
                "volume": {
                    "total": last.total_volume if last and txf.session_key == s.key else 0,
                    "ratio5": r(self._vol_ratio(s, now), 2),
                    "bar_volume": cur_bar.v if cur_bar and cur_bar.session == s.key else None,
                },
                "v3": {"verdict": v3["verdict"], "net": v3["net"], "n_available": v3["n_available"],
                       "n_items": v3["n_items"]},
            },
            "flow": {"badge": flow_badge, "txf": fl["TXF"], "mxf": fl["MXF"], "tmf": fl["TMF"]},
            "tech": {
                "ma5": [{"n": n, "value": r(ma5[n], 1), "slope": r(sl5[n], 2)} for n in MA5],
                "ma5_label": ind.ma_alignment(ma5, (3, 12, 60), (180, 228, 300)),
                "ma60": [{"n": n, "value": r(ma60[n], 1), "slope": r(sl60[n], 2)} for n in MA60],
                "ma60_close": closes60[-1] if closes60 else None,
                "ma60_label": ind.simple_alignment([ma60[n] for n in MA60]),
                "boll": {k: r(v, 3 if k == "pct_b" else 2) for k, v in bb.items()} if bb else None,
                "macd": {k: r(v, 2) for k, v in mac.items()} if mac else None,
            },
            "levels": levels,
            "patterns": {**strips, "latest": latest_hit},
            "opening8": o8,
            "v3": v3,
        }
        return snap


def reconcile(rebuilt: List[Bar], broker: List[Bar], tol: float = 0.0) -> List[dict]:
    """Compare rebuilt bars with broker bars (same timeframe). Returns the differences."""
    bmap = {b.t: b for b in broker}
    diffs = []
    for b in rebuilt:
        o = bmap.get(b.t)
        if o is None:
            diffs.append({"t": b.t.isoformat(), "issue": "missing_in_broker"})
            continue
        for f in ("o", "h", "l", "c"):
            if abs(getattr(b, f) - getattr(o, f)) > tol:
                diffs.append({"t": b.t.isoformat(), "issue": f"{f}_mismatch", "rebuilt": getattr(b, f),
                              "broker": getattr(o, f)})
        if b.v != o.v:
            diffs.append({"t": b.t.isoformat(), "issue": "v_mismatch", "rebuilt": b.v, "broker": o.v})
    rset = {b.t for b in rebuilt}
    for o in broker:
        if o.t not in rset:
            diffs.append({"t": o.t.isoformat(), "issue": "missing_in_rebuilt"})
    return diffs
