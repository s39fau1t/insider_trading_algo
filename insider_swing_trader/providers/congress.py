from __future__ import annotations

import csv
from datetime import date
from pathlib import Path
from typing import Iterable

from insider_swing_trader.models import CongressTrade


def _amount(value: str | None) -> float:
    if not value:
        return 0.0
    cleaned = value.replace("$", "").replace(",", "").strip()
    if not cleaned:
        return 0.0
    return float(cleaned)


class CsvCongressProvider:
    def __init__(self, csv_path: Path | None):
        self.csv_path = csv_path

    def trades(self) -> Iterable[CongressTrade]:
        if self.csv_path is None or not self.csv_path.exists():
            return []
        with self.csv_path.open(newline="") as handle:
            rows = list(csv.DictReader(handle))
        return [
            CongressTrade(
                ticker=row["ticker"].strip().upper(),
                representative=row.get("representative", "").strip(),
                transaction_date=date.fromisoformat(row["transaction_date"]),
                disclosure_date=date.fromisoformat(row["disclosure_date"]),
                transaction_type=row["transaction_type"].strip().lower(),
                amount_low=_amount(row.get("amount_low")),
                amount_high=_amount(row.get("amount_high")),
            )
            for row in rows
        ]

