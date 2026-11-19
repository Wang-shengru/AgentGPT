"""Live market data from SinoPac Shioaji — READ ONLY.

Written against shioaji 1.7.x (``api.subscribe``, ``api.Contracts``, single-argument v1
callbacks, ``on_event`` / ``on_session_down``) with automatic fallback to the legacy
``api.quote.*`` / ``(exchange, tick)`` callback style of 1.0–1.2.

HARD RULE (enforced by tests/test_readonly.py and by ``ReadOnlyApi`` at runtime): this module
never activates a CA, never touches orders and never queries accounts. Only login,
contracts, quote subscription, ticks/kbars/snapshots history and logout are used.
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from datetime import date, datetime, timedelta
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

from ..contracts import near_code
from ..session import last_session, prev_trading_day, session_of
from ..ticks import MockQuoteIdxV1, ticks_from_history, ts_to_local
from .mock import taipei_now

log = logging.getLogger("twtx.shioaji")

Emit = Callable[[str, str, object], None]

# Attribute names that a read-only terminal must never reach. Kept as a frozenset of plain
# strings so the static test can grep for real *calls* without tripping on this list.
_BLOCKED = frozenset({
    "activate_ca", "place_order", "update_order", "cancel_order", "place_comboorder",
    "cancel_comboorder", "update_status", "list_accounts", "account_balance", "margin",
    "list_positions", "list_position_detail", "list_profit_loss", "list_settlements",
    "settlements", "list_trades", "trading_limits", "subscribe_trade", "reserve_stock",
})


class ReadOnlyApi:
    """Thin proxy over a ``shioaji.Shioaji`` instance that refuses trading / account calls."""

    def __init__(self, api: Any):
        object.__setattr__(self, "_api", api)

    def __getattr__(self, name: str) -> Any:
        if name in _BLOCKED:
            raise PermissionError(f"TWTX is read-only: '{name}' is not allowed")
        return getattr(self._api, name)

    @property
    def raw_quote(self) -> Any:
        return getattr(self._api, "quote", None)


SUBSCRIBE_TICK = ("TXF", "TXF2", "MXF", "TMF")
SUBSCRIBE_BIDASK = ("TXF", "MXF", "TMF")
CONTINUOUS = {"TXF": ("TXF", "TXFR1"), "TXF2": ("TXF", "TXFR2"), "MXF": ("MXF", "MXFR1"), "TMF": ("TMF", "TMFR1")}


class ShioajiFeed:
    name = "live"

    def __init__(self, settings, emit: Emit):
        self.settings = settings
        self.emit_raw = emit
        self.holidays = settings.holidays
        self.api: Optional[ReadOnlyApi] = None
        self.sj: Any = None
        self.contracts: Dict[str, Any] = {}
        self.code_map: Dict[str, str] = {}
        self.display_codes: Dict[str, str] = {}
        self.connected = False
        self.status_text = "init"
        self.last_index_cb = 0.0
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self._reconnecting = threading.Lock()
        self._stop = False
        self._poll_task: Optional[asyncio.Task] = None

    # ------------------------------------------------------------------ clock
    def now(self) -> datetime:
        return taipei_now()

    # ------------------------------------------------------------------ connect
    def _login(self) -> None:
        import shioaji as sj  # imported lazily: mock mode does not need the package

        self.sj = sj
        raw = sj.Shioaji(simulation=self.settings.simulation)
        try:
            raw.login(api_key=self.settings.api_key, secret_key=self.settings.secret_key, subscribe_trade=False)
        except TypeError:
            raw.login(api_key=self.settings.api_key, secret_key=self.settings.secret_key)
        self.api = ReadOnlyApi(raw)
        log.info("shioaji %s logged in (simulation=%s)", getattr(sj, "__version__", "?"), self.settings.simulation)

    def _contracts_root(self) -> Any:
        api = self.api
        c = getattr(api, "Contracts", None)
        if c is None:
            c = getattr(api, "contracts", None)
            if callable(c):
                c = c()
        return c

    def _resolve_future(self, root: str, code: str) -> Any:
        fut = getattr(self._contracts_root(), "Futures")
        for fn in (lambda: fut[code], lambda: fut.get(code), lambda: getattr(getattr(fut, root), code),
                   lambda: getattr(fut, root)[code]):
            try:
                c = fn()
                if c is not None:
                    return c
            except Exception:
                continue
        raise LookupError(f"contract {code} not found")

    def _resolve_index(self) -> Any:
        idx = getattr(self._contracts_root(), "Indexs")
        for fn in (lambda: idx.TSE["001"], lambda: idx.TSE.TSE001, lambda: idx["001"], lambda: idx.get("001"),
                   lambda: idx.TSE.get("001")):
            try:
                c = fn()
                if c is not None:
                    return c
            except Exception:
                continue
        return None

    def _resolve_all(self) -> None:
        self.contracts.clear()
        self.code_map.clear()
        for prod, (root, code) in CONTINUOUS.items():
            c = self._resolve_future(root, code)
            self.contracts[prod] = c
            for attr in ("code", "target_code", "symbol"):
                v = getattr(c, attr, None)
                if v:
                    self.code_map[str(v)] = prod
            self.display_codes[prod] = str(getattr(c, "target_code", "") or getattr(c, "code", code))
        self.contracts["IDX"] = self._resolve_index()

    def _product_of(self, code: str) -> Optional[str]:
        if code in self.code_map:
            return self.code_map[code]
        if code.startswith("MXF"):
            return "MXF"
        if code.startswith("TMF"):
            return "TMF"
        if code.startswith("TXF"):
            return "TXF" if code == self.display_codes.get("TXF") else "TXF2"
        return None

    # ------------------------------------------------------------------ callbacks
    def _emit(self, kind: str, product: str, obj: Any) -> None:
        """Called from Shioaji threads: only enqueue, never compute."""
        if self.loop is not None:
            self.loop.call_soon_threadsafe(self.emit_raw, kind, product, obj)

    def _on_tick(self, *args: Any) -> None:
        tick = args[-1]  # 1.7.x: (tick)   legacy: (exchange, tick)
        p = self._product_of(str(tick.code))
        if p:
            self._emit("tick", p, tick)

    def _on_bidask(self, *args: Any) -> None:
        ba = args[-1]
        p = self._product_of(str(ba.code))
        if p:
            self._emit("bidask", p, ba)

    def _on_index(self, *args: Any) -> None:
        q = args[-1]
        self.last_index_cb = time.time()
        self._emit("index", "IDX", q)

    def _on_event(self, resp_code: int, event_code: int, info: str, event: str) -> None:
        log.info("shioaji event %s/%s %s %s", resp_code, event_code, info, event)
        if event_code in (12,):  # reconnecting
            self.connected = False
            self.status_text = "reconnecting"
        elif event_code in (13,):  # reconnected -> resubscribe to be safe
            self.connected = True
            self.status_text = "reconnected"
            threading.Thread(target=self._subscribe_all, daemon=True).start()

    def _on_session_down(self, *_: Any) -> None:
        log.warning("shioaji session down — scheduling re-login")
        self.connected = False
        self.status_text = "session down"
        if self.loop:
            self.loop.call_soon_threadsafe(lambda: asyncio.ensure_future(self._relogin()))

    def _register_callbacks(self) -> None:
        api = self.api
        q = api.raw_quote if not hasattr(api._api, "set_on_tick_fop_v1_callback") else api._api
        for setter, cb in (("set_on_tick_fop_v1_callback", self._on_tick),
                           ("set_on_bidask_fop_v1_callback", self._on_bidask),
                           ("set_on_quote_idx_v1_callback", self._on_index)):
            fn = getattr(q, setter, None) or getattr(api.raw_quote, setter, None)
            if fn:
                try:
                    fn(cb)
                except Exception as e:  # pragma: no cover
                    log.warning("%s failed: %s", setter, e)
        for name, cb in (("set_event_callback", self._on_event),
                         ("set_session_down_callback", self._on_session_down)):
            fn = getattr(api._api, name, None) or getattr(api.raw_quote, name, None)
            if fn:
                fn(cb)
            elif name == "set_event_callback" and api.raw_quote is not None:
                api.raw_quote.set_event_callback(self._on_event)

    def _subscribe(self, contract: Any, qt: str) -> None:
        sj, api = self.sj, self.api
        quote_type = getattr(sj.QuoteType, qt)
        kw: Dict[str, Any] = {"quote_type": quote_type}
        ver = getattr(getattr(sj, "QuoteVersion", None), "v1", None)
        if ver is not None:
            kw["version"] = ver
        if hasattr(api._api, "subscribe"):
            api._api.subscribe(contract, **kw)
        else:
            api.raw_quote.subscribe(contract, **kw)

    def _subscribe_all(self) -> None:
        for p in SUBSCRIBE_TICK:
            self._subscribe(self.contracts[p], "Tick")
        for p in SUBSCRIBE_BIDASK:
            self._subscribe(self.contracts[p], "BidAsk")
        idx = self.contracts.get("IDX")
        if idx is not None:
            for qt in ("Quote", "Tick"):
                try:
                    self._subscribe(idx, qt)
                    break
                except Exception as e:
                    log.info("index subscribe %s failed: %s", qt, e)
        # 8 subscriptions in total — far below the per-connection subscription limit.

    async def start(self) -> None:
        self.loop = asyncio.get_running_loop()
        await asyncio.to_thread(self._connect_blocking)
        self._poll_task = asyncio.create_task(self._index_poll())

    def _connect_blocking(self) -> None:
        self._login()
        self._resolve_all()
        self._register_callbacks()
        self._subscribe_all()
        self.connected = True
        self.status_text = "ok"

    async def _relogin(self) -> None:
        if not self._reconnecting.acquire(blocking=False):
            return
        try:
            delay = 2.0
            while not self._stop:
                try:
                    try:
                        await asyncio.to_thread(self.api.logout)
                    except Exception:
                        pass
                    await asyncio.to_thread(self._connect_blocking)
                    log.info("re-login ok")
                    return
                except Exception as e:
                    log.warning("re-login failed: %s (retry in %.0fs)", e, delay)
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, 60)
        finally:
            self._reconnecting.release()

    async def _index_poll(self) -> None:
        """Fallback for spot index / turnover: poll a snapshot when no index stream arrives."""
        while not self._stop:
            await asyncio.sleep(5)
            idx = self.contracts.get("IDX")
            if idx is None or not self.connected or time.time() - self.last_index_cb < 10:
                continue
            try:
                snaps = await asyncio.to_thread(self.api.snapshots, [idx])
                if snaps:
                    s = snaps[0]
                    dt = ts_to_local(int(s.ts))
                    q = MockQuoteIdxV1("TSE", "001", dt.date(), dt.time(), dt, "", str(s.open), str(s.high), str(s.low),
                                       str(s.close), str(s.total_amount), None)
                    q.reference = str(float(s.close) - float(s.change_price))
                    self.emit_raw("index", "IDX", q)
            except Exception as e:  # pragma: no cover
                log.debug("snapshot poll failed: %s", e)

    async def stop(self) -> None:
        self._stop = True
        if self._poll_task:
            self._poll_task.cancel()
        if self.api is not None:
            try:
                await asyncio.to_thread(self.api.logout)
            except Exception:
                pass

    # ------------------------------------------------------------------ history
    def history_ticks(self, product: str, day: date) -> List[Any]:
        """api.ticks for one trading date (AllDay) mapped to engine ticks."""
        c = self.contracts[product]
        h = self.api.ticks(contract=c, date=day.isoformat())
        code = self.display_codes.get(product, product)
        return ticks_from_history(h, code, product)

    def kbars_1m(self, product: str, start: date, end: date):
        """Broker 1-minute kbars (used ONLY for after-close reconciliation, never for display)."""
        from ..kbar import Bar

        k = self.api.kbars(contract=self.contracts[product], start=start.isoformat(), end=end.isoformat())
        out = []
        for i, ts in enumerate(k.ts):
            # Shioaji labels a 1-minute kbar with its END minute -> shift to bar start
            t = ts_to_local(int(ts)) - timedelta(minutes=1)
            out.append(Bar(t, float(k.Open[i]), float(k.High[i]), float(k.Low[i]), float(k.Close[i]), int(k.Volume[i]),
                           closed=True))
        return out
