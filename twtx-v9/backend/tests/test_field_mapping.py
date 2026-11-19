"""2.3 欄位對應 — especially 內外盤 direction."""
from dataclasses import fields
from datetime import datetime

import pytest

from twtx.ticks import (BUY, SELL, MockBidAskFOPv1, MockTickFOPv1, bidask_from_fop_v1, tick_from_fop_v1,
                        ticks_from_history)
from twtx.flow import FlowTracker

# fields declared by shioaji 1.7.x _core.pyi for TickFOPv1 / BidAskFOPv1
STUB_TICK = ["exchange", "code", "date", "time", "datetime", "open", "close", "high", "low", "underlying_price",
             "bid_side_total_vol", "ask_side_total_vol", "avg_price", "amount", "total_amount", "volume",
             "total_volume", "tick_type", "chg_type", "price_chg", "pct_chg", "simtrade"]
STUB_BIDASK = ["exchange", "code", "date", "time", "datetime", "bid_total_vol", "ask_total_vol", "bid_price",
               "bid_volume", "diff_bid_vol", "ask_price", "ask_volume", "diff_ask_vol", "first_derived_bid_price",
               "first_derived_ask_price", "first_derived_bid_vol", "first_derived_ask_vol", "underlying_price",
               "simtrade"]


def raw_tick(tt, vol=2, ask=10, bid=4, sim=False, dt="2026-11-19 09:00:01"):
    d = datetime.fromisoformat(dt)
    return MockTickFOPv1("TAIFEX", "TXFL6", d.date(), d.time(), d, "27000", "27001", "27010", "26990", "26980.5",
                         bid, ask, "27000.25", "54002", "999", vol, 100, tt, 1, "1", "0.01", sim)


def test_mock_tick_fields_identical_to_stub():
    assert [f.name for f in fields(MockTickFOPv1)] == STUB_TICK
    assert [f.name for f in fields(MockBidAskFOPv1)] == STUB_BIDASK


def test_mock_fields_exist_on_installed_shioaji():
    sj = pytest.importorskip("shioaji")
    for name in STUB_TICK:
        assert hasattr(sj.TickFOPv1, name), name
    for name in STUB_BIDASK:
        assert hasattr(sj.BidAskFOPv1, name), name


def test_tick_type_1_is_outside_aggressive_buy():
    t = tick_from_fop_v1(raw_tick(1))
    assert t.tick_type == BUY and t.is_buy and not t.is_sell


def test_tick_type_2_is_inside_aggressive_sell():
    t = tick_from_fop_v1(raw_tick(2))
    assert t.tick_type == SELL and t.is_sell


def test_side_totals_not_swapped():
    # ask_side_total_vol = traded at ASK = 外盤 = 主動買; bid_side_total_vol = 內盤 = 主動賣
    t = tick_from_fop_v1(raw_tick(1, ask=30, bid=10))
    assert t.ask_side_total_vol == 30 and t.bid_side_total_vol == 10


def test_buy_ratio_uses_ask_side_as_buy():
    f = FlowTracker(exclude_opening=False)
    f.on_tick(tick_from_fop_v1(raw_tick(1, vol=3, ask=3, bid=0)), "S")
    f.on_tick(tick_from_fop_v1(raw_tick(2, vol=1, ask=3, bid=1)), "S")
    s = f.snapshot()
    assert s["buy_ratio"] == pytest.approx(75.0)
    assert s["buy_ratio_exchange"] == pytest.approx(75.0)


def test_prices_given_as_str_or_decimal_are_parsed():
    from decimal import Decimal

    r = raw_tick(1)
    r.close = Decimal("27001.0")
    assert tick_from_fop_v1(r).close == 27001.0
    assert tick_from_fop_v1(raw_tick(1)).avg_price == 27000.25


def test_tick_type_enum_values():
    class E:
        def __init__(self, v):
            self.value = v

    r = raw_tick(0)
    r.tick_type = E("Buy")
    assert tick_from_fop_v1(r).tick_type == BUY
    r.tick_type = E("Sell")
    assert tick_from_fop_v1(r).tick_type == SELL


def test_simtrade_flag_kept_for_filtering():
    assert tick_from_fop_v1(raw_tick(1, sim=True)).simtrade is True


def test_iodelta_is_bid_minus_ask_total():
    d = datetime(2026, 11, 19, 9, 0, 1)
    b = MockBidAskFOPv1("TAIFEX", "TXFL6", d.date(), d.time(), d, 120, 80, ["1"] * 5, [24] * 5, [0] * 5, ["2"] * 5,
                        [16] * 5, [0] * 5, "0", "0", 0, 0, "0", False)
    assert bidask_from_fop_v1(b).io_delta == 40


def test_history_ticks_rebuild_side_totals():
    class H:
        ts = [int(datetime(2026, 11, 19, 9, 0, i).timestamp() * 1e9) for i in range(3)]
        close = [100.0, 101.0, 100.0]
        volume = [2, 3, 4]
        tick_type = [1, 1, 2]

    out = ticks_from_history(H, "TXFL6", "TXF")
    assert out[-1].ask_side_total_vol == 5 and out[-1].bid_side_total_vol == 4
    assert out[-1].total_volume == 9
