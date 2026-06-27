from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class FillResult:
    entry_order_id: int | None
    stop_order_id: int | None
    avg_fill_price: float
    stop_price: float


class Broker(Protocol):
    def available_funds(self) -> float:
        ...

    def position_size(self, ticker: str) -> int:
        ...

    def place_entry_with_stop(
        self,
        ticker: str,
        quantity: int,
        reference_price: float,
        stop_loss_pct: float,
    ) -> FillResult:
        ...

    def cancel_order(self, order_id: int) -> None:
        ...

    def submit_moc_exit(self, ticker: str, quantity: int) -> int | None:
        ...

    def close(self) -> None:
        ...
