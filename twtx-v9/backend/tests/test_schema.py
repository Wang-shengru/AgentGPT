"""schema.ts and schema.py must declare the same interfaces with the same fields, and a real
engine snapshot must conform to the Python schema."""
import re
import typing
from pathlib import Path

import pytest

from twtx import schema

TS = (Path(__file__).resolve().parents[2] / "frontend" / "src" / "schema.ts").read_text(encoding="utf-8")


def ts_interfaces():
    out = {}
    for m in re.finditer(r"export interface (\w+)(?: extends (\w+))? \{(.*?)\n\}", TS, re.S):
        name, parent, body = m.groups()
        fields = re.findall(r"^\s*(\w+)\??:", body, re.M)
        out[name] = (parent, fields)
    for name, (parent, fields) in list(out.items()):
        if parent:
            out[name] = (None, out[parent][1] + fields)
    return {k: v[1] for k, v in out.items()}


def py_typeddicts():
    out = {}
    for name in dir(schema):
        obj = getattr(schema, name)
        if isinstance(obj, type) and typing.is_typeddict(obj):
            out[name] = list(obj.__annotations__.keys())
    return out


def test_same_interfaces_and_fields():
    ts, py = ts_interfaces(), py_typeddicts()
    assert set(ts) == set(py)
    for name in py:
        assert ts[name] == py[name], name


def _check(value, tp, path="snap"):
    origin = typing.get_origin(tp)
    if tp is type(None):
        assert value is None, path
        return
    if origin is typing.Union:
        errs = []
        for a in typing.get_args(tp):
            try:
                _check(value, a, path)
                return
            except AssertionError as e:
                errs.append(str(e))
        raise AssertionError(f"{path}: {errs}")
    if origin is list:
        assert isinstance(value, list), path
        for i, v in enumerate(value):
            _check(v, typing.get_args(tp)[0], f"{path}[{i}]")
        return
    if origin is typing.Literal:
        assert value in typing.get_args(tp), path
        return
    if isinstance(tp, type) and typing.is_typeddict(tp):
        assert isinstance(value, dict), path
        hints = typing.get_type_hints(tp)
        required = set(tp.__required_keys__)
        assert required <= set(value), f"{path}: missing {required - set(value)}"
        assert set(value) <= set(hints), f"{path}: extra {set(value) - set(hints)}"
        for k, v in value.items():
            _check(v, hints[k], f"{path}.{k}")
        return
    if tp is float:
        assert isinstance(value, (int, float)) and not isinstance(value, bool), path
        return
    assert isinstance(value, tp), f"{path}: {type(value)} is not {tp}"


@pytest.fixture(scope="module")
def engine(tmp_path_factory):
    from twtx.backfill import mock_history
    from twtx.config import load_settings
    from twtx.engine import Engine
    from twtx.feeds.mock import MockFeed
    from twtx.storage import TickStore

    s = load_settings()
    s.mock_history_days = 2
    s.data_dir = tmp_path_factory.mktemp("data")
    store = TickStore(s.data_dir / "mock" / "ticks")
    eng = Engine(s, store)
    feed = MockFeed(s, eng.emit)
    eng.feed, eng.now_fn = feed, feed.now
    mock_history(eng, feed, store)
    return eng


def test_snapshot_conforms(engine):
    _check(engine.snapshot(), schema.Snapshot)


def test_chart_payload_conforms(engine):
    c = engine.chart(None)
    assert c["bars"], "mock history should produce bars"
    _check(c, schema.ChartPayload, "chart")


def test_landed_ticks_round_trip(engine):
    days = engine.store.days()
    assert days
    t = engine.store.load_ticks(days[-1], "TXF")
    assert t and all(x.product == "TXF" for x in t)
