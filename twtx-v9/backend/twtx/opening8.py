"""開盤八法：以現貨（加權指數）前三根 5 分 K 收盤相對昨收的高/低，歸入八種開盤型態。

純記錄、不帶策略。傾向文字為描述性（偏多/偏空/震盪），不構成任何操作建議。
"""
from __future__ import annotations

from typing import List, Optional, Sequence

# key: three letters, H = close above previous close, L = at/below previous close
EIGHT = {
    "HHH": ("三點高盤", "偏多", "三根皆在昨收之上，買方主導開盤"),
    "LLL": ("三點低盤", "偏空", "三根皆在昨收之下，賣方主導開盤"),
    "HHL": ("二高一低", "震盪偏多", "開高後第三根回落至昨收下"),
    "HLH": ("高低高", "震盪偏多", "開高、拉回、再站回昨收上"),
    "LHH": ("一低二高", "偏多", "開低後連兩根站回昨收上"),
    "LLH": ("二低一高", "震盪偏空", "開低後第三根才回到昨收上"),
    "LHL": ("低高低", "震盪偏空", "開低、反彈、再跌回昨收下"),
    "HLL": ("一高二低", "偏空", "開高後連兩根跌回昨收下"),
}


def classify(prev_close: Optional[float], closes: Sequence[float]) -> dict:
    """``closes`` = closes of the first three spot 5K bars (09:00, 09:05, 09:10)."""
    if prev_close is None or len(closes) < 3:
        return {
            "available": False,
            "key": None,
            "name": "資料不足" if prev_close is None else f"等待第 {len(closes) + 1} 根",
            "tendency": "—",
            "desc": "現貨前三根 5 分 K 尚未完成",
        }
    key = "".join("H" if c > prev_close else "L" for c in closes[:3])
    name, tendency, desc = EIGHT[key]
    return {"available": True, "key": key, "name": name, "tendency": tendency, "desc": desc}


def all_types() -> List[dict]:
    return [{"key": k, "name": v[0], "tendency": v[1]} for k, v in EIGHT.items()]
