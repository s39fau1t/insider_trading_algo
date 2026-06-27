from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import date
import sys

from .broker import Broker, DryRunBroker, IbTwsBroker
from .config import AppConfig, load_config
from .data import CsvMarketDataProvider, LiveMarketDataProvider, MarketDataProvider
from .scoring import rank_candidates
from .selector import score_daily_candidates, select_trade
from .state import ActivePosition, StateStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="isem-trader")
    subparsers = parser.add_subparsers(dest="command", required=True)
    _add_common_args(subparsers.add_parser("score", help="Score today's eligible earnings candidates"))
    _add_common_args(subparsers.add_parser("run", help="Run the daily trading workflow"))
    args = parser.parse_args(argv)

    config = load_config(args.config)
    run_date = date.fromisoformat(args.date)
    provider = _provider(config)

    if args.command == "score":
        return _score(provider, config, run_date)
    if args.command == "run":
        return _run(provider, config, run_date)
    return 2


def _score(provider: MarketDataProvider, config: AppConfig, run_date: date) -> int:
    scores = score_daily_candidates(provider, run_date, config.strategy)
    ranked = rank_candidates(scores, config.strategy.min_score)
    if not scores:
        print("No eligible earnings candidates for the entry window.")
        return 0

    for candidate in sorted(scores, key=lambda item: item.score, reverse=True):
        marker = "ELIGIBLE" if candidate in ranked else "below threshold"
        print(
            f"{candidate.event.ticker}: score={candidate.score} ({marker}), "
            f"dollars=${candidate.total_purchase_dollars:,.0f}, "
            f"buyers={len({tx.buyer_id for tx in candidate.transactions})}, "
            f"timing={candidate.breakdown.timing_quality}, "
            f"velocity={candidate.breakdown.velocity}"
        )
    return 0


def _run(provider: MarketDataProvider, config: AppConfig, run_date: date) -> int:
    store = StateStore(config.state.path)
    broker = _broker(config)
    try:
        active = store.load()
        if active is not None:
            return _manage_active_position(active, store, broker, run_date)

        available = broker.available_funds()
        selected = select_trade(provider, run_date, available, config.strategy)
        if selected is None:
            print("No qualifying trade. Holding cash.")
            return 0

        if broker.position_size(selected.candidate.event.ticker) != 0:
            print(f"Existing {selected.candidate.event.ticker} position found. No new entry.")
            return 0

        result = broker.place_entry_with_stop(
            selected.candidate.event.ticker,
            selected.quantity,
            selected.reference_price,
            config.strategy.stop_loss_pct,
        )
        active = ActivePosition(
            ticker=selected.candidate.event.ticker,
            quantity=selected.quantity,
            entry_date=selected.entry_date,
            exit_date=selected.exit_date,
            avg_fill_price=result.avg_fill_price,
            stop_price=result.stop_price,
            entry_order_id=result.entry_order_id,
            stop_order_id=result.stop_order_id,
        )
        store.save(active)
        print(
            f"Entered {active.quantity} {active.ticker} at ~${active.avg_fill_price:.2f}; "
            f"stop=${active.stop_price:.2f}; scheduled exit={active.exit_date.isoformat()}."
        )
        return 0
    finally:
        broker.close()


def _manage_active_position(
    active: ActivePosition,
    store: StateStore,
    broker: Broker,
    run_date: date,
) -> int:
    live_qty = broker.position_size(active.ticker)
    if live_qty == 0 and active.status != "exit_submitted":
        store.clear()
        print(f"No live {active.ticker} position found. Cleared local state.")
        return 0

    if run_date < active.exit_date:
        print(
            f"Holding {active.quantity} {active.ticker}. "
            f"Scheduled exit is {active.exit_date.isoformat()}."
        )
        return 0

    if active.status == "exit_submitted":
        if live_qty == 0:
            store.clear()
            print(f"{active.ticker} exit appears complete. Cleared local state.")
        else:
            print(f"{active.ticker} exit was already submitted; live quantity is {live_qty}.")
        return 0

    if active.stop_order_id is not None:
        broker.cancel_order(active.stop_order_id)
    exit_order_id = broker.submit_moc_exit(active.ticker, active.quantity)
    store.save(replace(active, exit_order_id=exit_order_id, status="exit_submitted"))
    print(f"Submitted MOC exit for {active.quantity} {active.ticker}.")
    return 0


def _provider(config: AppConfig) -> MarketDataProvider:
    if config.data.provider.lower() == "csv":
        return CsvMarketDataProvider(config.data)
    if config.data.provider.lower() == "live":
        return LiveMarketDataProvider(config.data)
    raise ValueError(f"Unknown data provider: {config.data.provider}")


def _broker(config: AppConfig) -> Broker:
    if config.execution.dry_run:
        return DryRunBroker()
    return IbTwsBroker(config.ib, config.execution)


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", default="config.toml")
    parser.add_argument("--date", default=date.today().isoformat())


if __name__ == "__main__":
    sys.exit(main())
