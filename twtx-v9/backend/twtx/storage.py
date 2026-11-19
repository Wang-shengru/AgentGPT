"""8010 落地 tick：每筆 tick 寫入 SQLite，依交易日（夜盤歸屬次一交易日）分檔.

Writes are buffered in memory and flushed from a worker thread so the asyncio loop never
blocks on disk I/O.
"""
from __future__ import annotations

import sqlite3
import threading
import time
from datetime import date, datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from .ticks import IndexQuote, Tick

TICK_COLS = (
    "product", "code", "dt", "close", "volume", "total_volume", "tick_type",
    "bid_side_total_vol", "ask_side_total_vol", "avg_price", "underlying_price",
    "open", "high", "low", "simtrade",
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS ticks (
  product TEXT, code TEXT, dt TEXT, close REAL, volume INTEGER, total_volume INTEGER,
  tick_type INTEGER, bid_side_total_vol INTEGER, ask_side_total_vol INTEGER,
  avg_price REAL, underlying_price REAL, open REAL, high REAL, low REAL, simtrade INTEGER
);
CREATE INDEX IF NOT EXISTS ix_ticks ON ticks(product, dt);
CREATE TABLE IF NOT EXISTS idx (
  code TEXT, dt TEXT, close REAL, reference REAL, open REAL, high REAL, low REAL, amount_sum REAL
);
CREATE INDEX IF NOT EXISTS ix_idx ON idx(dt);
"""


def _tick_row(t: Tick) -> tuple:
    return (t.product, t.code, t.dt.isoformat(timespec="microseconds"), t.close, t.volume, t.total_volume,
            t.tick_type, t.bid_side_total_vol, t.ask_side_total_vol, t.avg_price, t.underlying_price,
            t.open, t.high, t.low, int(t.simtrade))


def _row_tick(r: tuple) -> Tick:
    return Tick(code=r[1], dt=datetime.fromisoformat(r[2]), close=r[3], volume=r[4], total_volume=r[5],
                tick_type=r[6], bid_side_total_vol=r[7], ask_side_total_vol=r[8], avg_price=r[9],
                underlying_price=r[10], open=r[11], high=r[12], low=r[13], simtrade=bool(r[14]), product=r[0])


class TickStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._buf: List[Tuple[date, str, tuple]] = []
        self._lock = threading.Lock()
        self.rows_written = 0
        self.last_flush: Optional[float] = None
        self.last_error: Optional[str] = None
        self.pending = 0

    def path(self, trading_date: date) -> Path:
        return self.root / f"{trading_date.strftime('%Y%m%d')}.sqlite"

    def _conn(self, trading_date: date) -> sqlite3.Connection:
        c = sqlite3.connect(self.path(trading_date))
        c.executescript(SCHEMA)
        return c

    # ---- write path -------------------------------------------------------------------
    def put_tick(self, trading_date: date, t: Tick) -> None:
        with self._lock:
            self._buf.append((trading_date, "t", _tick_row(t)))
            self.pending = len(self._buf)

    def put_index(self, trading_date: date, q: IndexQuote) -> None:
        with self._lock:
            self._buf.append((trading_date, "i", (q.code, q.dt.isoformat(timespec="microseconds"), q.close,
                                                  q.reference, q.open, q.high, q.low, q.amount_sum)))
            self.pending = len(self._buf)

    def flush(self) -> int:
        with self._lock:
            buf, self._buf = self._buf, []
            self.pending = 0
        if not buf:
            self.last_flush = time.time()
            return 0
        by_day: Dict[date, Dict[str, list]] = {}
        for d, kind, row in buf:
            by_day.setdefault(d, {"t": [], "i": []})[kind].append(row)
        try:
            for d, rows in by_day.items():
                c = self._conn(d)
                with c:
                    if rows["t"]:
                        c.executemany(f"INSERT INTO ticks VALUES ({','.join('?' * len(TICK_COLS))})", rows["t"])
                    if rows["i"]:
                        c.executemany("INSERT INTO idx VALUES (?,?,?,?,?,?,?,?)", rows["i"])
                c.close()
            self.rows_written += len(buf)
            self.last_flush = time.time()
            self.last_error = None
        except Exception as e:  # pragma: no cover - disk errors
            self.last_error = str(e)
        return len(buf)

    def write_many(self, trading_date: date, ticks: Iterable[Tick], idx: Iterable[IndexQuote] = ()) -> None:
        c = self._conn(trading_date)
        with c:
            c.executemany(f"INSERT INTO ticks VALUES ({','.join('?' * len(TICK_COLS))})", [_tick_row(t) for t in ticks])
            c.executemany("INSERT INTO idx VALUES (?,?,?,?,?,?,?,?)",
                          [(q.code, q.dt.isoformat(timespec="microseconds"), q.close, q.reference, q.open, q.high,
                            q.low, q.amount_sum) for q in idx])
        c.close()

    # ---- read path --------------------------------------------------------------------
    def days(self) -> List[date]:
        out = []
        for p in sorted(self.root.glob("*.sqlite")):
            try:
                out.append(datetime.strptime(p.stem, "%Y%m%d").date())
            except ValueError:
                continue
        return out

    def load_ticks(self, trading_date: date, product: Optional[str] = None) -> List[Tick]:
        p = self.path(trading_date)
        if not p.exists():
            return []
        c = sqlite3.connect(p)
        try:
            q = "SELECT * FROM ticks"
            args: tuple = ()
            if product:
                q += " WHERE product=?"
                args = (product,)
            rows = c.execute(q + " ORDER BY dt, total_volume", args).fetchall()
        finally:
            c.close()
        return [_row_tick(r) for r in rows]

    def load_index(self, trading_date: date) -> List[IndexQuote]:
        p = self.path(trading_date)
        if not p.exists():
            return []
        c = sqlite3.connect(p)
        try:
            rows = c.execute("SELECT * FROM idx ORDER BY dt").fetchall()
        finally:
            c.close()
        return [IndexQuote(r[0], datetime.fromisoformat(r[1]), r[2], r[3], r[4], r[5], r[6], r[7]) for r in rows]

    def status(self) -> dict:
        lag = None if self.last_flush is None else time.time() - self.last_flush
        return {"rows": self.rows_written, "pending": self.pending, "flush_age": lag, "error": self.last_error}
