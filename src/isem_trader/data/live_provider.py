from __future__ import annotations

from datetime import date, timedelta
import re
import xml.etree.ElementTree as ET

from ..calendar_utils import next_weekday
from ..config import DataConfig
from ..models import EarningsEvent, EarningsTiming, InsiderTransaction


class LiveMarketDataProvider:
    """Best-effort live data adapter for the free sources named in the proposal.

    Yahoo and free public disclosure APIs change over time. Keep this adapter behind the
    MarketDataProvider interface so production systems can swap in a licensed or
    internally validated feed without touching the strategy logic.
    """

    def __init__(self, config: DataConfig):
        import requests

        self.config = config
        self.session = requests.Session()
        if config.sec_user_agent:
            self.session.headers.update({"User-Agent": config.sec_user_agent})
        self._ticker_meta: dict[str, dict] | None = None

    def get_earnings_events(self, run_date: date) -> list[EarningsEvent]:
        import yfinance as yf

        events: list[EarningsEvent] = []
        for ticker in self._tickers_on_major_exchanges():
            try:
                calendar = yf.Ticker(ticker).calendar
            except Exception:
                continue
            event = _event_from_yfinance_calendar(ticker, calendar)
            if event and event.report_date in {run_date, next_weekday(run_date)}:
                events.append(event)
        return events

    def get_prior_earnings_date(self, ticker: str, next_earnings_date: date) -> date | None:
        import yfinance as yf

        try:
            earnings = yf.Ticker(ticker).earnings_dates
        except Exception:
            return None
        if earnings is None or len(earnings) == 0:
            return None
        for idx in earnings.index:
            prior = idx.date()
            if prior < next_earnings_date:
                return prior
        return None

    def get_insider_transactions(
        self,
        ticker: str,
        since: date,
        until: date,
    ) -> list[InsiderTransaction]:
        return (
            self._sec_form4_purchases(ticker, since, until)
            + self._congress_purchases(ticker, since, until)
        )

    def get_last_price(self, ticker: str) -> float:
        import yfinance as yf

        fast_info = getattr(yf.Ticker(ticker), "fast_info", {})
        for key in ("last_price", "lastPrice", "regular_market_price"):
            value = fast_info.get(key) if hasattr(fast_info, "get") else None
            if value:
                return float(value)
        hist = yf.Ticker(ticker).history(period="1d")
        if len(hist):
            return float(hist["Close"].iloc[-1])
        return 0.0

    def _tickers_on_major_exchanges(self) -> list[str]:
        meta = self._load_ticker_meta()
        return [
            ticker
            for ticker, info in meta.items()
            if info.get("exchange", "").upper() in {"NYSE", "NASDAQ"}
        ]

    def _load_ticker_meta(self) -> dict[str, dict]:
        if self._ticker_meta is not None:
            return self._ticker_meta
        url = "https://www.sec.gov/files/company_tickers_exchange.json"
        data = self.session.get(url, timeout=30).json()
        fields = data["fields"]
        self._ticker_meta = {
            dict(zip(fields, row))["ticker"].upper(): dict(zip(fields, row))
            for row in data["data"]
        }
        return self._ticker_meta

    def _sec_form4_purchases(
        self,
        ticker: str,
        since: date,
        until: date,
    ) -> list[InsiderTransaction]:
        if not self.config.sec_user_agent:
            return []
        meta = self._load_ticker_meta().get(ticker.upper())
        if not meta:
            return []
        cik = str(meta["cik"]).zfill(10)
        submissions = self.session.get(
            f"https://data.sec.gov/submissions/CIK{cik}.json",
            timeout=30,
        ).json()
        recent = submissions.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        accessions = recent.get("accessionNumber", [])
        documents = recent.get("primaryDocument", [])

        purchases: list[InsiderTransaction] = []
        for form, accession, document in zip(forms, accessions, documents):
            if form != "4":
                continue
            url = (
                "https://www.sec.gov/Archives/edgar/data/"
                f"{int(cik)}/{accession.replace('-', '')}/{document}"
            )
            try:
                xml_text = self.session.get(url, timeout=30).text
                purchases.extend(_parse_form4_xml(ticker, xml_text, since, until))
            except Exception:
                continue
        return purchases

    def _congress_purchases(
        self,
        ticker: str,
        since: date,
        until: date,
    ) -> list[InsiderTransaction]:
        rows = []
        for url in (
            self.config.house_stock_watcher_url,
            self.config.senate_stock_watcher_url,
        ):
            if not url:
                continue
            try:
                payload = self.session.get(url, timeout=30).json()
            except Exception:
                continue
            rows.extend(payload if isinstance(payload, list) else payload.get("data", []))

        purchases: list[InsiderTransaction] = []
        for row in rows:
            symbol = str(row.get("ticker") or row.get("symbol") or "").upper()
            tx_type = str(row.get("type") or row.get("transaction_type") or "").lower()
            if symbol != ticker.upper() or "purchase" not in tx_type:
                continue
            tx_date = _parse_flexible_date(
                row.get("transaction_date") or row.get("transactionDate") or row.get("date")
            )
            if tx_date is None or not since < tx_date <= until:
                continue
            amount = _amount_to_float(row.get("amount") or row.get("value") or 0)
            purchases.append(
                InsiderTransaction(
                    ticker=symbol,
                    buyer_id=str(row.get("representative") or row.get("senator") or row.get("name") or ""),
                    buyer_name=str(row.get("representative") or row.get("senator") or row.get("name") or ""),
                    role="Congress",
                    source="congress",
                    transaction_date=tx_date,
                    shares=1.0,
                    price=amount,
                    planned_10b5_1=False,
                    disclosed_date=_parse_flexible_date(row.get("disclosure_date") or row.get("disclosureDate")),
                )
            )
        return purchases


def _event_from_yfinance_calendar(ticker: str, calendar) -> EarningsEvent | None:
    if calendar is None:
        return None
    raw_date = None
    if isinstance(calendar, dict):
        raw_date = calendar.get("Earnings Date") or calendar.get("EarningsDate")
    else:
        try:
            raw_date = calendar.loc["Earnings Date"][0]
        except Exception:
            raw_date = None
    if raw_date is None:
        return None
    if isinstance(raw_date, (list, tuple)):
        raw_date = raw_date[0]
    report_date = raw_date.date() if hasattr(raw_date, "date") else date.fromisoformat(str(raw_date)[:10])
    timing = EarningsTiming.AMC
    return EarningsEvent(ticker=ticker.upper(), report_date=report_date, timing=timing)


def _parse_form4_xml(
    ticker: str,
    xml_text: str,
    since: date,
    until: date,
) -> list[InsiderTransaction]:
    root = ET.fromstring(xml_text)
    footnote_text = " ".join(node.text or "" for node in root.findall(".//footnote"))
    planned = "10b5-1" in footnote_text.lower() or "10b5 -1" in footnote_text.lower()
    owner = root.find(".//reportingOwner")
    buyer_name = _text(owner, ".//rptOwnerName") if owner is not None else ""
    relation = owner.find(".//reportingOwnerRelationship") if owner is not None else None
    role = _role_from_relationship(relation)

    purchases: list[InsiderTransaction] = []
    for tx in root.findall(".//nonDerivativeTransaction"):
        code = _text(tx, ".//transactionCode")
        acquired = _text(tx, ".//transactionAcquiredDisposedCode/value")
        if code != "P" or acquired != "A":
            continue
        tx_date = _parse_flexible_date(_text(tx, ".//transactionDate/value"))
        if tx_date is None or not since < tx_date <= until:
            continue
        shares = float(_text(tx, ".//transactionShares/value") or 0)
        price = float(_text(tx, ".//transactionPricePerShare/value") or 0)
        tx_footnotes = " ".join(ET.tostring(child, encoding="unicode") for child in tx)
        purchases.append(
            InsiderTransaction(
                ticker=ticker.upper(),
                buyer_id=buyer_name,
                buyer_name=buyer_name,
                role=role,
                source="corporate",
                transaction_date=tx_date,
                shares=shares,
                price=price,
                planned_10b5_1=planned or "10b5-1" in tx_footnotes.lower(),
            )
        )
    return purchases


def _role_from_relationship(relation: ET.Element | None) -> str:
    if relation is None:
        return ""
    roles = []
    if _text(relation, "isOfficer") == "1":
        roles.append(_text(relation, "officerTitle") or "Officer")
    if _text(relation, "isDirector") == "1":
        roles.append("Director")
    if _text(relation, "isTenPercentOwner") == "1":
        roles.append("10% Owner")
    return ", ".join(filter(None, roles))


def _text(node: ET.Element | None, path: str) -> str:
    if node is None:
        return ""
    found = node.find(path)
    return (found.text or "").strip() if found is not None else ""


def _parse_flexible_date(value) -> date | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _amount_to_float(value) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value)
    numbers = [float(match.replace(",", "")) for match in re.findall(r"\d[\d,]*", text)]
    if not numbers:
        return 0.0
    return sum(numbers) / len(numbers)
