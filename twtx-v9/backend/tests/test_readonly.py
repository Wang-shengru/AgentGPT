"""Hard check: the terminal never trades, never activates a CA, never queries accounts."""
import re
from pathlib import Path

import pytest

from twtx.feeds.shioaji_feed import ReadOnlyApi

PKG = Path(__file__).resolve().parents[1] / "twtx"
FORBIDDEN_CALL = re.compile(
    r"\.(activate_ca|place_order|update_order|cancel_order|place_comboorder|cancel_comboorder|update_status|"
    r"list_accounts|account_balance|margin|list_positions|list_profit_loss|list_settlements|settlements|"
    r"list_trades|trading_limits)\s*\("
)


def test_no_trading_or_account_calls_in_source():
    hits = []
    for p in PKG.rglob("*.py"):
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if FORBIDDEN_CALL.search(line):
                hits.append(f"{p.name}:{n}: {line.strip()}")
    assert hits == []


def test_runtime_guard_blocks_trading():
    class Fake:
        def place_order(self, *a):  # pragma: no cover
            raise AssertionError("should never be reached")

        def ticks(self):
            return "ok"

    api = ReadOnlyApi(Fake())
    assert api.ticks() == "ok"
    for name in ("place_order", "activate_ca", "cancel_order", "update_order", "list_positions"):
        with pytest.raises(PermissionError):
            getattr(api, name)


def test_no_advice_wording_in_ui():
    ui = Path(__file__).resolve().parents[2] / "frontend" / "src"
    text = " ".join(p.read_text(encoding="utf-8") for p in ui.rglob("*.ts*"))
    for bad in ("建議買進", "建議賣出", "下單", "買進訊號", "賣出訊號"):
        assert bad not in text
    assert "本系統僅供行情觀察與研究紀錄，不構成任何投資建議。" in text
