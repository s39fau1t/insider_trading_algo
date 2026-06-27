from datetime import date

from isem_trader.config import DataConfig, StrategyConfig
from isem_trader.data.csv_provider import CsvMarketDataProvider
from isem_trader.selector import select_trade


def test_csv_provider_selects_top_trade_from_examples():
    provider = CsvMarketDataProvider(DataConfig())
    selected = select_trade(
        provider,
        run_date=date(2026, 6, 26),
        available_capital=100_000,
        config=StrategyConfig(),
    )

    assert selected is not None
    assert selected.candidate.event.ticker == "ACME"
    assert selected.quantity == 2040
    assert selected.exit_date == date(2026, 6, 29)
