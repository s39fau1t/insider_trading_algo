from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo
import tomllib


@dataclass(frozen=True)
class StrategyConfig:
    min_score: int = 50
    capital_fraction: float = 0.50
    cash_reserve_fraction: float = 0.50
    stop_loss_pct: float = 0.04
    post_earnings_exclusion_days: int = 14
    late_window_days: int = 28
    final_no_signal_days: int = 3
    congress_recent_disclosure_days: int = 7
    min_purchase_dollars: float = 0.0
    allowed_exchanges: tuple[str, ...] = ("NYSE", "NASDAQ")


@dataclass(frozen=True)
class ExecutionConfig:
    dry_run: bool = True
    entry_start_time: str = "15:30"
    entry_end_time: str = "15:59"
    timezone: str = "America/New_York"
    entry_order_type: str = "MKT"
    account_summary_tag: str = "AvailableFunds"

    @property
    def zoneinfo(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)


@dataclass(frozen=True)
class IbConfig:
    host: str = "127.0.0.1"
    port: int = 7497
    client_id: int = 17
    account: str = ""
    readonly: bool = False


@dataclass(frozen=True)
class StateConfig:
    path: Path = Path("work/isem_state.json")


@dataclass(frozen=True)
class DataConfig:
    provider: str = "csv"
    earnings_csv: Path = Path("examples/earnings.csv")
    prior_earnings_csv: Path = Path("examples/prior_earnings.csv")
    insider_csv: Path = Path("examples/insider_transactions.csv")
    price_csv: Path = Path("examples/prices.csv")
    sec_user_agent: str = ""
    house_stock_watcher_url: str = ""
    senate_stock_watcher_url: str = ""


@dataclass(frozen=True)
class AppConfig:
    strategy: StrategyConfig
    execution: ExecutionConfig
    ib: IbConfig
    state: StateConfig
    data: DataConfig


def load_config(path: str | Path) -> AppConfig:
    path = Path(path)
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    base = path.parent

    def section(name: str) -> dict[str, Any]:
        return dict(raw.get(name, {}))

    strategy = section("strategy")
    if "allowed_exchanges" in strategy:
        strategy["allowed_exchanges"] = tuple(strategy["allowed_exchanges"])

    state = section("state")
    if "path" in state:
        state["path"] = _resolve(base, state["path"])

    data = section("data")
    for key in ("earnings_csv", "prior_earnings_csv", "insider_csv", "price_csv"):
        if key in data:
            data[key] = _resolve(base, data[key])

    return AppConfig(
        strategy=StrategyConfig(**strategy),
        execution=ExecutionConfig(**section("execution")),
        ib=IbConfig(**section("ib")),
        state=StateConfig(**state),
        data=DataConfig(**data),
    )


def _resolve(base: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else base / path
