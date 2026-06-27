from __future__ import annotations

from datetime import date

from .calendar_utils import entry_date_for_event, exit_date_for_event
from .config import StrategyConfig
from .data.base import MarketDataProvider
from .models import CandidateScore, SelectedTrade
from .scoring import rank_candidates, score_candidate


def score_daily_candidates(
    provider: MarketDataProvider,
    run_date: date,
    config: StrategyConfig,
) -> list[CandidateScore]:
    scores: list[CandidateScore] = []
    allowed = {exchange.upper() for exchange in config.allowed_exchanges}
    events = provider.get_earnings_events(run_date)
    for event in events:
        if event.exchange and event.exchange.upper() not in allowed:
            continue
        if entry_date_for_event(event, run_date) is None:
            continue
        prior = provider.get_prior_earnings_date(event.ticker, event.report_date)
        if prior is None:
            continue
        transactions = provider.get_insider_transactions(
            event.ticker,
            since=prior,
            until=event.report_date,
        )
        scores.append(score_candidate(event, prior, transactions, run_date, config))
    return scores


def select_trade(
    provider: MarketDataProvider,
    run_date: date,
    available_capital: float,
    config: StrategyConfig,
) -> SelectedTrade | None:
    ranked = rank_candidates(
        score_daily_candidates(provider, run_date, config),
        config.min_score,
    )
    if not ranked:
        return None

    candidate = ranked[0]
    price = provider.get_last_price(candidate.event.ticker)
    if price <= 0:
        return None

    allocatable = available_capital * config.capital_fraction
    quantity = int(allocatable // price)
    if quantity <= 0:
        return None

    return SelectedTrade(
        candidate=candidate,
        entry_date=run_date,
        exit_date=exit_date_for_event(candidate.event),
        reference_price=price,
        quantity=quantity,
        capital_used=quantity * price,
    )
