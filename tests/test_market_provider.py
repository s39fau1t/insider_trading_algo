from insider_swing_trader.config import Settings
from insider_swing_trader.providers.market import IbkrMarketDataProvider


class FakeQuote:
    last = 10.0
    close = 9.5

    def marketPrice(self):
        return 10.25


class FakeBar:
    def __init__(self, volume):
        self.volume = volume


class FakeIB:
    def __init__(self):
        self.cancelled = False

    def isConnected(self):
        return True

    def qualifyContracts(self, contract):
        return [contract]

    def reqMktData(self, contract, generic_tick_list, snapshot, regulatory_snapshot):
        return FakeQuote()

    def sleep(self, seconds):
        return None

    def cancelMktData(self, contract):
        self.cancelled = True

    def reqHistoricalData(
        self,
        contract,
        endDateTime,
        durationStr,
        barSizeSetting,
        whatToShow,
        useRTH,
    ):
        return [FakeBar(1_000_000), FakeBar(2_000_000)]


def fake_stock(symbol, exchange, currency):
    return {"symbol": symbol, "exchange": exchange, "currency": currency}


def test_ibkr_market_data_provider_builds_snapshot_from_quote_and_history():
    fake_ib = FakeIB()
    provider = IbkrMarketDataProvider(Settings(), ib=fake_ib, stock_factory=fake_stock)

    snapshot = provider.snapshot("exmp")

    assert snapshot.ticker == "EXMP"
    assert snapshot.last_price == 10.25
    assert snapshot.average_volume == 1_500_000
    assert fake_ib.cancelled is True
