"""TWTX V9 backend entry point.

Runs three HTTP services in one asyncio process (ports from .env):
  API_PORT    (8001)  WebSocket /ws, REST /api/*, built frontend
  ENGINE_PORT (8006)  engine health
  STORE_PORT  (8010)  landed-tick store (health / days / ticks)
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .backfill import live_history, mock_history, reconcile_session
from .config import Settings, load_settings
from .engine import Engine
from .session import last_session, session_of
from .storage import TickStore

log = logging.getLogger("twtx")
ROOT = Path(__file__).resolve().parents[2]
DIST = ROOT / "frontend" / "dist"


class App:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.store = TickStore(settings.data_dir / settings.mode / "ticks")
        self.engine = Engine(settings, self.store)
        self.feed = None
        self.ready = False
        self.tasks = []

    async def boot(self) -> None:
        s = self.settings
        eng = self.engine
        if s.is_live:
            from .feeds.shioaji_feed import ShioajiFeed

            self.feed = ShioajiFeed(s, eng.emit)
        else:
            from .feeds.mock import MockFeed

            self.feed = MockFeed(s, eng.emit)
        eng.feed = self.feed
        eng.now_fn = self.feed.now
        t0 = time.monotonic()
        if s.is_live:
            await self.feed.start()  # login + subscribe first; live ticks queue while history loads
            await asyncio.to_thread(live_history, eng, self.feed, self.store, s)
        else:
            n = await asyncio.to_thread(mock_history, eng, self.feed, self.store)
            log.info("mock history: %d events", n)
            await self.feed.start()
        log.info("history ready in %.1fs", time.monotonic() - t0)
        self.tasks += [asyncio.create_task(c) for c in (eng.worker(), eng.snapshot_loop(), eng.flush_loop())]
        if s.is_live:
            self.tasks.append(asyncio.create_task(self.reconcile_loop()))
        self.ready = True

    async def reconcile_loop(self) -> None:
        done = set()
        while True:
            await asyncio.sleep(60)
            now = self.feed.now()
            sess = last_session(now, self.settings.holidays)
            if session_of(now, self.settings.holidays) is None and now - sess.end > timedelta(minutes=5) \
                    and sess.key not in done:
                done.add(sess.key)
                try:
                    n = await asyncio.to_thread(reconcile_session, self.engine, self.feed, sess, ROOT / "logs")
                    log.info("reconcile %s: %d differences", sess.key, n)
                except Exception as e:  # pragma: no cover
                    log.warning("reconcile failed: %s", e)


def api_app(app: App) -> FastAPI:
    api = FastAPI(title="TWTX V9 API")
    api.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])
    eng = app.engine

    @api.get("/api/health")
    def health():
        return {"ok": True, "ready": app.ready, "mode": app.settings.mode}

    @api.get("/api/config")
    def config():  # public settings only — never credentials
        s = app.settings
        return {"mode": s.mode, "api_port": s.api_port, "engine_port": s.engine_port, "store_port": s.store_port,
                "keep_days": s.keep_days}

    @api.get("/api/chart")
    def chart(date: Optional[str] = None):
        return eng.chart(date) if app.ready else {"date": None, "bars": [], "dates": []}

    @api.get("/api/snapshot")
    def snapshot():
        return eng.snapshot() if app.ready else JSONResponse({"ready": False}, status_code=503)

    @api.websocket("/ws")
    async def ws(sock: WebSocket):
        await sock.accept()
        lock = asyncio.Lock()

        async def send(msg: dict) -> None:
            async with lock:
                await sock.send_text(json.dumps(msg, ensure_ascii=False, default=str))

        eng.listeners.append(send)
        try:
            if app.ready:
                await send({"type": "snapshot", "data": eng.snapshot()})
            while True:
                await sock.receive_text()  # keepalive / ignore client messages
        except WebSocketDisconnect:
            pass
        finally:
            if send in eng.listeners:
                eng.listeners.remove(send)

    if DIST.exists():
        api.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

        @api.get("/")
        def index():
            return FileResponse(DIST / "index.html")

    return api


def engine_app(app: App) -> FastAPI:
    e = FastAPI(title="TWTX V9 engine")

    @e.get("/health")
    def health():
        eng = app.engine
        return {"ok": app.ready, "queue": eng.queue.qsize(), "driver_lag_s": eng.last_lag,
                "feed_connected": bool(app.feed and app.feed.connected)}

    return e


def store_app(app: App) -> FastAPI:
    st = FastAPI(title="TWTX V9 tick store")
    st.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])

    @st.get("/health")
    def health():
        return {"ok": True, **app.store.status()}

    @st.get("/days")
    def days():
        return [d.isoformat() for d in app.store.days()]

    @st.get("/ticks")
    def ticks(day: str, product: str = "TXF", limit: int = 1000):
        rows = app.store.load_ticks(date.fromisoformat(day), product)[-limit:]
        return [{"dt": t.dt.isoformat(), "close": t.close, "volume": t.volume, "tick_type": t.tick_type,
                 "simtrade": t.simtrade} for t in rows]

    return st


async def run(settings: Optional[Settings] = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    s = settings or load_settings()
    log.info("TWTX V9 starting in %s mode (ports %s/%s/%s)", s.mode, s.api_port, s.engine_port, s.store_port)
    import socket

    for port in (s.api_port, s.engine_port, s.store_port):
        with socket.socket() as sk:
            sk.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sk.bind((s.bind_host, port))
            except OSError:
                raise SystemExit(f"埠 {port} 已被占用：請關閉先前的 TWTX 或於 .env 修改 API_PORT/ENGINE_PORT/STORE_PORT")
    app = App(s)
    servers = [
        uvicorn.Server(uvicorn.Config(api_app(app), host=s.bind_host, port=s.api_port, log_level="warning")),
        uvicorn.Server(uvicorn.Config(engine_app(app), host=s.bind_host, port=s.engine_port, log_level="warning")),
        uvicorn.Server(uvicorn.Config(store_app(app), host=s.bind_host, port=s.store_port, log_level="warning")),
    ]
    boot = asyncio.create_task(app.boot())
    await asyncio.gather(*(srv.serve() for srv in servers), boot)


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
