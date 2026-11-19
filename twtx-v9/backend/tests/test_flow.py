import pytest

from twtx.flow import FlowTracker
from twtx.ticks import BidAsk


def test_txdelta_counts_ignore_type0(tick):
    f = FlowTracker(exclude_opening=False)
    for tt in (1, 1, 2, 0, 1):
        f.on_tick(tick("2026-11-19 09:00:00", 100, 1, tt), "A")
    s = f.snapshot()
    assert (s["tx_buy"], s["tx_sell"], s["tx_delta"]) == (3, 1, 2)


def test_vodelta_excludes_opening_auction(tick):
    f = FlowTracker(exclude_opening=True)
    f.on_tick(tick("2026-11-19 08:45:00", 100, 500, 1, ask=500), "A")  # opening match
    f.on_tick(tick("2026-11-19 08:45:01", 100, 3, 1, ask=503), "A")
    f.on_tick(tick("2026-11-19 08:45:02", 100, 1, 2, ask=503, bid=1), "A")
    s = f.snapshot()
    assert (s["vo_buy"], s["vo_sell"], s["vo_delta"]) == (3, 1, 2)
    assert s["buy_ratio"] == pytest.approx(75.0)
    assert s["buy_ratio_exchange"] == pytest.approx(75.0)  # baseline removes the opening 500


def test_opening_kept_when_configured(tick):
    f = FlowTracker(exclude_opening=False)
    f.on_tick(tick("2026-11-19 08:45:00", 100, 500, 1, ask=500), "A")
    assert f.snapshot()["vo_delta"] == 500


def test_scale_only_grows_and_resets_on_session_change(tick):
    f = FlowTracker(exclude_opening=False)
    for _ in range(30):
        f.on_tick(tick("2026-11-19 09:00:00", 100, 1, 1), "D")
    big = f.snapshot()["scale_tx"]
    assert big == 30
    for _ in range(10):
        f.on_tick(tick("2026-11-19 09:00:01", 100, 1, 2), "D")
    assert f.snapshot()["tx_delta"] == 20 and f.snapshot()["scale_tx"] == 30  # does not shrink
    f.on_tick(tick("2026-11-19 15:00:00", 100, 1, 2), "N")  # 日→夜
    s = f.snapshot()
    assert s["tx_delta"] == -1 and s["scale_tx"] == 20  # reset to minimum scale


def test_iodelta_and_scale(tick):
    from datetime import datetime

    f = FlowTracker()
    b = BidAsk("TXFL6", datetime(2026, 11, 19, 9), 150, 50, [], [], [], [])
    f.on_bidask(b, "D")
    s = f.snapshot()
    assert s["io_delta"] == 100 and s["scale_io"] == 100


def test_simtrade_ignored(tick):
    f = FlowTracker(exclude_opening=False)
    f.on_tick(tick("2026-11-19 08:40:00", 100, 9, 1, sim=True), "D")
    assert f.snapshot()["tx_buy"] == 0
