from __future__ import annotations

from dataclasses import dataclass
from threading import Event, Thread
import time

from ..config import ExecutionConfig, IbConfig
from .base import FillResult


@dataclass
class _OrderFill:
    status: str = ""
    filled: float = 0.0
    avg_fill_price: float = 0.0


class IbTwsBroker:
    def __init__(self, ib: IbConfig, execution: ExecutionConfig):
        from ibapi.client import EClient
        from ibapi.wrapper import EWrapper

        class App(EWrapper, EClient):
            def __init__(self):
                EClient.__init__(self, self)
                self.next_order_id: int | None = None
                self.next_id_event = Event()
                self.account_values: dict[str, float] = {}
                self.account_event = Event()
                self.positions: dict[str, int] = {}
                self.positions_event = Event()
                self.fills: dict[int, _OrderFill] = {}

            def nextValidId(self, orderId: int):  # noqa: N802
                self.next_order_id = orderId
                self.next_id_event.set()

            def accountSummary(self, reqId, account, tag, value, currency):  # noqa: N802
                try:
                    self.account_values[tag] = float(value)
                except ValueError:
                    return

            def accountSummaryEnd(self, reqId):  # noqa: N802
                self.account_event.set()

            def position(self, account, contract, position, avgCost):  # noqa: N802
                self.positions[contract.symbol.upper()] = int(position)

            def positionEnd(self):  # noqa: N802
                self.positions_event.set()

            def orderStatus(  # noqa: N802
                self,
                orderId,
                status,
                filled,
                remaining,
                avgFillPrice,
                permId,
                parentId,
                lastFillPrice,
                clientId,
                whyHeld,
                mktCapPrice,
            ):
                self.fills[orderId] = _OrderFill(status, filled, avgFillPrice)

        self.ib = ib
        self.execution = execution
        self.app = App()
        self.app.connect(ib.host, ib.port, ib.client_id)
        self.thread = Thread(target=self.app.run, daemon=True)
        self.thread.start()
        if not self.app.next_id_event.wait(10):
            raise TimeoutError("Timed out waiting for TWS next valid order id.")

    def available_funds(self) -> float:
        req_id = int(time.time()) % 1_000_000
        self.app.account_event.clear()
        self.app.reqAccountSummary(req_id, "All", self.execution.account_summary_tag)
        if not self.app.account_event.wait(10):
            raise TimeoutError("Timed out waiting for account summary from TWS.")
        self.app.cancelAccountSummary(req_id)
        return self.app.account_values.get(self.execution.account_summary_tag, 0.0)

    def position_size(self, ticker: str) -> int:
        self.app.positions.clear()
        self.app.positions_event.clear()
        self.app.reqPositions()
        if not self.app.positions_event.wait(10):
            raise TimeoutError("Timed out waiting for positions from TWS.")
        self.app.cancelPositions()
        return self.app.positions.get(ticker.upper(), 0)

    def place_entry_with_stop(
        self,
        ticker: str,
        quantity: int,
        reference_price: float,
        stop_loss_pct: float,
    ) -> FillResult:
        from ibapi.contract import Contract
        from ibapi.order import Order

        contract = _stock_contract(ticker)
        entry_id = self._next_order_id()
        entry = Order()
        entry.action = "BUY"
        entry.totalQuantity = quantity
        entry.orderType = self.execution.entry_order_type.upper()
        entry.transmit = True
        self.app.placeOrder(entry_id, contract, entry)

        fill = self._wait_for_fill(entry_id, quantity)
        avg_price = fill.avg_fill_price or reference_price
        stop_price = round(avg_price * (1 - stop_loss_pct), 2)

        stop_id = self._next_order_id()
        stop = Order()
        stop.action = "SELL"
        stop.totalQuantity = quantity
        stop.orderType = "STP"
        stop.auxPrice = stop_price
        stop.tif = "GTC"
        stop.transmit = True
        self.app.placeOrder(stop_id, contract, stop)

        return FillResult(
            entry_order_id=entry_id,
            stop_order_id=stop_id,
            avg_fill_price=avg_price,
            stop_price=stop_price,
        )

    def submit_moc_exit(self, ticker: str, quantity: int) -> int | None:
        from ibapi.order import Order

        order_id = self._next_order_id()
        exit_order = Order()
        exit_order.action = "SELL"
        exit_order.totalQuantity = quantity
        exit_order.orderType = "MOC"
        exit_order.transmit = True
        self.app.placeOrder(order_id, _stock_contract(ticker), exit_order)
        return order_id

    def cancel_order(self, order_id: int) -> None:
        self.app.cancelOrder(order_id, "")

    def close(self) -> None:
        self.app.disconnect()
        self.thread.join(timeout=2)

    def _next_order_id(self) -> int:
        if self.app.next_order_id is None:
            raise RuntimeError("TWS has not provided a next order id.")
        order_id = self.app.next_order_id
        self.app.next_order_id += 1
        return order_id

    def _wait_for_fill(self, order_id: int, quantity: int) -> _OrderFill:
        deadline = time.time() + 60
        while time.time() < deadline:
            fill = self.app.fills.get(order_id)
            if fill and fill.status == "Filled" and fill.filled >= quantity:
                return fill
            time.sleep(0.5)
        raise TimeoutError(f"Entry order {order_id} did not fully fill within 60 seconds.")


def _stock_contract(ticker: str):
    from ibapi.contract import Contract

    contract = Contract()
    contract.symbol = ticker.upper()
    contract.secType = "STK"
    contract.exchange = "SMART"
    contract.currency = "USD"
    return contract
