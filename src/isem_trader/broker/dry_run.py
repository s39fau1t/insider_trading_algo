from __future__ import annotations

from .base import FillResult


class DryRunBroker:
    def __init__(self, funds: float = 100_000.0):
        self.funds = funds

    def available_funds(self) -> float:
        return self.funds

    def position_size(self, ticker: str) -> int:
        return 0

    def place_entry_with_stop(
        self,
        ticker: str,
        quantity: int,
        reference_price: float,
        stop_loss_pct: float,
    ) -> FillResult:
        stop_price = round(reference_price * (1 - stop_loss_pct), 2)
        return FillResult(
            entry_order_id=None,
            stop_order_id=None,
            avg_fill_price=reference_price,
            stop_price=stop_price,
        )

    def submit_moc_exit(self, ticker: str, quantity: int) -> int | None:
        return None

    def cancel_order(self, order_id: int) -> None:
        return None

    def close(self) -> None:
        return None
