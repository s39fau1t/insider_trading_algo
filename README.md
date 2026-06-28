# Insider-Buying Earnings Swing Trader

Research and paper-trading system that ranks upcoming earnings events using public insider-buying disclosures, then optionally routes a single top candidate through Interactive Brokers TWS / IB Gateway paper trading.

This project is not financial advice and does not promise profit. The default configuration is conservative: scan and dry-run first, paper trading next, and live trading blocked unless multiple explicit flags are set.

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
pytest
```

Run a scan from CSV inputs:

```bash
insider-swing scan \
  --earnings-csv examples/earnings.csv \
  --insider-xml-dir examples/form4 \
  --market-csv examples/market.csv \
  --congress-csv examples/congress.csv
```

Or fetch Form 4 filings directly from SEC EDGAR for the tickers in the earnings file:

```bash
SEC_USER_AGENT="your-name your-email@example.com" insider-swing scan \
  --earnings-csv examples/earnings.csv \
  --market-csv examples/market.csv \
  --sec-live
```

Use Financial Modeling Prep for the earnings calendar instead of a CSV:

```bash
FMP_API_KEY="your-fmp-key" insider-swing scan \
  --fmp-earnings \
  --market-csv examples/market.csv \
  --sec-live
```

Run a dry paper-trade decision:

```bash
insider-swing paper-trade \
  --earnings-csv examples/earnings.csv \
  --insider-xml-dir examples/form4 \
  --market-csv examples/market.csv \
  --dry-run
```

Close a dry-run position recorded in the local SQLite order ledger:

```bash
insider-swing paper-trade \
  --earnings-csv examples/earnings.csv \
  --market-csv examples/market.csv \
  --order-side exit \
  --ticker EXMP \
  --dry-run
```

Connect to Interactive Brokers paper trading only after TWS or IB Gateway is running and API access is enabled:

```bash
python -m pip install -e ".[broker]"
insider-swing paper-trade \
  --earnings-csv examples/earnings.csv \
  --insider-xml-dir examples/form4 \
  --market-csv examples/market.csv \
  --ib-host 127.0.0.1 \
  --ib-port 7497
```

When TWS market data is available, use broker snapshots instead of a market CSV:

```bash
insider-swing scan \
  --earnings-csv examples/earnings.csv \
  --sec-live \
  --ib-market-data
```

Run one full automation cycle. The cycle first closes due positions, then opens the best due entry candidate for the current trading day if no position remains open:

```bash
insider-swing run-cycle \
  --earnings-csv examples/earnings.csv \
  --insider-xml-dir examples/form4 \
  --market-csv examples/market.csv \
  --congress-csv examples/congress.csv \
  --dry-run
```

Run continuously every 15 minutes:

```bash
insider-swing run-cycle \
  --fmp-earnings \
  --sec-live \
  --ib-market-data \
  --dry-run \
  --loop \
  --poll-seconds 900
```

## Data Inputs

`--earnings-csv` columns:

- `ticker`
- `earnings_date` in `YYYY-MM-DD`
- `timing`: `BMO`, `AMC`, `DURING`, or `UNKNOWN`
- `previous_earnings_date` in `YYYY-MM-DD`

`--fmp-earnings` uses the `FMP_API_KEY` environment variable or `--fmp-api-key`, then infers `previous_earnings_date` from the fetched historical earnings calendar.

`--congress-csv` columns:

- `ticker`
- `transaction_date`
- `disclosure_date`
- `transaction_type`: text containing `purchase` or `sale`
- `amount_low`
- `amount_high`
- `representative`

`--market-csv` columns:

- `ticker`
- `last_price`
- `average_volume`

`--insider-xml-dir` should contain SEC Form 4 XML documents. The parser uses open-market purchases (`P`) as positive signals and sales (`S`) as negative signals. For live EDGAR fetching, pass `--sec-live` and set `SEC_USER_AGENT` to an identifying contact string.

## Safety Defaults

- Unknown earnings timing is skipped.
- Only filings disclosed before the decision timestamp are scored.
- Candidates without price and volume data are skipped.
- Entry orders are rejected if a long position or open order already exists.
- Exit orders are rejected if no long position exists.
- `run-cycle` stores open positions with planned exit dates and closes them before considering a new entry.
- Paper trading is the default execution mode.
- Live trading requires `TRADING_MODE=live` and `ALLOW_LIVE_TRADING=YES`.
- If no candidate passes score, price, and liquidity checks, the runner stays in cash.
