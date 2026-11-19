"""盤面現況分析 V3 — 13 voting items in 4 equal-weight groups (each group ±1, net ±4).

Every item returns::

    {key, group, label, direction: +1/0/−1, strength: 1–4, value, text, voting, available}

* group score  = mean over voting+available items of direction × strength / 4   (±1)
* net          = Σ group scores                                                 (±4)
* consistency  = |majority items − minority items| ÷ available voting items × 100
* verdict      : |net| < 0.5 中性; 0.5–1.5 中性偏X; 1.5–3 偏X; > 3 極偏X

All thresholds live in ``DEFAULT_PARAMS`` and can be overridden with a JSON file
(``SCORING_PARAMS_FILE``). The output is descriptive only — never advice.
"""
from __future__ import annotations

import copy
import json
from typing import Any, Callable, Dict, List, Optional, Sequence

GROUPS = [
    ("ma", "均線結構"),
    ("pos", "位置動能"),
    ("flow", "成交流"),
    ("pat", "型態"),
]

# thresholds: [t1, t2, t3, t4]: |x| < t1 -> neutral; >= t1 strength 1, >= t2 -> 2, >= t3 -> 3, >= t4 -> 4
DEFAULT_PARAMS: Dict[str, Any] = {
    "items": {
        # --- 均線結構 ---
        "ma_cross": {"group": "ma", "label": "5K 12ma vs 180ma", "th": [5, 20, 50, 100], "voting": True},
        "ma180_slope": {"group": "ma", "label": "5K 180ma 斜率", "th": [0.05, 0.2, 0.5, 1.0], "voting": True},
        "ma60_slope3": {"group": "ma", "label": "近 3 根 60ma 斜率同向", "th": [0.1, 0.5, 1.5, 3.0], "voting": True},
        "h60_ma25_slope": {"group": "ma", "label": "60K 25ma 斜率", "th": [0.5, 2, 5, 10], "voting": True},
        # --- 位置動能 ---
        "macd_osc": {"group": "pos", "label": "5K MACD 柱狀", "th": [0.2, 1, 3, 6], "voting": True},
        "boll_pctb": {"group": "pos", "label": "布林 %b", "th": [0.1, 0.2, 0.35, 0.5], "voting": True},
        "vwap_dev": {"group": "pos", "label": "VWAP 偏差", "th": [3, 10, 25, 50], "voting": True},
        "range_pos": {"group": "pos", "label": "本時段高低區間位置", "th": [0.1, 0.2, 0.3, 0.42], "voting": True},
        # --- 成交流 ---
        "tx_pct": {"group": "flow", "label": "大台買筆/賣筆差 %", "th": [1, 3, 6, 12], "voting": True},
        "recent5_tx_pct": {"group": "flow", "label": "近 5 分買賣筆差 %（vs 同時段中位數）", "th": [2, 5, 10, 20], "voting": True},
        "weighted_vol": {"group": "flow", "label": "加權量差 ÷ 本時段量", "th": [0.5, 1.5, 3, 6], "voting": True},
        "vo_pct": {"group": "flow", "label": "大台買口/賣口差 %", "th": [1, 3, 6, 12], "voting": False},
        "recent5_vo_pct": {"group": "flow", "label": "近 5 分買賣口差 %", "th": [2, 5, 10, 20], "voting": False},
        "mxf_tx_pct": {"group": "flow", "label": "小台買賣筆差 %（參考）", "th": [1, 3, 6, 12], "voting": False},
        "tmf_tx_pct": {"group": "flow", "label": "微台買賣筆差 %（參考）", "th": [1, 3, 6, 12], "voting": False},
        # --- 型態 ---
        "pat5": {"group": "pat", "label": "5K 最近型態", "th": [0.0, 0.3, 0.55, 0.8], "voting": True},
        "pat60": {"group": "pat", "label": "60K 最近型態", "th": [0.0, 0.3, 0.55, 0.8], "voting": True},
    },
    "verdict": {"neutral": 0.5, "lean": 1.5, "strong": 3.0},
    "consistency": {"high": 70, "mid": 40},
    "pattern_lookback": 3,
}


def load_params(path: str = "") -> Dict[str, Any]:
    p = copy.deepcopy(DEFAULT_PARAMS)
    if path:
        with open(path, encoding="utf-8") as f:
            user = json.load(f)
        for k, v in user.items():
            if k == "items" and isinstance(v, dict):
                for ik, iv in v.items():
                    p["items"].setdefault(ik, {}).update(iv)
            elif isinstance(v, dict) and isinstance(p.get(k), dict):
                p[k].update(v)
            else:
                p[k] = v
    return p


def grade(x: Optional[float], th: Sequence[float]) -> tuple[int, int]:
    """Signed value -> (direction, strength 1..4)."""
    if x is None:
        return 0, 1
    a = abs(x)
    if a < th[0] or (th[0] == 0 and a == 0):
        return 0, 1
    s = 1
    for i, t in enumerate(th[1:], start=2):
        if a >= t:
            s = i
    return (1 if x > 0 else -1), s


def _fmt(x: Optional[float], nd: int = 1, suffix: str = "") -> str:
    if x is None:
        return "—"
    return f"{x:+.{nd}f}{suffix}"


def _item(key: str, cfg: dict, value: Optional[float], signed: Optional[float], text: str,
          available: bool = True, display: Optional[str] = None) -> dict:
    d, s = grade(signed if available else None, cfg["th"])
    return {
        "key": key,
        "group": cfg["group"],
        "label": cfg["label"],
        "direction": d if available else 0,
        "strength": s if available else 0,
        "value": value,
        "display": display if display is not None else ("—" if value is None else f"{value:.2f}"),
        "text": text if available else "資料不足（不可用）",
        "voting": bool(cfg.get("voting", True)),
        "available": bool(available),
    }


def _dir_word(d: int) -> str:
    return "偏多" if d > 0 else "偏空" if d < 0 else "中性"


def compute_items(f: Dict[str, Any], params: Dict[str, Any]) -> List[dict]:
    """``f`` = features dict produced by the engine (see engine._features)."""
    P = params["items"]
    out: List[dict] = []
    px = f.get("price")

    def bp(x: Optional[float]) -> Optional[float]:
        return None if (x is None or not px) else x / px * 1e4

    # 1. 短長均線相對位置
    m12, m180 = f.get("m5_12"), f.get("m5_180")
    v = bp(m12 - m180) if (m12 is not None and m180 is not None) else None
    out.append(_item("ma_cross", P["ma_cross"], v, v,
                     (f"12ma 高於 180ma {abs(v):.0f}bp" if (v or 0) >= 0 else f"12ma 低於 180ma {abs(v):.0f}bp") if v is not None else "",
                     v is not None, _fmt(v, 0, "bp")))
    # 2. 180ma 斜率 (bp/bar)
    v = bp(f.get("m5_180_slope"))
    out.append(_item("ma180_slope", P["ma180_slope"], v, v,
                     f"180ma {'上彎' if (v or 0) > 0 else '下彎' if (v or 0) < 0 else '走平'}", v is not None, _fmt(v, 2, "bp")))
    # 3. 近 3 根 60ma 斜率同向
    sl = f.get("m5_60_slopes3")
    if sl and len(sl) == 3 and all(x is not None for x in sl):
        same = all(x > 0 for x in sl) or all(x < 0 for x in sl)
        tot = bp(sum(sl))
        signed = tot if same else 0.0
        txt = ("連 3 根上彎" if sl[0] > 0 else "連 3 根下彎") if same else "斜率方向不一"
        out.append(_item("ma60_slope3", P["ma60_slope3"], tot, signed, txt, True, _fmt(tot, 2, "bp")))
    else:
        out.append(_item("ma60_slope3", P["ma60_slope3"], None, None, "", False))
    # 4. 60K 25ma 斜率
    v = bp(f.get("h60_25_slope"))
    out.append(_item("h60_ma25_slope", P["h60_ma25_slope"], v, v,
                     f"60K 25ma {'上彎' if (v or 0) > 0 else '下彎' if (v or 0) < 0 else '走平'}", v is not None, _fmt(v, 1, "bp")))

    # 5. MACD 柱
    mac = f.get("macd")
    if mac:
        v = bp(mac["osc"])
        grow = abs(mac["osc"]) >= abs(mac["osc_prev"])
        txt = f"DIF {'在上' if mac['dif'] >= mac['dea'] else '在下'}，柱狀{'擴大' if grow else '收斂'}"
        out.append(_item("macd_osc", P["macd_osc"], mac["osc"], v, txt, True, f"{mac['osc']:+.1f}"))
    else:
        out.append(_item("macd_osc", P["macd_osc"], None, None, "", False))
    # 6. 布林 %b (centered at 0.5)
    bb = f.get("boll")
    if bb:
        pb = bb["pct_b"]
        out.append(_item("boll_pctb", P["boll_pctb"], pb, pb - 0.5,
                         "近上軌" if pb > 0.8 else "近下軌" if pb < 0.2 else "中軌之上" if pb >= 0.5 else "中軌之下",
                         True, f"{pb:.2f}"))
    else:
        out.append(_item("boll_pctb", P["boll_pctb"], None, None, "", False))
    # 7. VWAP 偏差
    vw = f.get("vwap")
    v = bp(px - vw) if (vw and px) else None
    out.append(_item("vwap_dev", P["vwap_dev"], v, v, f"現價{'高於' if (v or 0) >= 0 else '低於'} VWAP",
                     v is not None, _fmt(v, 0, "bp")))
    # 8. 區間位置
    rp = f.get("range_pos")
    out.append(_item("range_pos", P["range_pos"], rp, None if rp is None else rp - 0.5,
                     "位於區間上緣" if (rp or 0) > 0.7 else "位於區間下緣" if (rp or 0) < 0.3 else "位於區間中段",
                     rp is not None, "—" if rp is None else f"{rp * 100:.0f}%"))

    # 9–15. 成交流
    for key, fk, txt_fn in [
        ("tx_pct", "tx_pct", lambda x: f"買筆{'多於' if x >= 0 else '少於'}賣筆"),
        ("recent5_tx_pct", "recent5_tx_rel", lambda x: f"近 5 分筆差較同時段中位數{'偏買' if x >= 0 else '偏賣'}"),
        ("weighted_vol", "weighted_vol", lambda x: f"時間加權口差{'偏買' if x >= 0 else '偏賣'}"),
        ("vo_pct", "vo_pct", lambda x: f"買口{'多於' if x >= 0 else '少於'}賣口"),
        ("recent5_vo_pct", "recent5_vo_pct", lambda x: f"近 5 分口差{'偏買' if x >= 0 else '偏賣'}"),
        ("mxf_tx_pct", "mxf_tx_pct", lambda x: "小台參考，僅顯示不投票"),
        ("tmf_tx_pct", "tmf_tx_pct", lambda x: "微台參考，僅顯示不投票"),
    ]:
        x = f.get(fk)
        out.append(_item(key, P[key], x, x, txt_fn(x) if x is not None else "", x is not None, _fmt(x, 1, "%")))

    # 16–17. 型態
    for key, fk in (("pat5", "pat5"), ("pat60", "pat60")):
        pinfo = f.get(fk)
        if pinfo is None:
            out.append(_item(key, P[key], None, None, "", False))
            continue
        name, bias, br = pinfo.get("pattern"), pinfo.get("bias", 0), pinfo.get("body_ratio", 0.0)
        if not name:
            out.append(_item(key, P[key], 0.0, 0.0, "近期無型態", True, "—"))
        else:
            signed = bias * max(br, 0.01) if bias else 0.0
            it = _item(key, P[key], br, signed, f"{name}（{pinfo.get('t', '')}），實體佔距 {br * 100:.0f}%", True,
                       f"{br * 100:.0f}%")
            out.append(it)
    return out


def summarize(items: List[dict], params: Dict[str, Any]) -> dict:
    groups = []
    net = 0.0
    for gkey, gname in GROUPS:
        g_items = [i for i in items if i["group"] == gkey]
        votes = [i for i in g_items if i["voting"] and i["available"]]
        score = sum(i["direction"] * i["strength"] / 4 for i in votes) / len(votes) if votes else 0.0
        net += score
        groups.append({
            "key": gkey,
            "name": gname,
            "score": round(score, 4),
            "available": bool(votes),
            "n_voting": len([i for i in g_items if i["voting"]]),
            "n_available": len(votes),
            "items": g_items,
        })
    voting = [i for i in items if i["voting"]]
    avail = [i for i in voting if i["available"]]
    bull = sum(1 for i in avail if i["direction"] > 0)
    bear = sum(1 for i in avail if i["direction"] < 0)
    neu = len(avail) - bull - bear
    consistency = abs(bull - bear) / len(avail) * 100 if avail else 0.0
    v = params["verdict"]
    a = abs(net)
    side = "多" if net > 0 else "空"
    if a < v["neutral"]:
        verdict = "中性"
    elif a < v["lean"]:
        verdict = f"中性偏{side}"
    elif a <= v["strong"]:
        verdict = f"偏{side}"
    else:
        verdict = f"極偏{side}"
    c = params["consistency"]
    if verdict == "中性":
        sentence = f"多空均衡（{bull} 多 / {bear} 空）"
    elif consistency >= c["high"]:
        sentence = f"{verdict}，且相當一致（{bull} 多 / {bear} 空）"
    elif consistency >= c["mid"]:
        sentence = f"{verdict}，但不算一致（{bull} 多 / {bear} 空）"
    else:
        sentence = f"{verdict}，多空分歧（{bull} 多 / {bear} 空）"
    return {
        "net": round(net, 3),
        "verdict": verdict,
        "sentence": sentence,
        "consistency": round(consistency, 1),
        "bull": bull,
        "bear": bear,
        "neutral": neu,
        "n_available": len(avail),
        "n_items": len(voting),
        "groups_available": sum(1 for g in groups if g["available"]),
        "n_groups": len(groups),
        "groups": groups,
    }


def score(features: Dict[str, Any], params: Optional[Dict[str, Any]] = None) -> dict:
    params = params or DEFAULT_PARAMS
    return summarize(compute_items(features, params), params)


def regime(net: float, bb_width: Optional[float], bb_prev_width: Optional[float]) -> str:
    """Descriptive market regime for the status capsule."""
    expanding = bb_width is not None and bb_prev_width is not None and bb_width > bb_prev_width
    if abs(net) >= 1.5 and expanding:
        return "趨勢盤"
    if abs(net) >= 1.5:
        return "偏趨勢"
    return "盤整盤"
