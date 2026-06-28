from datetime import date

from insider_swing_trader.providers.sec import SecForm4Provider


class FakeSecClient:
    def company_tickers(self):
        return {"EXMP": "0000123456"}

    def submissions(self, cik):
        assert cik == "0000123456"
        return {
            "filings": {
                "recent": {
                    "form": ["10-Q", "4", "4/A"],
                    "accessionNumber": [
                        "0000000000-26-000001",
                        "0001111111-26-000123",
                        "0001111111-26-000124",
                    ],
                    "filingDate": ["2026-05-01", "2026-06-03", "2026-08-01"],
                    "primaryDocument": ["q.htm", "form4.xml", "form4a.xml"],
                }
            }
        }

    def filing_document(self, cik, accession_number, primary_document):
        assert accession_number == "0001111111-26-000123"
        assert primary_document == "form4.xml"
        return open("tests/fixtures/form4_purchase.xml").read()


def test_sec_form4_provider_filters_recent_form4_filings_and_uses_metadata():
    provider = SecForm4Provider(
        FakeSecClient(),
        ["EXMP"],
        lookback_start=date(2026, 6, 1),
        lookback_end=date(2026, 6, 30),
    )

    trades = list(provider.trades())

    assert len(trades) == 1
    assert trades[0].filing_date == date(2026, 6, 3)
    assert trades[0].accession_number == "0001111111-26-000123"
