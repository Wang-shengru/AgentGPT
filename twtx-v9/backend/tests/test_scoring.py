import json

import pytest

from twtx import scoring
from twtx.scoring import DEFAULT_PARAMS, grade, load_params, summarize


def it(group, d, s, voting=True, available=True, key=None):
    return {"key": key or f"{group}{d}{s}", "group": group, "label": "", "direction": d, "strength": s, "value": 0,
            "display": "", "text": "", "voting": voting, "available": available}


def test_grade_thresholds():
    th = [1, 3, 6, 12]
    assert grade(0.5, th) == (0, 1)
    assert grade(1, th) == (1, 1)
    assert grade(-3, th) == (-1, 2)
    assert grade(7, th) == (1, 3)
    assert grade(-100, th) == (-1, 4)
    assert grade(None, th) == (0, 1)


def test_group_score_is_mean_of_dir_times_strength_over_4():
    items = [it("ma", 1, 4), it("ma", 1, 2), it("ma", -1, 2), it("ma", 0, 1)]
    out = summarize(items, DEFAULT_PARAMS)
    g = out["groups"][0]
    assert g["score"] == pytest.approx((1 + 0.5 - 0.5 + 0) / 4)


def test_net_is_sum_of_groups_and_bounded():
    items = [it(g, 1, 4) for g in ("ma", "pos", "flow", "pat")]
    out = summarize(items, DEFAULT_PARAMS)
    assert out["net"] == 4 and out["verdict"] == "極偏多"


def test_non_voting_and_unavailable_excluded():
    items = [it("flow", 1, 4), it("flow", -1, 4, voting=False), it("flow", -1, 4, available=False)]
    out = summarize(items, DEFAULT_PARAMS)
    assert out["groups"][2]["score"] == 1.0
    assert out["n_items"] == 2 and out["n_available"] == 1


def test_consistency_formula():
    items = [it("ma", 1, 1, key=f"b{i}") for i in range(11)] + [it("pos", -1, 1, key=f"s{i}") for i in range(2)]
    out = summarize(items, DEFAULT_PARAMS)
    assert out["consistency"] == pytest.approx(9 / 13 * 100, abs=0.1)
    assert out["bull"] == 11 and out["bear"] == 2


@pytest.mark.parametrize("net,verdict", [(0.49, "中性"), (0.5, "中性偏多"), (-1.49, "中性偏空"), (1.5, "偏多"),
                                         (-3.0, "偏空"), (3.01, "極偏多")])
def test_verdict_thresholds(net, verdict):
    # construct a single group whose score equals net/1 by spreading across groups
    per = net / 4
    items = []
    for g in ("ma", "pos", "flow", "pat"):
        d = 1 if per > 0 else -1
        items.append(it(g, d, 4, key=g + "a"))
        # mix in a neutral to scale group score to |per|
        frac = abs(per)
        if frac < 1:
            # score = (1*1 + 0*k)/(k+1) -> pick weights via strength
            items[-1]["strength"] = round(frac * 4 * 1000) / 1000
    out = summarize(items, DEFAULT_PARAMS)
    assert out["net"] == pytest.approx(net, abs=1e-3)
    assert out["verdict"] == verdict


def test_thirteen_voting_items_by_default():
    voting = [k for k, v in DEFAULT_PARAMS["items"].items() if v["voting"]]
    assert len(voting) == 13
    groups = {g for g, _ in scoring.GROUPS}
    assert {v["group"] for v in DEFAULT_PARAMS["items"].values()} == groups


def test_missing_data_marks_unavailable():
    out = scoring.score({"price": 27000.0})
    assert out["n_available"] < 13
    assert all(not i["available"] or i["voting"] is not None for g in out["groups"] for i in g["items"])


def test_full_features_all_available():
    f = {"price": 27000.0, "m5_12": 27010, "m5_180": 26950, "m5_180_slope": 1.0, "m5_60_slopes3": [0.5, 0.4, 0.3],
         "h60_25_slope": 3.0, "macd": {"dif": 5, "dea": 3, "osc": 2, "osc_prev": 1}, "boll": {"pct_b": 0.8},
         "vwap": 26980, "range_pos": 0.8, "tx_pct": 8, "recent5_tx_rel": 6, "weighted_vol": 2, "vo_pct": 4,
         "recent5_vo_pct": 3, "mxf_tx_pct": 1, "tmf_tx_pct": 1, "pat5": {"pattern": "多頭吞噬", "bias": 1, "body_ratio": 0.7},
         "pat60": {"pattern": None, "bias": 0, "body_ratio": 0}}
    out = scoring.score(f)
    assert out["n_available"] == 13 and out["groups_available"] == 4
    assert out["net"] > 1.5 and "多" in out["verdict"]
    texts = " ".join(i["text"] for g in out["groups"] for i in g["items"])
    assert "買進" not in texts and "賣出" not in texts and "建議" not in texts


def test_params_override(tmp_path):
    p = tmp_path / "p.json"
    p.write_text(json.dumps({"items": {"vo_pct": {"voting": True}}, "verdict": {"neutral": 1.0}}))
    params = load_params(str(p))
    assert params["items"]["vo_pct"]["voting"] is True
    assert params["verdict"]["neutral"] == 1.0 and params["verdict"]["lean"] == 1.5
    assert DEFAULT_PARAMS["items"]["vo_pct"]["voting"] is False  # defaults untouched
