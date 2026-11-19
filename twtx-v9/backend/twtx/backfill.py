"""Startup history: landed ticks first, then Shioaji history to fill the gap, de-duplicated
by timestamp so live ticks continue without a K-bar gap. Also after-close reconciliation.
"""
from __future__ import annotations

import json
import logging
import shutil
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List

from .kbar import aggregate_bars
from .session import last_session, prev_trading_day, session_of
from .ticks import IndexQuote, Tick

log = logging.getLogger("twtx.backfill")


def mock_history(engine, feed, store) -> int:
    """Regenerate deterministic mock history and land it (mock store is rebuilt every start)."""
    shutil.rmtree(store.root, ignore_errors=True)
    store.root.mkdir(parents=True, exist_ok=True)
    engine.history_mode = True
    n = 0
    for kind, product, obj in feed.history():
        engine.handle(kind, product, obj, land=True)
        n += 1
        if n % 50000 == 0:
            store.flush()
    store.flush()
    engine.history_mode = False
    return n


def live_history(engine, feed, store, settings, days: int = 25) -> None:
    """1) replay landed ticks of the last ``days`` trading days, 2) fetch missing days (TXF) and
    today's gap (all products) with api.ticks, landing what was fetched."""
    now = feed.now()
    cur = last_session(now, settings.holidays)
    td = cur.trading_date
    day_list: List[date] = [td]
    d = td
    for _ in range(days - 1):
        d = prev_trading_day(d, settings.holidays)
        day_list.append(d)
    day_list.reverse()
    engine.history_mode = True
    for d in day_list:
        ticks = store.load_ticks(d)
        idx = store.load_index(d)
        if not ticks and d < td:
            try:
                ticks = feed.history_ticks("TXF", d)
                store.write_many(d, ticks)
                time.sleep(0.25)  # stay well inside the history-query rate limit
            except Exception as e:  # pragma: no cover - network
                log.warning("history %s failed: %s", d, e)
                ticks = []
        if d == td:
            last_dt: Dict[str, datetime] = {}
            for t in ticks:
                last_dt[t.product] = max(last_dt.get(t.product, t.dt), t.dt)
            fetched: List[Tick] = []
            for prod in ("TXF", "MXF", "TMF", "TXF2"):
                try:
                    got = feed.history_ticks(prod, d)
                except Exception as e:  # pragma: no cover - network
                    log.warning("gap backfill %s failed: %s", prod, e)
                    continue
                lim = last_dt.get(prod)
                fetched += [t for t in got if lim is None or t.dt > lim]
                time.sleep(0.25)
            if fetched:
                store.write_many(d, fetched)
            ticks = sorted(ticks + fetched, key=lambda t: t.dt)
        merged: List = [("tick", t.product, t) for t in ticks] + [("index", "IDX", q) for q in idx]
        merged.sort(key=lambda x: x[2].dt)
        for kind, prod, obj in merged:
            engine.handle(kind, prod, obj, land=False)
    engine.history_mode = False


def reconcile_session(engine, feed, sess, log_dir: Path) -> int:
    """Compare rebuilt TXF 5K bars of a finished session with broker kbars; log differences."""
    from .engine import reconcile

    start, end = sess.start, sess.end + timedelta(minutes=1)
    rebuilt = [b for b in engine.b5.bars if start <= b.t < end]
    broker_1m = feed.kbars_1m("TXF", start.date(), end.date())
    broker = [b for b in aggregate_bars(broker_1m, 5, engine.holidays) if start <= b.t < end]
    diffs = reconcile(rebuilt, broker)
    log_dir.mkdir(parents=True, exist_ok=True)
    with open(log_dir / "reconcile.log", "a", encoding="utf-8") as f:
        f.write(json.dumps({"session": sess.key, "checked": len(rebuilt), "diffs": diffs[:500],
                            "n_diffs": len(diffs), "at": datetime.now().isoformat()}, ensure_ascii=False) + "\n")
    return len(diffs)
