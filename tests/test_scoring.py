from datetime import date, datetime

from insider_swing_trader.models import CongressTrade, EarningsEvent, EarningsTiming
from insider_swing_trader.providers.sec import parse_form4_xml
from insider_swing_trader.scoring import score_event


def test_score_uses_only_publicly_disclosed_trades():
    event = EarningsEvent("EXMP", date(2026, 6, 30), EarningsTiming.AMC, date(2026, 3, 31))
    xml = open("tests/fixtures/form4_purchase.xml").read()
    trade = parse_form4_xml(xml)[0]

    before_disclosure = score_event(event, [trade], [], datetime(2026, 6, 1, 12, 0))
    after_disclosure = score_event(event, [trade], [], datetime(2026, 6, 1, 16, 2))

    assert before_disclosure.insider_score == 0
    assert after_disclosure.insider_score > 0


def test_score_penalizes_sales_and_boosts_congress_purchase():
    event = EarningsEvent("EXMP", date(2026, 6, 30), EarningsTiming.AMC, date(2026, 3, 31))
    trades = parse_form4_xml(open("tests/fixtures/form4_sale_and_missing_price.xml").read())
    congress = [
        CongressTrade(
            ticker="EXMP",
            representative="Rep Example",
            transaction_date=date(2026, 6, 15),
            disclosure_date=date(2026, 6, 20),
            transaction_type="Purchase",
            amount_low=15001,
            amount_high=50000,
        )
    ]

    candidate = score_event(event, trades, congress, datetime(2026, 6, 21, 10, 0))

    assert candidate.insider_score < 1.5
    assert candidate.congress_score > 0
    assert "congressional purchase disclosure booster" in candidate.reasons

