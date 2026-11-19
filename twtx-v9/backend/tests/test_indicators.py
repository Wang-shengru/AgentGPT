import pytest

from twtx import indicators as ind
from twtx import opening8, patterns
from twtx.kbar import Bar
from datetime import datetime, timedelta


def test_sma_and_slope():
    xs = [1, 2, 3, 4, 5]
    assert ind.sma(xs, 3) == 4
    assert ind.sma(xs, 6) is None
    assert ind.sma_slope(xs, 3) == pytest.approx(1)


def test_bollinger_flat_series():
    b = ind.bollinger([10.0] * 20)
    assert b["upper"] == b["lower"] == 10 and b["pct_b"] == 0.5


def test_macd_needs_enough_bars_and_sign():
    assert ind.macd(list(range(20))) is None
    up = ind.macd([float(i) for i in range(60)])
    assert up["dif"] > 0


def test_cdp():
    c = ind.cdp(110, 90, 100)
    assert c["CDP"] == 100 and c["AH"] == 120 and c["NH"] == 110 and c["NL"] == 90 and c["AL"] == 80


def test_vwap_self_calc():
    v = ind.VwapCalc()
    v.add(100, 1)
    v.add(110, 3)
    assert v.value == pytest.approx(107.5)


def _b(i, o, h, l, c):
    return Bar(datetime(2026, 11, 19, 9) + timedelta(minutes=5 * i), o, h, l, c, closed=True)


def test_patterns_engulfing_and_hammer():
    down = [_b(0, 110, 111, 104, 105), _b(1, 105, 106, 99, 100), _b(2, 100, 101, 94, 95)]
    bull = down + [_b(3, 95, 96, 90, 91), _b(4, 90, 98, 89, 97)]
    assert patterns.detect_at(bull, 4) == "多頭吞噬"
    hammer = down + [_b(3, 92, 93.8, 85, 93.5)]  # long lower shadow, body outside the prior body
    assert patterns.detect_at(hammer, 3) == "錘子"
    harami = down + [_b(3, 96, 97, 90, 91), _b(4, 92, 92.5, 91.5, 92.4)]
    assert patterns.detect_at(harami, 4) == "多頭孕線"
    doji = down + [_b(3, 93, 96, 90, 93.1)]  # body outside prior body, otherwise it is a 孕線
    assert patterns.detect_at(doji, 3) == "十字"


def test_shooting_star_after_uptrend():
    up = [_b(0, 100, 106, 99, 105), _b(1, 105, 111, 104, 110), _b(2, 110, 116, 109, 115)]
    bars = up + [_b(3, 115, 125, 114.8, 117)]
    assert patterns.detect_at(bars, 3) == "射擊之星"


def test_opening8_classification():
    assert opening8.classify(100, [101, 102, 103])["name"] == "三點高盤"
    assert opening8.classify(100, [99, 98, 97])["name"] == "三點低盤"
    assert opening8.classify(100, [99, 101, 102])["key"] == "LHH"
    assert opening8.classify(100, [101])["available"] is False
    assert len(opening8.EIGHT) == 8
