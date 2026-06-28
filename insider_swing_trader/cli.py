from __future__ import annotations

import argparse
import time as time_module
from datetime import date, datetime, timedelta
from pathlib import Path

from .backtest import run_backtest
from .broker.ibkr import DryRunBroker, IbkrBroker
from .config import Settings
from .db import (
    connect,
    due_open_positions,
    mark_position_closed,
    open_positions,
    open_quantity_for_ticker,
    save_candidate_scores,
    save_congress_trades,
    save_earnings_events,
    save_insider_trades,
    save_order,
    save_position_entry,
)
from .providers.congress import CsvCongressProvider
from .providers.earnings import CsvEarningsProvider, FmpEarningsProvider
from .providers.market import CsvMarketDataProvider, IbkrMarketDataProvider
from .providers.sec import LocalForm4Provider, SecEdgarClient, SecForm4Provider
from .scanner import rank_candidates


def _date(value: str) -> date:
    return date.fromisoformat(value)


def _settings(args: argparse.Namespace) -> Settings:
    env = Settings.from_env()
    return Settings(
        db_path=Path(args.db_path) if getattr(args, "db_path", None) else env.db_path,
        min_score=args.min_score if hasattr(args, "min_score") else env.min_score,
        min_price=env.min_price,
        min_average_volume=env.min_average_volume,
        max_positions=env.max_positions,
        allocation_pct=env.allocation_pct,
        ib_host=getattr(args, "ib_host", env.ib_host),
        ib_port=getattr(args, "ib_port", env.ib_port),
        ib_client_id=getattr(args, "ib_client_id", env.ib_client_id),
        trading_mode=env.trading_mode,
        allow_live_trading=env.allow_live_trading,
        sec_user_agent=env.sec_user_agent,
        fmp_api_key=getattr(args, "fmp_api_key", None) or env.fmp_api_key,
    )


def _market_provider(args: argparse.Namespace, settings: Settings):
    if args.ib_market_data:
        return IbkrMarketDataProvider(settings)
    return CsvMarketDataProvider(Path(args.market_csv) if args.market_csv else None)


def _earnings_provider(args: argparse.Namespace, settings: Settings):
    if args.fmp_earnings:
        if not settings.fmp_api_key:
            raise RuntimeError("Set FMP_API_KEY or pass --fmp-api-key to use --fmp-earnings.")
        return FmpEarningsProvider(settings.fmp_api_key)
    if not args.earnings_csv:
        raise RuntimeError("Provide --earnings-csv or use --fmp-earnings.")
    return CsvEarningsProvider(Path(args.earnings_csv))


def _load_inputs(args: argparse.Namespace, start: date, end: date, settings: Settings):
    earnings = _earnings_provider(args, settings)
    events = list(earnings.events(start, end))
    insider_trades = []
    congress_path = Path(args.congress_csv) if args.congress_csv else None
    congress_trades = list(CsvCongressProvider(congress_path).trades())
    if args.insider_xml_dir:
        insider_trades.extend(LocalForm4Provider(Path(args.insider_xml_dir)).trades())
    if args.sec_live:
        if not events:
            return events, insider_trades, congress_trades, _market_provider(args, settings)
        tickers = sorted({event.ticker for event in events})
        lookback_start = min(event.previous_earnings_date for event in events)
        lookback_end = end
        client = SecEdgarClient(Settings.from_env().sec_user_agent)
        insider_trades.extend(
            SecForm4Provider(client, tickers, lookback_start, lookback_end).trades()
        )
    market = _market_provider(args, settings)
    return events, insider_trades, congress_trades, market


def _print_candidates(candidates) -> None:
    if not candidates:
        print("No qualifying candidates.")
        return
    for index, candidate in enumerate(candidates, start=1):
        reasons = "; ".join(candidate.reasons)
        print(
            f"{index}. {candidate.event.ticker} "
            f"{candidate.event.earnings_date} {candidate.event.timing.value} "
            f"score={candidate.total_score:.3f} "
            f"insider={candidate.insider_score:.3f} "
            f"congress={candidate.congress_score:.3f} "
            f"entry={candidate.window.entry_date} exit={candidate.window.exit_date} "
            f"reasons={reasons}"
        )


def cmd_scan(args: argparse.Namespace) -> int:
    settings = _settings(args)
    start = args.start or date.today()
    end = args.end or start + timedelta(days=7)
    events, insider_trades, congress_trades, market = _load_inputs(args, start, end, settings)
    decision_at = args.decision_at or datetime.now()
    candidates = rank_candidates(
        events,
        insider_trades,
        congress_trades,
        decision_at,
        settings,
        market,
    )
    conn = connect(settings.db_path)
    save_earnings_events(conn, events)
    save_insider_trades(conn, insider_trades)
    save_congress_trades(conn, congress_trades)
    save_candidate_scores(conn, decision_at, candidates)
    _print_candidates(candidates)
    return 0


def cmd_backtest(args: argparse.Namespace) -> int:
    settings = _settings(args)
    events, insider_trades, congress_trades, market = _load_inputs(
        args,
        args.start,
        args.end,
        settings,
    )
    decisions = run_backtest(events, insider_trades, congress_trades, settings, market)
    for decision in decisions:
        if decision.selected is None:
            print(f"{decision.decision_at}: CASH")
        else:
            selected = decision.selected
            print(
                f"{decision.decision_at}: BUY {selected.event.ticker} "
                f"score={selected.total_score:.3f} "
                f"entry={selected.window.entry_date} exit={selected.window.exit_date}"
            )
    return 0


def cmd_paper_trade(args: argparse.Namespace) -> int:
    settings = _settings(args)
    start = args.start or date.today()
    end = args.end or start + timedelta(days=3)
    events, insider_trades, congress_trades, market = _load_inputs(args, start, end, settings)
    decision_at = args.decision_at or datetime.now()
    conn = connect(settings.db_path)
    if args.order_side == "exit" and args.ticker:
        ticker = args.ticker.upper()
        dry_positions = {}
        if args.dry_run:
            dry_positions[ticker] = open_quantity_for_ticker(conn, ticker)
        broker = DryRunBroker(positions=dry_positions) if args.dry_run else IbkrBroker(settings)
        if not args.dry_run:
            broker.connect()
        order = broker.plan_exit_order(ticker)
        order_id = broker.place_order(order)
        created_at = datetime.now()
        save_order(conn, created_at, order, order_id)
        mark_position_closed(conn, order.ticker, order_id, created_at)
        print(
            f"{'DRY RUN ' if args.dry_run else ''}{order.action} {order.quantity} "
            f"{order.ticker} order_type={order.order_type} broker_order_id={order_id}"
        )
        return 0
    candidates = rank_candidates(
        events,
        insider_trades,
        congress_trades,
        decision_at,
        settings,
        market,
    )
    if not candidates:
        print("No qualifying candidate; staying in cash.")
        return 0
    selected = candidates[0]
    dry_positions = {}
    if args.dry_run and args.order_side == "exit":
        quantity = open_quantity_for_ticker(conn, selected.event.ticker)
        dry_positions[selected.event.ticker] = quantity
    broker = DryRunBroker(positions=dry_positions) if args.dry_run else IbkrBroker(settings)
    if not args.dry_run:
        broker.connect()
    if args.order_side == "entry":
        order = broker.plan_entry_order(selected, settings)
    else:
        order = broker.plan_exit_order(selected.event.ticker)
    order_id = broker.place_order(order)
    created_at = datetime.now()
    save_earnings_events(conn, events)
    save_insider_trades(conn, insider_trades)
    save_congress_trades(conn, congress_trades)
    save_candidate_scores(conn, decision_at, candidates)
    save_order(conn, created_at, order, order_id)
    if order.action == "BUY":
        save_position_entry(conn, selected, order, order_id, created_at)
    elif order.action == "SELL":
        mark_position_closed(conn, order.ticker, order_id, created_at)
    print(
        f"{'DRY RUN ' if args.dry_run else ''}{order.action} {order.quantity} "
        f"{order.ticker} order_type={order.order_type} broker_order_id={order_id}"
    )
    return 0


def _broker_for_cycle(args: argparse.Namespace, settings: Settings, conn):
    if not args.dry_run:
        broker = IbkrBroker(settings)
        broker.connect()
        return broker
    positions = {position.ticker: position.quantity for position in open_positions(conn)}
    return DryRunBroker(positions=positions)


def _run_cycle_once(args: argparse.Namespace) -> int:
    settings = _settings(args)
    as_of = args.as_of or datetime.now()
    start = args.start or as_of.date()
    end = args.end or start + timedelta(days=3)
    conn = connect(settings.db_path)
    broker = _broker_for_cycle(args, settings, conn)

    exits = due_open_positions(conn, as_of.date())
    for position in exits:
        order = broker.plan_exit_order(position.ticker)
        order_id = broker.place_order(order)
        closed_at = datetime.now()
        save_order(conn, closed_at, order, order_id)
        mark_position_closed(conn, position.ticker, order_id, closed_at)
        print(
            f"{'DRY RUN ' if args.dry_run else ''}EXIT {position.ticker} "
            f"quantity={order.quantity} broker_order_id={order_id}"
        )

    if open_positions(conn):
        print("Open position remains after exits; no new entry.")
        return 0

    events, insider_trades, congress_trades, market = _load_inputs(args, start, end, settings)
    candidates = [
        candidate
        for candidate in rank_candidates(
            events,
            insider_trades,
            congress_trades,
            as_of,
            settings,
            market,
        )
        if candidate.window.entry_date == as_of.date()
    ]
    save_earnings_events(conn, events)
    save_insider_trades(conn, insider_trades)
    save_congress_trades(conn, congress_trades)
    save_candidate_scores(conn, as_of, candidates)
    if not candidates:
        print("No due entry candidate; staying in cash.")
        return 0
    selected = candidates[0]
    if args.dry_run:
        broker.positions = {position.ticker: position.quantity for position in open_positions(conn)}
    order = broker.plan_entry_order(selected, settings)
    order_id = broker.place_order(order)
    created_at = datetime.now()
    save_order(conn, created_at, order, order_id)
    save_position_entry(conn, selected, order, order_id, created_at)
    print(
        f"{'DRY RUN ' if args.dry_run else ''}ENTRY {order.ticker} "
        f"quantity={order.quantity} score={selected.total_score:.3f} "
        f"exit_date={selected.window.exit_date} broker_order_id={order_id}"
    )
    return 0


def cmd_run_cycle(args: argparse.Namespace) -> int:
    while True:
        code = _run_cycle_once(args)
        if not args.loop:
            return code
        time_module.sleep(args.poll_seconds)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="insider-swing")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_common(subparser: argparse.ArgumentParser) -> None:
        subparser.add_argument("--earnings-csv")
        subparser.add_argument(
            "--fmp-earnings",
            action="store_true",
            help="Fetch earnings calendar from Financial Modeling Prep.",
        )
        subparser.add_argument("--fmp-api-key")
        subparser.add_argument("--insider-xml-dir")
        subparser.add_argument(
            "--sec-live",
            action="store_true",
            help="Fetch recent Form 4/4-A filings from SEC EDGAR for earnings tickers.",
        )
        subparser.add_argument("--market-csv")
        subparser.add_argument(
            "--ib-market-data",
            action="store_true",
            help="Use TWS/IB Gateway for price and volume snapshots instead of --market-csv.",
        )
        subparser.add_argument("--congress-csv")
        subparser.add_argument("--db-path")
        subparser.add_argument("--min-score", type=float, default=Settings.from_env().min_score)
        subparser.add_argument(
            "--decision-at",
            type=lambda value: datetime.fromisoformat(value),
            help="Point-in-time decision timestamp, e.g. 2026-06-28T15:45:00.",
        )

    scan = subparsers.add_parser("scan")
    add_common(scan)
    scan.add_argument("--start", type=_date)
    scan.add_argument("--end", type=_date)
    scan.set_defaults(func=cmd_scan)

    backtest = subparsers.add_parser("backtest")
    add_common(backtest)
    backtest.add_argument("--start", type=_date, required=True)
    backtest.add_argument("--end", type=_date, required=True)
    backtest.set_defaults(func=cmd_backtest)

    paper = subparsers.add_parser("paper-trade")
    add_common(paper)
    paper.add_argument("--start", type=_date)
    paper.add_argument("--end", type=_date)
    paper.add_argument("--dry-run", action="store_true")
    paper.add_argument(
        "--order-side",
        choices=["entry", "exit"],
        default="entry",
        help="Plan an earnings swing entry buy or exit sell.",
    )
    paper.add_argument("--ticker", help="Ticker to close when --order-side exit is used.")
    paper.add_argument("--ib-host", default=Settings.from_env().ib_host)
    paper.add_argument("--ib-port", type=int, default=Settings.from_env().ib_port)
    paper.add_argument("--ib-client-id", type=int, default=Settings.from_env().ib_client_id)
    paper.set_defaults(func=cmd_paper_trade)

    cycle = subparsers.add_parser("run-cycle")
    add_common(cycle)
    cycle.add_argument("--start", type=_date)
    cycle.add_argument("--end", type=_date)
    cycle.add_argument("--dry-run", action="store_true")
    cycle.add_argument("--loop", action="store_true")
    cycle.add_argument("--poll-seconds", type=int, default=900)
    cycle.add_argument(
        "--as-of",
        type=lambda value: datetime.fromisoformat(value),
        help="Override the cycle timestamp for testing or scheduled runs.",
    )
    cycle.add_argument("--ib-host", default=Settings.from_env().ib_host)
    cycle.add_argument("--ib-port", type=int, default=Settings.from_env().ib_port)
    cycle.add_argument("--ib-client-id", type=int, default=Settings.from_env().ib_client_id)
    cycle.set_defaults(func=cmd_run_cycle)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
