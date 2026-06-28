from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Iterable

from .calendar import previous_trading_day
from .config import Settings
from .models import CandidateScore, CongressTrade, EarningsEvent, InsiderTrade
from .scanner import MarketDataProvider
from .scanner import rank_candidates


@dataclass(frozen=True)
class BacktestDecision:
    decision_at: datetime
    selected: CandidateScore | None
    candidates: list[CandidateScore]


def decision_time_for_event(event: EarningsEvent) -> datetime:
    from .models import EarningsTiming

    if event.timing.name in {"BMO", "DURING"}:
        day = previous_trading_day(event.earnings_date)
    else:
        day = event.earnings_date
    return datetime.combine(day, time(15, 45))


def run_backtest(
    events: Iterable[EarningsEvent],
    insider_trades: Iterable[InsiderTrade],
    congress_trades: Iterable[CongressTrade],
    settings: Settings,
    market_data: MarketDataProvider | None = None,
) -> list[BacktestDecision]:
    decisions: list[BacktestDecision] = []
    for event in sorted(events, key=lambda item: (item.earnings_date, item.ticker)):
        decision_at = decision_time_for_event(event)
        candidates = rank_candidates(
            [event],
            insider_trades,
            congress_trades,
            decision_at,
            settings,
            market_data,
        )
        decisions.append(
            BacktestDecision(
                decision_at=decision_at,
                selected=candidates[0] if candidates else None,
                candidates=candidates,
            )
        )
    return decisions
