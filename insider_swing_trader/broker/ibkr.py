from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time

from insider_swing_trader.config import Settings
from insider_swing_trader.models import CandidateScore, PlannedOrder


@dataclass(frozen=True)
class BrokerAccount:
    available_cash: float


class DryRunBroker:
    def __init__(
        self,
        account: BrokerAccount | None = None,
        positions: dict[str, int] | None = None,
        open_order_tickers: set[str] | None = None,
    ):
        self.account = account or BrokerAccount(available_cash=10_000.0)
        self.positions = {ticker.upper(): quantity for ticker, quantity in (positions or {}).items()}
        self.open_order_tickers = {ticker.upper() for ticker in (open_order_tickers or set())}

    def validate_entry(self, candidate: CandidateScore) -> None:
        if candidate.window.timing.name == "UNKNOWN":
            raise RuntimeError("Refusing to trade unknown earnings timing.")
        if candidate.market_snapshot is None:
            raise RuntimeError("Refusing to trade without market price and volume data.")
        if self.positions.get(candidate.event.ticker, 0) > 0:
            raise RuntimeError(f"Refusing duplicate entry; already long {candidate.event.ticker}.")
        if candidate.event.ticker in self.open_order_tickers:
            raise RuntimeError(f"Refusing entry; open order already exists for {candidate.event.ticker}.")

    def validate_exit(self, ticker: str) -> int:
        quantity = self.positions.get(ticker.upper(), 0)
        if quantity <= 0:
            raise RuntimeError(f"Refusing exit; no long position found for {ticker.upper()}.")
        if ticker.upper() in self.open_order_tickers:
            raise RuntimeError(f"Refusing exit; open order already exists for {ticker.upper()}.")
        return quantity

    def plan_entry_order(self, candidate: CandidateScore, settings: Settings) -> PlannedOrder:
        self.validate_entry(candidate)
        price = candidate.market_snapshot.last_price
        quantity = int((self.account.available_cash * settings.allocation_pct) // price)
        if quantity <= 0:
            raise RuntimeError("Available cash is too low for the selected candidate.")
        return PlannedOrder(
            ticker=candidate.event.ticker,
            action="BUY",
            quantity=quantity,
            order_type="MKT",
            limit_price=None,
            reason=f"score={candidate.total_score}",
        )

    def plan_exit_order(self, ticker: str) -> PlannedOrder:
        quantity = self.validate_exit(ticker)
        return PlannedOrder(
            ticker=ticker.upper(),
            action="SELL",
            quantity=quantity,
            order_type="MKT",
            limit_price=None,
            reason="earnings swing exit",
        )

    def place_order(self, order: PlannedOrder) -> str:
        return f"dry-run-{order.ticker}-{order.quantity}"


class IbkrBroker(DryRunBroker):
    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings
        self.ib = None

    def connect(self) -> None:
        try:
            from ib_async import IB
        except ImportError as exc:
            raise RuntimeError(
                "Install broker dependencies with: python -m pip install -e '.[broker]'"
            ) from exc
        self.settings.validate_trading_mode()
        self.ib = IB()
        self.ib.connect(
            self.settings.ib_host,
            self.settings.ib_port,
            clientId=self.settings.ib_client_id,
        )
        if not self.ib.isConnected():
            raise RuntimeError("TWS/IB Gateway connection failed.")

    def _account_cash(self) -> float:
        if self.ib is None:
            raise RuntimeError("IBKR broker is not connected.")
        for value in self.ib.accountValues():
            if value.tag == "AvailableFunds" and value.currency == "USD":
                return float(value.value)
        raise RuntimeError("Could not read USD AvailableFunds from IBKR account.")

    def _refresh_positions_and_orders(self) -> None:
        if self.ib is None:
            raise RuntimeError("IBKR broker is not connected.")
        self.positions = {}
        for position in self.ib.positions():
            symbol = getattr(position.contract, "symbol", "").upper()
            if symbol:
                self.positions[symbol] = int(position.position)
        self.open_order_tickers = set()
        for trade in self.ib.openTrades():
            symbol = getattr(trade.contract, "symbol", "").upper()
            if symbol:
                self.open_order_tickers.add(symbol)

    def _market_is_safe_for_close_order(self) -> None:
        now = datetime.now().time()
        if now >= time(15, 55):
            raise RuntimeError("Order cutoff guard triggered after 15:55 local time.")

    def plan_entry_order(self, candidate: CandidateScore, settings: Settings) -> PlannedOrder:
        self.account = BrokerAccount(available_cash=self._account_cash())
        self._refresh_positions_and_orders()
        self._market_is_safe_for_close_order()
        return super().plan_entry_order(candidate, settings)

    def plan_exit_order(self, ticker: str) -> PlannedOrder:
        self._refresh_positions_and_orders()
        self._market_is_safe_for_close_order()
        return super().plan_exit_order(ticker)

    def place_order(self, order: PlannedOrder) -> str:
        if self.ib is None:
            raise RuntimeError("IBKR broker is not connected.")
        from ib_async import MarketOrder, Stock

        contract = Stock(order.ticker, "SMART", "USD")
        qualified = self.ib.qualifyContracts(contract)
        if not qualified:
            raise RuntimeError(f"IBKR could not qualify contract for {order.ticker}.")
        trade = self.ib.placeOrder(contract, MarketOrder(order.action, order.quantity))
        return str(getattr(trade.order, "orderId", "submitted"))
