from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum


class EarningsTiming(StrEnum):
    BMO = "BMO"
    INTRADAY = "INTRADAY"
    AMC = "AMC"


class SignalWindow(StrEnum):
    EXCLUDED = "excluded"
    CORE = "core"
    LATE = "late"
    FINAL = "final"
    OUTSIDE = "outside"


@dataclass(frozen=True)
class EarningsEvent:
    ticker: str
    report_date: date
    timing: EarningsTiming
    exchange: str = ""


@dataclass(frozen=True)
class InsiderTransaction:
    ticker: str
    buyer_id: str
    buyer_name: str
    role: str
    source: str
    transaction_date: date
    shares: float
    price: float
    planned_10b5_1: bool = False
    disclosed_date: date | None = None

    @property
    def dollars(self) -> float:
        return self.shares * self.price

    @property
    def is_congress(self) -> bool:
        return self.source.lower() == "congress"


@dataclass(frozen=True)
class ScoreBreakdown:
    insider_count: int
    role_weighting: int
    timing_quality: int
    velocity: int
    congress_lag_adjustment: int

    @property
    def total(self) -> int:
        return (
            self.insider_count
            + self.role_weighting
            + self.timing_quality
            + self.velocity
            + self.congress_lag_adjustment
        )


@dataclass(frozen=True)
class CandidateScore:
    event: EarningsEvent
    prior_earnings_date: date
    transactions: tuple[InsiderTransaction, ...]
    breakdown: ScoreBreakdown
    total_purchase_dollars: float

    @property
    def score(self) -> int:
        return self.breakdown.total


@dataclass(frozen=True)
class SelectedTrade:
    candidate: CandidateScore
    entry_date: date
    exit_date: date
    reference_price: float
    quantity: int
    capital_used: float
