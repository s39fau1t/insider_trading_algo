from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Optional


class EarningsTiming(str, Enum):
    BMO = "BMO"
    AMC = "AMC"
    DURING = "DURING"
    UNKNOWN = "UNKNOWN"


class InsiderTransactionCode(str, Enum):
    PURCHASE = "P"
    SALE = "S"


@dataclass(frozen=True)
class EarningsEvent:
    ticker: str
    earnings_date: date
    timing: EarningsTiming
    previous_earnings_date: date


@dataclass(frozen=True)
class TradeWindow:
    ticker: str
    earnings_date: date
    timing: EarningsTiming
    entry_date: date
    exit_date: date


@dataclass(frozen=True)
class InsiderTrade:
    ticker: str
    issuer_name: str
    owner_name: str
    owner_cik: Optional[str]
    relationship: str
    transaction_date: date
    filing_date: date
    disclosed_at: datetime
    code: str
    shares: float
    price: Optional[float]
    direct_or_indirect: Optional[str]
    accession_number: Optional[str] = None

    @property
    def dollar_value(self) -> float:
        if self.price is None:
            return 0.0
        return max(0.0, self.shares) * max(0.0, self.price)


@dataclass(frozen=True)
class CongressTrade:
    ticker: str
    representative: str
    transaction_date: date
    disclosure_date: date
    transaction_type: str
    amount_low: float = 0.0
    amount_high: float = 0.0

    @property
    def estimated_amount(self) -> float:
        if self.amount_low and self.amount_high:
            return (self.amount_low + self.amount_high) / 2
        return self.amount_high or self.amount_low


@dataclass(frozen=True)
class MarketSnapshot:
    ticker: str
    last_price: float
    average_volume: int


@dataclass
class CandidateScore:
    event: EarningsEvent
    window: TradeWindow
    insider_score: float
    congress_score: float
    liquidity_score: float
    total_score: float
    reasons: list[str] = field(default_factory=list)
    market_snapshot: Optional[MarketSnapshot] = None


@dataclass(frozen=True)
class PlannedOrder:
    ticker: str
    action: str
    quantity: int
    order_type: str
    limit_price: Optional[float]
    reason: str


@dataclass(frozen=True)
class OpenPosition:
    ticker: str
    quantity: int
    entry_order_id: str
    entry_at: datetime
    entry_date: date
    exit_date: date
    status: str = "open"
