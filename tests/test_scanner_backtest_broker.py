from datetime import date, datetime

from insider_swing_trader.backtest import run_backtest
from insider_swing_trader.broker.ibkr import DryRunBroker
from insider_swing_trader.config import Settings
from insider_swing_trader.models import EarningsEvent, EarningsTiming, MarketSnapshot
from insider_swing_trader.providers.sec import parse_form4_xml
from insider_swing_trader.scanner import StaticMarketDataProvider, rank_candidates


def test_scan_ranks_candidate_from_fixture():
    settings = Settings(min_score=1.0)
    event = EarningsEvent("EXMP", date(2026, 6, 30), EarningsTiming.AMC, date(2026, 3, 31))
    trades = parse_form4_xml(open("tests/fixtures/form4_purchase.xml").read())
    market = StaticMarketDataProvider({"EXMP": MarketSnapshot("EXMP", 12.0, 2_000_000)})

    candidates = rank_candidates(
        [event],
        trades,
        [],
        datetime(2026, 6, 1, 16, 2),
        settings,
        market,
    )

    assert len(candidates) == 1
    assert candidates[0].event.ticker == "EXMP"
    assert candidates[0].liquidity_score > 0


def test_backtest_has_no_lookahead_before_disclosure():
    settings = Settings(min_score=1.0)
    event = EarningsEvent("EXMP", date(2026, 6, 1), EarningsTiming.AMC, date(2026, 3, 31))
    trades = parse_form4_xml(open("tests/fixtures/form4_purchase.xml").read())

    decisions = run_backtest([event], trades, [], settings)

    assert decisions[0].selected is None


def test_dry_run_broker_plans_quantity_from_cash():
    settings = Settings(min_score=1.0, allocation_pct=0.95)
    event = EarningsEvent("EXMP", date(2026, 6, 30), EarningsTiming.AMC, date(2026, 3, 31))
    trades = parse_form4_xml(open("tests/fixtures/form4_purchase.xml").read())
    market = StaticMarketDataProvider({"EXMP": MarketSnapshot("EXMP", 10.0, 2_000_000)})
    candidate = rank_candidates(
        [event],
        trades,
        [],
        datetime(2026, 6, 1, 16, 2),
        settings,
        market,
    )[0]

    order = DryRunBroker().plan_entry_order(candidate, settings)

    assert order.ticker == "EXMP"
    assert order.action == "BUY"
    assert order.quantity == 950


def test_dry_run_broker_refuses_duplicate_entry():
    settings = Settings(min_score=1.0, allocation_pct=0.95)
    event = EarningsEvent("EXMP", date(2026, 6, 30), EarningsTiming.AMC, date(2026, 3, 31))
    trades = parse_form4_xml(open("tests/fixtures/form4_purchase.xml").read())
    market = StaticMarketDataProvider({"EXMP": MarketSnapshot("EXMP", 10.0, 2_000_000)})
    candidate = rank_candidates(
        [event],
        trades,
        [],
        datetime(2026, 6, 1, 16, 2),
        settings,
        market,
    )[0]

    try:
        DryRunBroker(positions={"EXMP": 100}).plan_entry_order(candidate, settings)
    except RuntimeError as exc:
        assert "already long EXMP" in str(exc)
    else:
        raise AssertionError("duplicate entry was not rejected")


def test_dry_run_broker_plans_exit_and_refuses_missing_position():
    order = DryRunBroker(positions={"EXMP": 100}).plan_exit_order("EXMP")

    assert order.action == "SELL"
    assert order.quantity == 100

    try:
        DryRunBroker().plan_exit_order("EXMP")
    except RuntimeError as exc:
        assert "no long position" in str(exc)
    else:
        raise AssertionError("missing position exit was not rejected")
