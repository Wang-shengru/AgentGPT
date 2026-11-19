"""Runtime configuration, read from environment / .env (never sent to the frontend)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

try:  # optional dependency
    from dotenv import load_dotenv

    _ROOT = Path(__file__).resolve().parents[2]
    load_dotenv(_ROOT / ".env")
    load_dotenv(_ROOT / "backend" / ".env")
except Exception:  # pragma: no cover
    pass


def _bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    if v is None or v == "":
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "") or default)
    except ValueError:
        return default


def _holidays() -> frozenset[date]:
    out = set()
    for s in (os.environ.get("HOLIDAYS") or "").split(","):
        s = s.strip()
        if s:
            try:
                out.add(date.fromisoformat(s))
            except ValueError:
                pass
    return frozenset(out)


@dataclass
class Settings:
    mode: str = "mock"
    api_key: str = ""
    secret_key: str = ""
    simulation: bool = False
    api_port: int = 8001
    engine_port: int = 8006
    store_port: int = 8010
    bind_host: str = "127.0.0.1"
    data_dir: Path = Path("./data")
    exclude_opening_auction: bool = True
    keep_days: int = 10
    volume_ratio_days: int = 5
    holidays: frozenset = field(default_factory=frozenset)
    spot_amount_divisor: float = 1e8
    mock_speed: float = 1.0
    mock_history_days: int = 25
    mock_seed: int = 9
    scoring_params_file: str = ""

    @property
    def is_live(self) -> bool:
        return self.mode == "live"


def load_settings() -> Settings:
    api_key = os.environ.get("SJ_API_KEY", "")
    secret = os.environ.get("SJ_SECRET_KEY", "")
    mode = (os.environ.get("TWTX_MODE") or "").strip().lower()
    if mode not in ("mock", "live"):
        mode = "live" if (api_key and secret) else "mock"
    if mode == "live" and not (api_key and secret):
        mode = "mock"  # no key -> always fall back to mock so the UI still runs
    data_dir = Path(os.environ.get("DATA_DIR") or "./data")
    if not data_dir.is_absolute():
        data_dir = Path(__file__).resolve().parents[2] / data_dir
    return Settings(
        mode=mode,
        api_key=api_key,
        secret_key=secret,
        simulation=_bool("SJ_SIMULATION", False),
        api_port=_int("API_PORT", 8001),
        engine_port=_int("ENGINE_PORT", 8006),
        store_port=_int("STORE_PORT", 8010),
        bind_host=os.environ.get("BIND_HOST") or "127.0.0.1",
        data_dir=data_dir,
        exclude_opening_auction=_bool("EXCLUDE_OPENING_AUCTION", True),
        keep_days=_int("KEEP_DAYS", 10),
        volume_ratio_days=_int("VOLUME_RATIO_DAYS", 5),
        holidays=_holidays(),
        spot_amount_divisor=_float("SPOT_AMOUNT_DIVISOR", 1e8),
        mock_speed=max(0.1, _float("MOCK_SPEED", 1.0)),
        mock_history_days=_int("MOCK_HISTORY_DAYS", 25),
        mock_seed=_int("MOCK_SEED", 9),
        scoring_params_file=os.environ.get("SCORING_PARAMS_FILE", ""),
    )
