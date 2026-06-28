from __future__ import annotations

import json
import urllib.request
from datetime import date, datetime, time
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET

from insider_swing_trader.models import InsiderTrade


def _text(parent: ET.Element, path: str, default: str = "") -> str:
    node = parent.find(path)
    if node is None or node.text is None:
        return default
    return node.text.strip()


def _float_text(parent: ET.Element, path: str) -> float | None:
    value = _text(parent, path)
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def parse_form4_xml(
    xml_text: str,
    ticker_hint: str | None = None,
    filing_date_override: date | None = None,
    accession_number: str | None = None,
) -> list[InsiderTrade]:
    root = ET.fromstring(xml_text)
    issuer = root.find("issuer")
    if issuer is None:
        return []
    ticker = (_text(issuer, "issuerTradingSymbol") or ticker_hint or "").upper()
    issuer_name = _text(issuer, "issuerName")
    period = _text(root, "periodOfReport")
    filing_date = filing_date_override or (date.fromisoformat(period) if period else date.today())
    owner = root.find("reportingOwner")
    owner_name = ""
    owner_cik = None
    relationship_parts: list[str] = []
    if owner is not None:
        owner_name = _text(owner, "reportingOwnerId/rptOwnerName")
        owner_cik = _text(owner, "reportingOwnerId/rptOwnerCik") or None
        rel = owner.find("reportingOwnerRelationship")
        if rel is not None:
            if _text(rel, "isDirector") == "1":
                relationship_parts.append("director")
            if _text(rel, "isOfficer") == "1":
                title = _text(rel, "officerTitle")
                relationship_parts.append(f"officer:{title}" if title else "officer")
            if _text(rel, "isTenPercentOwner") == "1":
                relationship_parts.append("10pct")
            if _text(rel, "isOther") == "1":
                relationship_parts.append("other")
    relationship = ",".join(relationship_parts) or "unknown"
    accession = accession_number or _text(root, "documentSchemaVersion") or None
    disclosed_at = datetime.combine(filing_date, time(16, 1))
    trades: list[InsiderTrade] = []
    table = root.find("nonDerivativeTable")
    if table is None:
        return trades
    for transaction in table.findall("nonDerivativeTransaction"):
        code = _text(transaction, "transactionCoding/transactionCode").upper()
        tx_date_text = _text(transaction, "transactionDate/value")
        shares = _float_text(transaction, "transactionAmounts/transactionShares/value")
        price = _float_text(transaction, "transactionAmounts/transactionPricePerShare/value")
        if not ticker or not tx_date_text or shares is None:
            continue
        trades.append(
            InsiderTrade(
                ticker=ticker,
                issuer_name=issuer_name,
                owner_name=owner_name,
                owner_cik=owner_cik,
                relationship=relationship,
                transaction_date=date.fromisoformat(tx_date_text),
                filing_date=filing_date,
                disclosed_at=disclosed_at,
                code=code,
                shares=shares,
                price=price,
                direct_or_indirect=_text(
                    transaction,
                    "ownershipNature/directOrIndirectOwnership/value",
                )
                or None,
                accession_number=accession,
            )
        )
    return trades


class LocalForm4Provider:
    def __init__(self, xml_dir: Path | None):
        self.xml_dir = xml_dir

    def trades(self) -> Iterable[InsiderTrade]:
        if self.xml_dir is None or not self.xml_dir.exists():
            return []
        trades: list[InsiderTrade] = []
        for path in sorted(self.xml_dir.glob("*.xml")):
            trades.extend(parse_form4_xml(path.read_text()))
        return trades


class SecEdgarClient:
    """Small SEC EDGAR client for live Form 4 ingestion.

    It intentionally exposes primitives instead of hiding point-in-time choices in
    the downloader. The scanner should still filter on `disclosed_at`.
    """

    def __init__(self, user_agent: str):
        self.user_agent = user_agent

    def _get_json(self, url: str) -> dict:
        request = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))

    def _get_text(self, url: str) -> str:
        request = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read().decode("utf-8", errors="replace")

    def company_tickers(self) -> dict[str, str]:
        data = self._get_json("https://www.sec.gov/files/company_tickers.json")
        return {
            item["ticker"].upper(): str(item["cik_str"]).zfill(10)
            for item in data.values()
        }

    def submissions(self, cik: str) -> dict:
        return self._get_json(f"https://data.sec.gov/submissions/CIK{cik}.json")

    def filing_document(self, cik: str, accession_number: str, primary_document: str) -> str:
        cik_int = str(int(cik))
        accession_path = accession_number.replace("-", "")
        url = (
            "https://www.sec.gov/Archives/edgar/data/"
            f"{cik_int}/{accession_path}/{primary_document}"
        )
        return self._get_text(url)


class SecForm4Provider:
    def __init__(
        self,
        client: SecEdgarClient,
        tickers: Iterable[str],
        lookback_start: date,
        lookback_end: date,
    ):
        self.client = client
        self.tickers = [ticker.upper() for ticker in tickers]
        self.lookback_start = lookback_start
        self.lookback_end = lookback_end

    def trades(self) -> Iterable[InsiderTrade]:
        cik_by_ticker = self.client.company_tickers()
        trades: list[InsiderTrade] = []
        for ticker in self.tickers:
            cik = cik_by_ticker.get(ticker)
            if cik is None:
                continue
            submissions = self.client.submissions(cik)
            recent = submissions.get("filings", {}).get("recent", {})
            forms = recent.get("form", [])
            accession_numbers = recent.get("accessionNumber", [])
            filing_dates = recent.get("filingDate", [])
            primary_documents = recent.get("primaryDocument", [])
            rows = zip(forms, accession_numbers, filing_dates, primary_documents)
            for form, accession, filing_date_text, primary_document in rows:
                if form not in {"4", "4/A"}:
                    continue
                filing_date = date.fromisoformat(filing_date_text)
                if not self.lookback_start <= filing_date <= self.lookback_end:
                    continue
                xml = self.client.filing_document(cik, accession, primary_document)
                trades.extend(
                    parse_form4_xml(
                        xml,
                        ticker_hint=ticker,
                        filing_date_override=filing_date,
                        accession_number=accession,
                    )
                )
        return trades
