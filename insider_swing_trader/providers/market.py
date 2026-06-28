from __future__ import annotations

import csv
from pathlib import Path

from insider_swing_trader.config import Settings
from insider_swing_trader.models import MarketSnapshot


class CsvMarketDataProvider:
    def __init__(self, csv_path: Path | None):
        self.snapshots: dict[str, MarketSnapshot] = {}
        if csv_path is None or not csv_path.exists():
            return
        with csv_path.open(newline="") as handle:
            for row in csv.DictReader(handle):
                ticker = row["ticker"].strip().upper()
                self.snapshots[ticker] = MarketSnapshot(
                    ticker=ticker,
                    last_price=float(row["last_price"]),
                    average_volume=int(float(row["average_volume"])),
                )

    def snapshot(self, ticker: str) -> MarketSnapshot | None:
        return self.snapshots.get(ticker.upper())


class IbkrMarketDataProvider:
    def __init__(self, settings: Settings, ib=None, stock_factory=None):
        self.settings = settings
        self.ib = ib
        self.stock_factory = stock_factory
        self._owns_connection = ib is None

    def connect(self) -> None:
        if self.ib is not None:
            return
        try:
            from ib_async import IB
        except ImportError as exc:
            raise RuntimeError(
                "Install broker dependencies with: python -m pip install -e '.[broker]'"
            ) from exc
        self.ib = IB()
        self.ib.connect(
            self.settings.ib_host,
            self.settings.ib_port,
            clientId=self.settings.ib_client_id + 100,
        )
        if not self.ib.isConnected():
            raise RuntimeError("TWS/IB Gateway market-data connection failed.")

    def close(self) -> None:
        if self._owns_connection and self.ib is not None and self.ib.isConnected():
            self.ib.disconnect()

    def snapshot(self, ticker: str) -> MarketSnapshot | None:
        self.connect()
        if self.stock_factory is None:
            from ib_async import Stock

            self.stock_factory = Stock
        symbol = ticker.upper()
        contract = self.stock_factory(symbol, "SMART", "USD")
        qualified = self.ib.qualifyContracts(contract)
        if not qualified:
            return None
        contract = qualified[0]
        quote = self.ib.reqMktData(contract, "", False, False)
        self.ib.sleep(2)
        price = quote.marketPrice()
        self.ib.cancelMktData(contract)
        if price is None or price <= 0:
            price = quote.last or quote.close
        bars = self.ib.reqHistoricalData(
            contract,
            endDateTime="",
            durationStr="30 D",
            barSizeSetting="1 day",
            whatToShow="TRADES",
            useRTH=True,
        )
        volumes = [int(bar.volume) for bar in bars if getattr(bar, "volume", 0)]
        average_volume = int(sum(volumes) / len(volumes)) if volumes else 0
        if price is None or price <= 0 or average_volume <= 0:
            return None
        return MarketSnapshot(symbol, float(price), average_volume)
