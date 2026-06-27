from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
import json
from pathlib import Path


@dataclass(frozen=True)
class ActivePosition:
    ticker: str
    quantity: int
    entry_date: date
    exit_date: date
    avg_fill_price: float
    stop_price: float
    entry_order_id: int | None = None
    stop_order_id: int | None = None
    exit_order_id: int | None = None
    status: str = "open"


class StateStore:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> ActivePosition | None:
        if not self.path.exists():
            return None
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if not data:
            return None
        return ActivePosition(
            ticker=data["ticker"],
            quantity=int(data["quantity"]),
            entry_date=date.fromisoformat(data["entry_date"]),
            exit_date=date.fromisoformat(data["exit_date"]),
            avg_fill_price=float(data["avg_fill_price"]),
            stop_price=float(data["stop_price"]),
            entry_order_id=data.get("entry_order_id"),
            stop_order_id=data.get("stop_order_id"),
            exit_order_id=data.get("exit_order_id"),
            status=data.get("status", "open"),
        )

    def save(self, active: ActivePosition) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = asdict(active)
        data["entry_date"] = active.entry_date.isoformat()
        data["exit_date"] = active.exit_date.isoformat()
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def clear(self) -> None:
        if self.path.exists():
            self.path.unlink()
