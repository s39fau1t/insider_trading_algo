from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Iterable

from datetime import date

from .models import (
    CandidateScore,
    CongressTrade,
    EarningsEvent,
    InsiderTrade,
    OpenPosition,
    PlannedOrder,
)


SCHEMA = """
CREATE TABLE IF NOT EXISTS earnings_events (
    ticker TEXT NOT NULL,
    earnings_date TEXT NOT NULL,
    timing TEXT NOT NULL,
    previous_earnings_date TEXT NOT NULL,
    PRIMARY KEY (ticker, earnings_date)
);

CREATE TABLE IF NOT EXISTS insider_trades (
    ticker TEXT NOT NULL,
    issuer_name TEXT NOT NULL,
    owner_name TEXT NOT NULL,
    owner_cik TEXT,
    relationship TEXT NOT NULL,
    transaction_date TEXT NOT NULL,
    filing_date TEXT NOT NULL,
    disclosed_at TEXT NOT NULL,
    code TEXT NOT NULL,
    shares REAL NOT NULL,
    price REAL,
    direct_or_indirect TEXT,
    accession_number TEXT,
    PRIMARY KEY (ticker, owner_name, transaction_date, code, shares, accession_number)
);

CREATE TABLE IF NOT EXISTS congress_trades (
    ticker TEXT NOT NULL,
    representative TEXT NOT NULL,
    transaction_date TEXT NOT NULL,
    disclosure_date TEXT NOT NULL,
    transaction_type TEXT NOT NULL,
    amount_low REAL NOT NULL,
    amount_high REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS candidate_scores (
    scanned_at TEXT NOT NULL,
    ticker TEXT NOT NULL,
    earnings_date TEXT NOT NULL,
    insider_score REAL NOT NULL,
    congress_score REAL NOT NULL,
    liquidity_score REAL NOT NULL,
    total_score REAL NOT NULL,
    reasons TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    created_at TEXT NOT NULL,
    ticker TEXT NOT NULL,
    action TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    order_type TEXT NOT NULL,
    limit_price REAL,
    reason TEXT NOT NULL,
    broker_order_id TEXT
);

CREATE TABLE IF NOT EXISTS positions (
    ticker TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    entry_order_id TEXT NOT NULL,
    exit_order_id TEXT,
    entry_at TEXT NOT NULL,
    exit_at TEXT,
    entry_date TEXT NOT NULL,
    exit_date TEXT NOT NULL,
    status TEXT NOT NULL,
    PRIMARY KEY (ticker, entry_order_id)
);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def save_insider_trades(conn: sqlite3.Connection, trades: Iterable[InsiderTrade]) -> None:
    conn.executemany(
        """
        INSERT OR REPLACE INTO insider_trades (
            ticker, issuer_name, owner_name, owner_cik, relationship,
            transaction_date, filing_date, disclosed_at, code, shares, price,
            direct_or_indirect, accession_number
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                trade.ticker,
                trade.issuer_name,
                trade.owner_name,
                trade.owner_cik,
                trade.relationship,
                trade.transaction_date.isoformat(),
                trade.filing_date.isoformat(),
                trade.disclosed_at.isoformat(),
                trade.code,
                trade.shares,
                trade.price,
                trade.direct_or_indirect,
                trade.accession_number,
            )
            for trade in trades
        ],
    )
    conn.commit()


def save_earnings_events(conn: sqlite3.Connection, events: Iterable[EarningsEvent]) -> None:
    conn.executemany(
        """
        INSERT OR REPLACE INTO earnings_events (
            ticker, earnings_date, timing, previous_earnings_date
        ) VALUES (?, ?, ?, ?)
        """,
        [
            (
                event.ticker,
                event.earnings_date.isoformat(),
                event.timing.value,
                event.previous_earnings_date.isoformat(),
            )
            for event in events
        ],
    )
    conn.commit()


def save_congress_trades(conn: sqlite3.Connection, trades: Iterable[CongressTrade]) -> None:
    conn.executemany(
        """
        INSERT INTO congress_trades (
            ticker, representative, transaction_date, disclosure_date,
            transaction_type, amount_low, amount_high
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                trade.ticker,
                trade.representative,
                trade.transaction_date.isoformat(),
                trade.disclosure_date.isoformat(),
                trade.transaction_type,
                trade.amount_low,
                trade.amount_high,
            )
            for trade in trades
        ],
    )
    conn.commit()


def save_candidate_scores(
    conn: sqlite3.Connection,
    scanned_at: datetime,
    candidates: Iterable[CandidateScore],
) -> None:
    conn.executemany(
        """
        INSERT INTO candidate_scores (
            scanned_at, ticker, earnings_date, insider_score, congress_score,
            liquidity_score, total_score, reasons
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                scanned_at.isoformat(),
                candidate.event.ticker,
                candidate.event.earnings_date.isoformat(),
                candidate.insider_score,
                candidate.congress_score,
                candidate.liquidity_score,
                candidate.total_score,
                "; ".join(candidate.reasons),
            )
            for candidate in candidates
        ],
    )
    conn.commit()


def save_order(
    conn: sqlite3.Connection,
    created_at: datetime,
    order: PlannedOrder,
    broker_order_id: str,
) -> None:
    conn.execute(
        """
        INSERT INTO orders (
            created_at, ticker, action, quantity, order_type, limit_price,
            reason, broker_order_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            created_at.isoformat(),
            order.ticker,
            order.action,
            order.quantity,
            order.order_type,
            order.limit_price,
            order.reason,
            broker_order_id,
        ),
    )
    conn.commit()


def open_quantity_for_ticker(conn: sqlite3.Connection, ticker: str) -> int:
    rows = conn.execute(
        """
        SELECT action, quantity
        FROM orders
        WHERE ticker = ?
        """,
        (ticker.upper(),),
    ).fetchall()
    quantity = 0
    for row in rows:
        action = row["action"].upper()
        if action == "BUY":
            quantity += int(row["quantity"])
        elif action == "SELL":
            quantity -= int(row["quantity"])
    return max(0, quantity)


def save_position_entry(
    conn: sqlite3.Connection,
    candidate: CandidateScore,
    order: PlannedOrder,
    broker_order_id: str,
    entry_at: datetime,
) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO positions (
            ticker, quantity, entry_order_id, exit_order_id, entry_at, exit_at,
            entry_date, exit_date, status
        ) VALUES (?, ?, ?, NULL, ?, NULL, ?, ?, 'open')
        """,
        (
            order.ticker,
            order.quantity,
            broker_order_id,
            entry_at.isoformat(),
            candidate.window.entry_date.isoformat(),
            candidate.window.exit_date.isoformat(),
        ),
    )
    conn.commit()


def mark_position_closed(
    conn: sqlite3.Connection,
    ticker: str,
    exit_order_id: str,
    exit_at: datetime,
) -> None:
    conn.execute(
        """
        UPDATE positions
        SET status = 'closed', exit_order_id = ?, exit_at = ?
        WHERE ticker = ? AND status = 'open'
        """,
        (exit_order_id, exit_at.isoformat(), ticker.upper()),
    )
    conn.commit()


def open_positions(conn: sqlite3.Connection) -> list[OpenPosition]:
    rows = conn.execute(
        """
        SELECT ticker, quantity, entry_order_id, entry_at, entry_date, exit_date, status
        FROM positions
        WHERE status = 'open'
        ORDER BY entry_at ASC
        """
    ).fetchall()
    return [
        OpenPosition(
            ticker=row["ticker"],
            quantity=int(row["quantity"]),
            entry_order_id=row["entry_order_id"],
            entry_at=datetime.fromisoformat(row["entry_at"]),
            entry_date=date.fromisoformat(row["entry_date"]),
            exit_date=date.fromisoformat(row["exit_date"]),
            status=row["status"],
        )
        for row in rows
    ]


def due_open_positions(conn: sqlite3.Connection, as_of: date) -> list[OpenPosition]:
    return [position for position in open_positions(conn) if position.exit_date <= as_of]
