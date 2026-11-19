import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from twtx.ticks import Tick  # noqa: E402


def mk(dt, px, vol=1, tt=1, product="TXF", sim=False, ask=0, bid=0, code="TXFL6"):
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt)
    return Tick(code, dt, float(px), vol, 0, tt, bid, ask, float(px), 0.0, float(px), float(px), float(px), sim, product)


@pytest.fixture
def tick():
    return mk
