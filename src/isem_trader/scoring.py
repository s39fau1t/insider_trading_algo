from __future__ import annotations

from datetime import date

from .config import StrategyConfig
from .models import (
    CandidateScore,
    EarningsEvent,
    InsiderTransaction,
    ScoreBreakdown,
    SignalWindow,
)

C_SUITE_KEYWORDS = (
    "ceo",
    "chief executive",
    "cfo",
    "chief financial",
    "coo",
    "chief operating",
    "cto",
    "chief technology",
    "president",
)
BOARD_KEYWORDS = ("director", "board")
OWNER_KEYWORDS = ("10%", "ten percent", "beneficial owner", "beneficial")


def classify_window(
    transaction_date: date,
    prior_earnings_date: date,
    next_earnings_date: date,
    config: StrategyConfig,
) -> SignalWindow:
    if transaction_date <= prior_earnings_date or transaction_date > next_earnings_date:
        return SignalWindow.OUTSIDE

    days_after_prior = (transaction_date - prior_earnings_date).days
    days_before_next = (next_earnings_date - transaction_date).days

    if days_after_prior <= config.post_earnings_exclusion_days:
        return SignalWindow.EXCLUDED
    if days_before_next <= config.final_no_signal_days:
        return SignalWindow.FINAL
    if days_before_next <= config.late_window_days:
        return SignalWindow.LATE
    return SignalWindow.CORE


def score_candidate(
    event: EarningsEvent,
    prior_earnings_date: date,
    transactions: list[InsiderTransaction],
    run_date: date,
    config: StrategyConfig,
) -> CandidateScore:
    qualifying = [
        tx
        for tx in transactions
        if _is_qualifying(tx, event, prior_earnings_date, config)
    ]

    windows = {
        tx: classify_window(
            tx.transaction_date,
            prior_earnings_date,
            event.report_date,
            config,
        )
        for tx in qualifying
    }
    scored = [
        tx
        for tx, window in windows.items()
        if window in {SignalWindow.CORE, SignalWindow.LATE}
    ]

    buyer_count = len({tx.buyer_id or tx.buyer_name for tx in scored})
    insider_count = min(buyer_count, 5) * 5

    roles = [tx.role.lower() for tx in scored]
    role_weighting = 0
    if any(_contains_any(role, C_SUITE_KEYWORDS) for role in roles):
        role_weighting += 10
    if any(_contains_any(role, BOARD_KEYWORDS + OWNER_KEYWORDS) for role in roles):
        role_weighting += 5
    if any(tx.is_congress for tx in scored):
        role_weighting += 5

    has_late = any(windows[tx] == SignalWindow.LATE for tx in scored)
    has_core = any(windows[tx] == SignalWindow.CORE for tx in scored)
    timing_quality = 20 if has_late else 10 if has_core else 0

    velocity = 0
    if len(scored) > 1:
        velocity += 10
    if _has_increasing_third_volume(scored, prior_earnings_date, event.report_date):
        velocity += 10

    congress_lag_adjustment = 0
    if any(
        tx.is_congress
        and tx.disclosed_date is not None
        and (run_date - tx.disclosed_date).days <= config.congress_recent_disclosure_days
        and windows[tx] == SignalWindow.LATE
        for tx in scored
    ):
        congress_lag_adjustment = 5

    breakdown = ScoreBreakdown(
        insider_count=insider_count,
        role_weighting=min(role_weighting, 20),
        timing_quality=timing_quality,
        velocity=min(velocity, 20),
        congress_lag_adjustment=congress_lag_adjustment,
    )
    return CandidateScore(
        event=event,
        prior_earnings_date=prior_earnings_date,
        transactions=tuple(scored),
        breakdown=breakdown,
        total_purchase_dollars=sum(tx.dollars for tx in scored),
    )


def rank_candidates(candidates: list[CandidateScore], min_score: int) -> list[CandidateScore]:
    eligible = [candidate for candidate in candidates if candidate.score >= min_score]
    return sorted(
        eligible,
        key=lambda candidate: (candidate.score, candidate.total_purchase_dollars),
        reverse=True,
    )


def _is_qualifying(
    tx: InsiderTransaction,
    event: EarningsEvent,
    prior_earnings_date: date,
    config: StrategyConfig,
) -> bool:
    if tx.ticker.upper() != event.ticker.upper():
        return False
    if tx.planned_10b5_1:
        return False
    if tx.dollars < config.min_purchase_dollars:
        return False
    return classify_window(
        tx.transaction_date,
        prior_earnings_date,
        event.report_date,
        config,
    ) in {SignalWindow.CORE, SignalWindow.LATE}


def _contains_any(value: str, needles: tuple[str, ...]) -> bool:
    return any(needle in value for needle in needles)


def _has_increasing_third_volume(
    transactions: list[InsiderTransaction],
    prior_earnings_date: date,
    next_earnings_date: date,
) -> bool:
    if not transactions:
        return False
    total_days = max((next_earnings_date - prior_earnings_date).days, 1)
    buckets = [0.0, 0.0, 0.0]
    for tx in transactions:
        elapsed = max((tx.transaction_date - prior_earnings_date).days, 0)
        idx = min(int(elapsed / total_days * 3), 2)
        buckets[idx] += tx.dollars
    return buckets[0] < buckets[1] < buckets[2]
