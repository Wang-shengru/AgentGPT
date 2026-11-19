"""Candlestick pattern recognition on closed bars (descriptive only)."""
from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from .kbar import Bar

# name -> bias (+1 bullish reading, −1 bearish reading, 0 neutral)
PATTERN_BIAS = {
    "晨星": 1,
    "夜星": -1,
    "多頭吞噬": 1,
    "空頭吞噬": -1,
    "多頭孕線": 1,
    "空頭孕線": -1,
    "錘子": 1,
    "倒錘": 1,
    "上吊": -1,
    "射擊之星": -1,
    "十字": 0,
}


def _parts(b: Bar) -> Tuple[float, float, float, float]:
    rng = b.h - b.l
    body = abs(b.c - b.o)
    upper = b.h - max(b.o, b.c)
    lower = min(b.o, b.c) - b.l
    return rng, body, upper, lower


def color(b: Bar, doji_ratio: float = 0.1) -> str:
    rng, body, _, _ = _parts(b)
    if rng == 0 or body <= doji_ratio * rng:
        return "doji"
    return "up" if b.c > b.o else "down"


def body_ratio(b: Bar) -> float:
    rng, body, _, _ = _parts(b)
    return body / rng if rng else 0.0


def _trend(bars: Sequence[Bar], i: int, look: int = 3) -> int:
    """Prior trend before bar i: +1 rising, −1 falling, 0 flat/unknown."""
    if i - look < 0:
        return 0
    a, b = bars[i - look].c, bars[i - 1].c
    if b > a:
        return 1
    if b < a:
        return -1
    return 0


def detect_at(bars: Sequence[Bar], i: int, doji_ratio: float = 0.1) -> Optional[str]:
    """Detect the strongest pattern completing on bar i."""
    b = bars[i]
    rng, body, upper, lower = _parts(b)
    if rng <= 0:
        return None
    trend = _trend(bars, i)
    # 3-bar patterns
    if i >= 2:
        a, m = bars[i - 2], bars[i - 1]
        ra, ba, _, _ = _parts(a)
        rm, bm, _, _ = _parts(m)
        long_a = ra > 0 and ba >= 0.6 * ra
        small_m = rm == 0 or bm <= 0.3 * max(rm, 1e-9) or bm <= 0.35 * ba
        mid_a = (a.o + a.c) / 2
        if long_a and small_m and a.c < a.o and b.c > b.o and b.c > mid_a:
            return "晨星"
        if long_a and small_m and a.c > a.o and b.c < b.o and b.c < mid_a:
            return "夜星"
    # 2-bar patterns
    if i >= 1:
        p = bars[i - 1]
        rp, bp, _, _ = _parts(p)
        real_p = rp > 0 and bp >= 0.3 * rp  # previous bar is not a doji
        if real_p and trend <= 0 and p.c < p.o and b.c > b.o and b.c >= p.o and b.o <= p.c and body > bp:
            return "多頭吞噬"
        if real_p and trend >= 0 and p.c > p.o and b.c < b.o and b.c <= p.c and b.o >= p.o and body > bp:
            return "空頭吞噬"
        long_p = rp > 0 and bp >= 0.6 * rp
        if long_p and body <= 0.4 * bp and max(b.o, b.c) <= max(p.o, p.c) and min(b.o, b.c) >= min(p.o, p.c):
            if p.c < p.o and trend < 0:
                return "多頭孕線"
            if p.c > p.o and trend > 0:
                return "空頭孕線"
    # 1-bar patterns
    if body <= doji_ratio * rng:
        return "十字"
    if lower >= 2 * body and upper <= max(body * 0.5, rng * 0.1):
        if trend < 0:
            return "錘子"
        if trend > 0:
            return "上吊"
    if upper >= 2 * body and lower <= max(body * 0.5, rng * 0.1):
        if trend > 0:
            return "射擊之星"
        if trend < 0:
            return "倒錘"
    return None


def strip(bars: Sequence[Bar], n: int = 12, doji_ratio: float = 0.1) -> List[dict]:
    """Last n closed bars as colour cells with any detected pattern."""
    closed = [b for b in bars if b.closed]
    start = max(0, len(closed) - n)
    out = []
    for i in range(start, len(closed)):
        b = closed[i]
        p = detect_at(closed, i, doji_ratio)
        out.append(
            {
                "t": b.t.strftime("%m/%d %H:%M"),
                "color": color(b, doji_ratio),
                "pattern": p,
                "bias": PATTERN_BIAS.get(p, 0) if p else 0,
                "body_ratio": round(body_ratio(b), 3),
            }
        )
    return out


def latest_hit(cells: List[dict]) -> Optional[dict]:
    for c in reversed(cells):
        if c["pattern"]:
            return c
    return None
