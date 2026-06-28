from __future__ import annotations

from datetime import date, datetime
from typing import Iterable

from .config import Settings
from .models import CandidateScore, CongressTrade, EarningsEvent, InsiderTrade, MarketSnapshot
from .scoring import score_event


class MarketDataProvider:
    def snapshot(self, ticker: str) -> MarketSnapshot | None:
        return None


class StaticMarketDataProvider(MarketDataProvider):
    def __init__(self, snapshots: dict[str, MarketSnapshot] | None = None):
        self.snapshots = snapshots or {}

    def snapshot(self, ticker: str) -> MarketSnapshot | None:
        return self.snapshots.get(ticker.upper())


def rank_candidates(
    events: Iterable[EarningsEvent],
    insider_trades: Iterable[InsiderTrade],
    congress_trades: Iterable[CongressTrade],
    decision_at: datetime,
    settings: Settings,
    market_data: MarketDataProvider | None = None,
) -> list[CandidateScore]:
    insider_list = list(insider_trades)
    congress_list = list(congress_trades)
    provider = market_data or StaticMarketDataProvider()
    candidates: list[CandidateScore] = []
    for event in events:
        snapshot = provider.snapshot(event.ticker)
        if snapshot is None:
            continue
        if snapshot.last_price < settings.min_price:
            continue
        if snapshot.average_volume < settings.min_average_volume:
            continue
        candidate = score_event(event, insider_list, congress_list, decision_at, snapshot)
        if candidate is None:
            continue
        if candidate.total_score >= settings.min_score:
            candidates.append(candidate)
    return sorted(candidates, key=lambda item: item.total_score, reverse=True)


def events_for_window(provider, start: date, end: date) -> list[EarningsEvent]:
    return list(provider.events(start, end))
