import json
from datetime import date

from insider_swing_trader.models import EarningsTiming
from insider_swing_trader.providers.earnings import FmpEarningsProvider


def test_fmp_earnings_provider_pairs_event_with_previous_earnings_date():
    def fetcher(url):
        assert "from=2025-03-27" in url
        return json.dumps(
            [
                {"symbol": "EXMP", "date": "2026-03-31", "time": "amc"},
                {"symbol": "EXMP", "date": "2026-06-30", "time": "amc"},
                {"symbol": "OTHER", "date": "2026-06-30", "time": "bmo"},
            ]
        )

    provider = FmpEarningsProvider("demo", fetcher=fetcher)
    events = list(provider.events(date(2026, 6, 30), date(2026, 6, 30)))

    assert len(events) == 1
    assert events[0].ticker == "EXMP"
    assert events[0].timing == EarningsTiming.AMC
    assert events[0].previous_earnings_date == date(2026, 3, 31)
