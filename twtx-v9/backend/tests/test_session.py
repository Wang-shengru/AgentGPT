from datetime import date, datetime

from twtx.session import next_session, next_trading_day, session_of, spot_bar_index

D = datetime.fromisoformat


def test_day_session_bounds():
    assert session_of(D("2026-11-19 08:44:59")) is None
    s = session_of(D("2026-11-19 08:45:00"))
    assert s.kind == "day" and s.trading_date == date(2026, 11, 19)
    assert session_of(D("2026-11-19 13:45:00.500")).kind == "day"  # closing auction tick
    assert session_of(D("2026-11-19 13:47:00")) is None
    assert session_of(D("2026-11-19 14:59:59")) is None


def test_night_session_belongs_to_next_trading_day():
    s = session_of(D("2026-11-19 15:00:00"))
    assert s.kind == "night" and s.trading_date == date(2026, 11, 20)
    s2 = session_of(D("2026-11-20 04:59:59"))
    assert s2.key == s.key
    assert session_of(D("2026-11-20 05:00:30")).key == s.key
    assert session_of(D("2026-11-20 05:02:00")) is None


def test_friday_night_belongs_to_monday():
    s = session_of(D("2026-11-20 21:00:00"))  # Friday
    assert s.trading_date == date(2026, 11, 23)
    assert session_of(D("2026-11-21 03:00:00")).trading_date == date(2026, 11, 23)  # Saturday early morning
    assert session_of(D("2026-11-21 10:00:00")) is None
    assert session_of(D("2026-11-22 16:00:00")) is None  # Sunday


def test_holidays():
    hol = [date(2026, 11, 20)]
    assert session_of(D("2026-11-20 10:00:00"), hol) is None
    assert session_of(D("2026-11-19 20:00:00"), hol).trading_date == date(2026, 11, 23)
    assert next_trading_day(date(2026, 11, 19), hol) == date(2026, 11, 23)


def test_session_switch_changes_key():
    a = session_of(D("2026-11-19 13:44:00"))
    b = session_of(D("2026-11-19 15:00:01"))
    assert a.key != b.key and a.key.endswith("D") and b.key.endswith("N")


def test_bar_index_and_last_bar_folding():
    s = session_of(D("2026-11-19 10:00:00"))
    assert s.n_bars(5) == 60
    assert s.bar_index(D("2026-11-19 08:45:00"), 5) == 0
    assert s.bar_index(D("2026-11-19 08:49:59"), 5) == 0
    assert s.bar_index(D("2026-11-19 08:50:00"), 5) == 1
    assert s.bar_index(D("2026-11-19 13:45:00"), 5) == 59
    n = session_of(D("2026-11-19 16:00:00"))
    assert n.n_bars(5) == 168 and n.n_bars(60) == 14


def test_next_session_countdown():
    ns = next_session(D("2026-11-19 14:00:00"))
    assert ns.kind == "night" and ns.start == D("2026-11-19 15:00:00")
    ns = next_session(D("2026-11-21 10:00:00"))  # Saturday -> Monday day session
    assert ns.start == D("2026-11-23 08:45:00")


def test_spot_bars():
    assert spot_bar_index(D("2026-11-19 08:59:59")) is None
    assert spot_bar_index(D("2026-11-19 09:00:00")) == 0
    assert spot_bar_index(D("2026-11-19 09:14:59")) == 2
