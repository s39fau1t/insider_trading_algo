from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    db_path: Path = Path("data/insider_swing.sqlite3")
    min_score: float = 6.0
    min_price: float = 2.0
    min_average_volume: int = 300_000
    max_positions: int = 1
    allocation_pct: float = 0.95
    ib_host: str = "127.0.0.1"
    ib_port: int = 7497
    ib_client_id: int = 77
    trading_mode: str = "paper"
    allow_live_trading: bool = False
    sec_user_agent: str = "insider-swing-trader/0.1 contact@example.com"
    fmp_api_key: str = ""

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            db_path=Path(os.getenv("IST_DB_PATH", "data/insider_swing.sqlite3")),
            min_score=float(os.getenv("IST_MIN_SCORE", "6.0")),
            min_price=float(os.getenv("IST_MIN_PRICE", "2.0")),
            min_average_volume=int(os.getenv("IST_MIN_AVG_VOLUME", "300000")),
            allocation_pct=float(os.getenv("IST_ALLOCATION_PCT", "0.95")),
            ib_host=os.getenv("IB_HOST", "127.0.0.1"),
            ib_port=int(os.getenv("IB_PORT", "7497")),
            ib_client_id=int(os.getenv("IB_CLIENT_ID", "77")),
            trading_mode=os.getenv("TRADING_MODE", "paper").lower(),
            allow_live_trading=os.getenv("ALLOW_LIVE_TRADING", "").upper() == "YES",
            sec_user_agent=os.getenv(
                "SEC_USER_AGENT", "insider-swing-trader/0.1 contact@example.com"
            ),
            fmp_api_key=os.getenv("FMP_API_KEY", ""),
        )

    def validate_trading_mode(self) -> None:
        if self.trading_mode == "live" and not self.allow_live_trading:
            raise RuntimeError(
                "Live trading is blocked. Set TRADING_MODE=live and "
                "ALLOW_LIVE_TRADING=YES only if you intentionally want live orders."
            )
        if self.trading_mode not in {"paper", "live"}:
            raise RuntimeError("TRADING_MODE must be either 'paper' or 'live'.")
