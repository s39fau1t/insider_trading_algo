from datetime import date

from insider_swing_trader.calendar import trade_window_for_event
from insider_swing_trader.models import EarningsEvent, EarningsTiming


def test_bmo_event_enters_previous_trading_day_before_weekend():
    event = EarningsEvent("EXMP", date(2026, 6, 29), EarningsTiming.BMO, date(2026, 3, 30))
    window = trade_window_for_event(event)

    assert window.entry_date == date(2026, 6, 26)
    assert window.exit_date == date(2026, 6, 29)


def test_amc_event_exits_next_trading_day_after_friday():
    event = EarningsEvent("EXMP", date(2026, 6, 26), EarningsTiming.AMC, date(2026, 3, 30))
    window = trade_window_for_event(event)

    assert window.entry_date == date(2026, 6, 26)
    assert window.exit_date == date(2026, 6, 29)


def test_unknown_timing_is_skipped():
    event = EarningsEvent(
        "EXMP",
        date(2026, 6, 26),
        EarningsTiming.UNKNOWN,
        date(2026, 3, 30),
    )

    assert trade_window_for_event(event) is None

