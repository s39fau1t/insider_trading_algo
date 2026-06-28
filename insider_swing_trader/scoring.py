from __future__ import annotations

import math
from collections import Counter
from datetime import datetime, timedelta
from typing import Iterable

from .calendar import trade_window_for_event
from .models import (
    CandidateScore,
    CongressTrade,
    EarningsEvent,
    InsiderTrade,
    MarketSnapshot,
)

POST_EARNINGS_EXCLUSION_DAYS = 5
STRONG_SIGNAL_DAYS = 45


def _role_weight(relationship: str) -> float:
    rel = relationship.lower()
    weight = 1.0
    if "ceo" in rel or "chief executive" in rel:
        weight += 1.5
    if "cfo" in rel or "chief financial" in rel:
        weight += 1.2
    if "chair" in rel:
        weight += 0.8
    if "director" in rel:
        weight += 0.6
    if "10pct" in rel:
        weight += 0.4
    return weight


def _value_weight(dollar_value: float) -> float:
    if dollar_value <= 0:
        return 0.2
    return min(4.0, math.log10(dollar_value + 1) - 3.0)


def score_insiders(
    event: EarningsEvent,
    trades: Iterable[InsiderTrade],
    decision_at: datetime,
) -> tuple[float, list[str]]:
    start = event.previous_earnings_date + timedelta(days=POST_EARNINGS_EXCLUSION_DAYS)
    end = event.earnings_date
    relevant = [
        trade
        for trade in trades
        if trade.ticker == event.ticker
        and start <= trade.transaction_date < end
        and trade.disclosed_at <= decision_at
    ]
    if not relevant:
        return 0.0, ["no qualifying public insider trades"]

    score = 0.0
    reasons: list[str] = []
    buyers: set[str] = set()
    purchase_dates: list = []
    sales_value = 0.0
    for trade in relevant:
        days_before = max(1, (event.earnings_date - trade.transaction_date).days)
        recency = 1.0
        if days_before <= STRONG_SIGNAL_DAYS:
            recency += (STRONG_SIGNAL_DAYS - days_before) / STRONG_SIGNAL_DAYS
        value = _value_weight(trade.dollar_value)
        role = _role_weight(trade.relationship)
        if trade.code == "P":
            buyers.add(trade.owner_name)
            purchase_dates.append(trade.transaction_date)
            direct_bonus = 0.4 if (trade.direct_or_indirect or "").upper() == "D" else 0.0
            contribution = (1.0 + value) * role * recency + direct_bonus
            score += contribution
        elif trade.code == "S":
            sales_value += trade.dollar_value
            score -= max(0.8, (1.0 + value) * 0.9)
        else:
            score -= 0.25

    if len(buyers) >= 2:
        score += min(3.0, len(buyers) * 0.75)
        reasons.append(f"cluster buying by {len(buyers)} insiders")
    if purchase_dates:
        counts = Counter((event.earnings_date - day).days <= 21 for day in purchase_dates)
        if counts[True] >= 2:
            score += 1.5
            reasons.append("recent insider buying velocity increased")
        reasons.append(f"{len(purchase_dates)} open-market purchase(s)")
    if sales_value:
        reasons.append(f"sales penalty on ${sales_value:,.0f} disclosed sales")
    return round(score, 3), reasons


def score_congress(
    event: EarningsEvent,
    trades: Iterable[CongressTrade],
    decision_at: datetime,
) -> tuple[float, list[str]]:
    start = event.previous_earnings_date
    relevant = [
        trade
        for trade in trades
        if trade.ticker == event.ticker
        and start <= trade.transaction_date < event.earnings_date
        and datetime.combine(trade.disclosure_date, datetime.min.time()) <= decision_at
    ]
    score = 0.0
    reasons: list[str] = []
    for trade in relevant:
        amount_weight = min(1.5, math.log10(max(1.0, trade.estimated_amount)) - 3.0)
        tx_type = trade.transaction_type.lower()
        if "purchase" in tx_type or "buy" in tx_type:
            score += max(0.2, amount_weight) * 0.45
        elif "sale" in tx_type or "sell" in tx_type:
            score -= max(0.2, amount_weight) * 0.3
    if score > 0:
        reasons.append("congressional purchase disclosure booster")
    elif score < 0:
        reasons.append("congressional sale disclosure penalty")
    return round(score, 3), reasons


def liquidity_score(snapshot: MarketSnapshot | None) -> tuple[float, list[str]]:
    if snapshot is None:
        return 0.0, ["no market snapshot"]
    score = 0.0
    reasons: list[str] = []
    if snapshot.last_price >= 5:
        score += 0.5
    if snapshot.average_volume >= 1_000_000:
        score += 0.75
        reasons.append("high liquidity")
    elif snapshot.average_volume >= 300_000:
        score += 0.3
        reasons.append("acceptable liquidity")
    return score, reasons


def score_event(
    event: EarningsEvent,
    insider_trades: Iterable[InsiderTrade],
    congress_trades: Iterable[CongressTrade],
    decision_at: datetime,
    snapshot: MarketSnapshot | None = None,
) -> CandidateScore | None:
    window = trade_window_for_event(event)
    if window is None:
        return None
    insider_score, insider_reasons = score_insiders(event, insider_trades, decision_at)
    congress_score, congress_reasons = score_congress(event, congress_trades, decision_at)
    liq_score, liq_reasons = liquidity_score(snapshot)
    total = round(insider_score + congress_score + liq_score, 3)
    return CandidateScore(
        event=event,
        window=window,
        insider_score=insider_score,
        congress_score=congress_score,
        liquidity_score=liq_score,
        total_score=total,
        reasons=insider_reasons + congress_reasons + liq_reasons,
        market_snapshot=snapshot,
    )

