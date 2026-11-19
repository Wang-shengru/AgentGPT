"""Pure technical-indicator functions (lists of floats in, numbers out)."""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence


def sma(xs: Sequence[float], n: int, offset: int = 0) -> Optional[float]:
    """Simple MA of the last n values, ``offset`` bars back. None if not enough data."""
    end = len(xs) - offset
    if n <= 0 or end < n:
        return None
    return sum(xs[end - n : end]) / n


def sma_slope(xs: Sequence[float], n: int, lag: int = 1) -> Optional[float]:
    a = sma(xs, n)
    b = sma(xs, n, lag)
    if a is None or b is None:
        return None
    return a - b


def ema_series(xs: Sequence[float], n: int) -> List[float]:
    if not xs:
        return []
    k = 2 / (n + 1)
    out = [xs[0]]
    for x in xs[1:]:
        out.append(out[-1] + k * (x - out[-1]))
    return out


def macd(xs: Sequence[float], fast: int = 12, slow: int = 26, signal: int = 9) -> Optional[Dict[str, float]]:
    """DIF = EMA12 − EMA26, DEA = EMA9(DIF), OSC = DIF − DEA. Needs slow+signal bars."""
    if len(xs) < slow + signal:
        return None
    ef, es = ema_series(xs, fast), ema_series(xs, slow)
    dif = [a - b for a, b in zip(ef, es)]
    dea = ema_series(dif, signal)
    return {
        "dif": dif[-1],
        "dea": dea[-1],
        "osc": dif[-1] - dea[-1],
        "osc_prev": dif[-2] - dea[-2],
    }


def bollinger(xs: Sequence[float], n: int = 20, k: float = 2.0) -> Optional[Dict[str, float]]:
    if len(xs) < n:
        return None
    w = xs[-n:]
    mid = sum(w) / n
    sd = math.sqrt(sum((x - mid) ** 2 for x in w) / n)
    up, dn = mid + k * sd, mid - k * sd
    last = xs[-1]
    width = (up - dn) / mid * 100 if mid else 0.0
    pct_b = (last - dn) / (up - dn) if up != dn else 0.5
    prev_width = None
    if len(xs) >= n + 1:
        w2 = xs[-n - 1 : -1]
        m2 = sum(w2) / n
        sd2 = math.sqrt(sum((x - m2) ** 2 for x in w2) / n)
        prev_width = (2 * k * sd2) / m2 * 100 if m2 else None
    return {"upper": up, "mid": mid, "lower": dn, "width": width, "pct_b": pct_b, "prev_width": prev_width}


def cdp(prev_high: float, prev_low: float, prev_close: float) -> Dict[str, float]:
    """CDP 逆勢操作系統價位：CDP=(H+L+2C)/4, AH=CDP+(H−L), NH=2CDP−L, NL=2CDP−H, AL=CDP−(H−L)."""
    c = (prev_high + prev_low + 2 * prev_close) / 4
    rng = prev_high - prev_low
    return {"AH": c + rng, "NH": 2 * c - prev_low, "CDP": c, "NL": 2 * c - prev_high, "AL": c - rng}


class VwapCalc:
    """Self-computed VWAP, used to cross-check tick.avg_price."""

    def __init__(self) -> None:
        self.pv = 0.0
        self.v = 0

    def reset(self) -> None:
        self.pv, self.v = 0.0, 0

    def add(self, px: float, vol: int) -> None:
        self.pv += px * vol
        self.v += vol

    @property
    def value(self) -> Optional[float]:
        return self.pv / self.v if self.v else None


def ma_alignment(values: Dict[int, Optional[float]], short: Sequence[int], long: Sequence[int]) -> str:
    """Describe MA ordering: 多頭排列 when strictly descending by period ascending, etc."""
    s = [values.get(n) for n in short]
    if all(v is not None for v in s) and len(s) >= 2:
        if all(s[i] > s[i + 1] for i in range(len(s) - 1)):
            short_state = "短多頭"
        elif all(s[i] < s[i + 1] for i in range(len(s) - 1)):
            short_state = "短空頭"
        else:
            short_state = "短交錯"
    else:
        short_state = "短不足"
    l = [values.get(n) for n in long]
    if all(v is not None for v in l) and len(l) >= 2:
        if all(l[i] > l[i + 1] for i in range(len(l) - 1)):
            long_state = "長多頭"
        elif all(l[i] < l[i + 1] for i in range(len(l) - 1)):
            long_state = "長空頭"
        else:
            long_state = "長交錯"
    else:
        long_state = "長不足"
    return f"{short_state}/{long_state}"


def simple_alignment(values: Sequence[Optional[float]]) -> str:
    if any(v is None for v in values) or len(values) < 2:
        return "資料不足"
    if all(values[i] > values[i + 1] for i in range(len(values) - 1)):
        return "多頭"
    if all(values[i] < values[i + 1] for i in range(len(values) - 1)):
        return "空頭"
    return "交錯"
