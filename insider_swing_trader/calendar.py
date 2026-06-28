from __future__ import annotations

from datetime import date, timedelta

from .models import EarningsEvent, EarningsTiming, TradeWindow


def is_trading_day(day: date) -> bool:
    return day.weekday() < 5


def previous_trading_day(day: date) -> date:
    cursor = day - timedelta(days=1)
    while not is_trading_day(cursor):
        cursor -= timedelta(days=1)
    return cursor


def next_trading_day(day: date) -> date:
    cursor = day + timedelta(days=1)
    while not is_trading_day(cursor):
        cursor += timedelta(days=1)
    return cursor


def trade_window_for_event(event: EarningsEvent) -> TradeWindow | None:
    if event.timing == EarningsTiming.UNKNOWN:
        return None
    if event.timing in {EarningsTiming.BMO, EarningsTiming.DURING}:
        entry_date = previous_trading_day(event.earnings_date)
        exit_date = event.earnings_date
    elif event.timing == EarningsTiming.AMC:
        entry_date = event.earnings_date
        exit_date = next_trading_day(event.earnings_date)
    else:
        return None
    return TradeWindow(
        ticker=event.ticker,
        earnings_date=event.earnings_date,
        timing=event.timing,
        entry_date=entry_date,
        exit_date=exit_date,
    )

