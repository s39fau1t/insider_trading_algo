from datetime import date

from insider_swing_trader.providers.sec import parse_form4_xml


def test_parse_form4_purchase_fixture():
    xml = open("tests/fixtures/form4_purchase.xml").read()
    trades = parse_form4_xml(xml)

    assert len(trades) == 1
    trade = trades[0]
    assert trade.ticker == "EXMP"
    assert trade.owner_name == "Jane CEO"
    assert trade.code == "P"
    assert trade.transaction_date == date(2026, 5, 29)
    assert trade.dollar_value == 105000
    assert "officer:CEO" in trade.relationship


def test_parse_form4_sale_and_missing_price():
    xml = open("tests/fixtures/form4_sale_and_missing_price.xml").read()
    trades = parse_form4_xml(xml)

    assert [trade.code for trade in trades] == ["S", "P"]
    assert trades[1].price is None
    assert trades[1].dollar_value == 0


def test_parse_form4_uses_filing_date_override_for_disclosure():
    xml = open("tests/fixtures/form4_purchase.xml").read()
    trades = parse_form4_xml(
        xml,
        filing_date_override=date(2026, 6, 3),
        accession_number="0001111111-26-000123",
    )

    assert trades[0].filing_date == date(2026, 6, 3)
    assert trades[0].disclosed_at.date() == date(2026, 6, 3)
    assert trades[0].accession_number == "0001111111-26-000123"

