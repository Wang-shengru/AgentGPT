from datetime import datetime, timedelta

from twtx.engine import reconcile
from twtx.kbar import Bar, BarSeries, aggregate_bars, build_bars

D = datetime.fromisoformat


def test_rebuild_5k_ohlcv_and_flow(tick):
    ts = [tick("2026-11-19 08:45:00", 100, 5, 0), tick("2026-11-19 08:46:00", 103, 2, 1),
          tick("2026-11-19 08:47:00", 98, 1, 2), tick("2026-11-19 08:49:59", 101, 3, 1),
          tick("2026-11-19 08:50:00", 102, 1, 1)]
    bars = build_bars(ts, 5)
    assert len(bars) == 2
    b = bars[0]
    assert (b.o, b.h, b.l, b.c, b.v) == (100, 103, 98, 101, 11)
    assert (b.buy_cnt, b.sell_cnt, b.buy_vol, b.sell_vol) == (2, 1, 5, 1)
    assert b.closed and not bars[1].closed


def test_simtrade_never_enters_bars(tick):
    ts = [tick("2026-11-19 08:45:00", 100), tick("2026-11-19 08:46:00", 999, sim=True)]
    b = build_bars(ts, 5)
    assert len(b) == 1 and b[0].h == 100


def test_closing_tick_folds_into_last_bar(tick):
    ts = [tick("2026-11-19 13:41:00", 100), tick("2026-11-19 13:45:00.2", 105)]
    b = build_bars(ts, 5)
    assert len(b) == 1 and b[0].t == D("2026-11-19 13:40:00") and b[0].c == 105


def test_session_boundary_starts_new_bar(tick):
    ts = [tick("2026-11-19 13:44:00", 100), tick("2026-11-19 15:00:00", 110)]
    b = build_bars(ts, 60)
    assert [x.t for x in b] == [D("2026-11-19 12:45:00"), D("2026-11-19 15:00:00")]
    assert b[0].session != b[1].session


def test_60k_alignment_from_session_start(tick):
    b = build_bars([tick("2026-11-19 09:44:59", 1), tick("2026-11-19 09:45:00", 2)], 60)
    assert [x.t for x in b] == [D("2026-11-19 08:45:00"), D("2026-11-19 09:45:00")]


def test_session_bar(tick):
    b = build_bars([tick("2026-11-19 09:00:00", 1), tick("2026-11-19 13:00:00", 5), tick("2026-11-19 16:00:00", 3)], "S")
    assert len(b) == 2 and b[0].h == 5 and b[1].t == D("2026-11-19 15:00:00")


def test_out_of_order_tick_dropped(tick):
    s = BarSeries(5)
    s.on_tick(tick("2026-11-19 09:10:00", 100))
    bar, _ = s.on_tick(tick("2026-11-19 09:01:00", 50))
    assert bar is None and len(s.bars) == 1


def test_close_through(tick):
    s = BarSeries(5)
    s.on_tick(tick("2026-11-19 09:01:00", 100))
    s.close_through(D("2026-11-19 09:04:59"))
    assert not s.bars[-1].closed
    s.close_through(D("2026-11-19 09:05:00"))
    assert s.bars[-1].closed


def test_aggregate_and_reconcile(tick):
    ticks = [tick(f"2026-11-19 09:0{i}:10", 100 + i, 1) for i in range(10)]
    rebuilt = build_bars(ticks, 5)
    one_min = [Bar(D(f"2026-11-19 09:0{i}:00"), 100 + i, 100 + i, 100 + i, 100 + i, 1, closed=True) for i in range(10)]
    agg = aggregate_bars(one_min, 5)
    assert reconcile(rebuilt, agg) == []
    agg[0].c += 1
    diffs = reconcile(rebuilt, agg)
    assert diffs and diffs[0]["issue"] == "c_mismatch"
