"""TAIFEX contract-month helpers (near-month code, settlement day, rollover)."""
from __future__ import annotations

import calendar
from datetime import date

MONTH_LETTERS = "ABCDEFGHIJKL"  # Jan..Dec for futures


def settlement_day(year: int, month: int) -> date:
    """Third Wednesday of the month (TAIFEX index futures final settlement)."""
    c = calendar.Calendar()
    weds = [d for d in c.itermonthdates(year, month) if d.month == month and d.weekday() == 2]
    return weds[2]


def near_month(trading_date: date) -> tuple[int, int]:
    """(year, month) of the near-month contract on a trading date (rolls after settlement)."""
    y, m = trading_date.year, trading_date.month
    if trading_date > settlement_day(y, m):
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return y, m


def next_month(y: int, m: int) -> tuple[int, int]:
    return (y + 1, 1) if m == 12 else (y, m + 1)


def code_for(root: str, y: int, m: int) -> str:
    return f"{root}{MONTH_LETTERS[m - 1]}{y % 10}"


def near_code(root: str, trading_date: date) -> str:
    return code_for(root, *near_month(trading_date))


def next_code(root: str, trading_date: date) -> str:
    return code_for(root, *next_month(*near_month(trading_date)))
