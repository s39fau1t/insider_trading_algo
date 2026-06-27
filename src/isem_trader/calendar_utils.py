from __future__ import annotations

from datetime import date, timedelta

from .models import EarningsEvent, EarningsTiming


def entry_date_for_event(event: EarningsEvent, run_date: date) -> date | None:
    if event.timing == EarningsTiming.AMC and event.report_date == run_date:
        return run_date
    if event.timing in {EarningsTiming.BMO, EarningsTiming.INTRADAY}:
        if event.report_date == next_weekday(run_date):
            return run_date
    return None


def exit_date_for_event(event: EarningsEvent) -> date:
    if event.timing in {EarningsTiming.BMO, EarningsTiming.INTRADAY}:
        return event.report_date
    return next_weekday(event.report_date)


def next_weekday(day: date) -> date:
    current = day + timedelta(days=1)
    while current.weekday() >= 5:
        current += timedelta(days=1)
    return current
