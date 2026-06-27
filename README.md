# ISEM Trader

Python implementation of the **Insider Signal Earnings Momentum Trader** described in the proposal. It evaluates upcoming earnings candidates, scores insider and congressional purchase activity, selects the highest-ranked signal, and can execute the resulting long trade through Interactive Brokers TWS.

This is trading software, not financial advice. Run it in IB paper trading first.

## What It Implements

- Long-only earnings swing strategy.
- One position at a time.
- 50% capital allocation per trade with 50% cash reserve.
- Post-earnings exclusion window, core signal window, late signal window, and final execution window.
- 90-point scoring model from the proposal.
- 4% protective stop based on actual fill price.
- Market-on-close exit on the proposal-defined exit date.
- CSV data provider for controlled testing and staging.
- Optional Yahoo Finance, SEC EDGAR, and Stock Watcher adapters for live data plumbing.
- Interactive Brokers TWS execution adapter.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp config.example.toml config.toml
```

Edit `config.toml`. For SEC access, set a real `sec_user_agent`.

## Run Locally With CSV Data

```bash
isem-trader score --config config.toml --date 2026-06-26
```

To submit orders to IB, set `execution.dry_run = false`, start TWS or IB Gateway, log into paper trading, enable API connections, then run near the close:

```bash
isem-trader run --config config.toml --date 2026-06-26
```

The daily runner is designed to be invoked during the final 15-30 minutes of the U.S. session. It enters a new position only when no active position exists. On the scheduled exit day, run it again near the close and it submits the MOC exit.

## Data Files

The CSV provider expects these columns:

- `earnings.csv`: `ticker,report_date,timing,exchange`
- `prior_earnings.csv`: `ticker,prior_earnings_date`
- `insider_transactions.csv`: `ticker,buyer_id,buyer_name,role,source,transaction_date,shares,price,planned_10b5_1,disclosed_date`
- `prices.csv`: `ticker,price`

Timing values are `BMO`, `INTRADAY`, or `AMC`.

## IB Notes

The default execution path places the entry order, waits for the fill, then submits the stop using the actual average fill price. This is more faithful to the proposal's "4% below entry price" rule than estimating the stop from a pre-trade quote.

The MOC exit is submitted on the scheduled exit date by the daily runner. Future-dated MOC behavior can vary by venue and TWS settings, so the safer production workflow is to run the bot each trading day near the close.
