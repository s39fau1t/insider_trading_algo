import yfinance as yf
from sec_edgar_downloader import Downloader

from datetime import datetime, timedelta, date
from pathlib import Path
import xml.etree.ElementTree as ET

# Initialize the calendars object
start = datetime.now().replace(hour=16)
#TODO                   SHOULD BE 1; 14 for debug purposes
end = start + timedelta(days=14)

calendars = yf.Calendars(start, end)

# Get upcoming earnings (Limit of 100 results)
df = calendars.get_earnings_calendar()

symbols = []

for row in df.itertuples():
    symbol = row.Index
    ticker = yf.Ticker(symbol)
    exchange = ticker.info.get('exchange')
    #nasdaq = NMS, NYSE = NYQ
    if exchange == 'NMS' or exchange == 'NYQ':
        symbols.append(symbol)

dl = Downloader('MyCompanyName', 'my.email@domain.com')

for symbol in symbols:
    ticker = yf.Ticker(symbol)
    earnings_dates = ticker.get_earnings_dates()
    last_earnings = earnings_dates.index[0].date()

    if last_earnings > date.today():
        last_earnings = earnings_dates.index[1].date()

    dl.get('4', symbol, after=last_earnings)

    filings = Path(f'sec-edgar-filings/{symbol}/4')
    if not filings.exists():
        continue

    for folder in filings.iterdir():
        file = folder / "full-submission.txt"
        raw = file.read_text()
        xml_start = raw.find('<XML>') + len('<XML>')
        xml_end = raw.find('</XML>')
        tree = ET.ElementTree(ET.fromstring(raw[xml_start:xml_end].strip()))
        root = tree.getroot()

        # exclude 10b5-1 pre-planned purchases
        pre_planned = int(root.find("aff10b5One").value)
        if pre_planned:
            continue

        # TODO: account for multiple nonDerivativeTransaction s
        
        
        # find whether acquired "a" or disposed "d" TODO: could be multiple, must check all
        """
        a_d = root.find(".//transactionAcquiredDisposedCode/value")

        print(a_d.text)
        """
        # account for direct/indirect ownership??


"""
    <nonDerivativeTable>
        <nonDerivativeTransaction>
            <securityTitle>
                <value>Class B Common Stock</value>
            </securityTitle>
            <transactionDate>
                <value>2026-04-07</value>
                <footnoteId id="F1"/>
            </transactionDate>
            <transactionCoding>
                <transactionFormType>4</transactionFormType>
                <transactionCode>P</transactionCode>
                <equitySwapInvolved>0</equitySwapInvolved>
            </transactionCoding>
            <transactionTimeliness></transactionTimeliness>
            <transactionAmounts>
                <transactionShares>
                    <value>11781.387</value>
                </transactionShares>
                <transactionPricePerShare>
                    <value>42.44</value>
                    <footnoteId id="F2"/>
                </transactionPricePerShare>
                <transactionAcquiredDisposedCode>
                    <value>A</value>
                </transactionAcquiredDisposedCode>
            </transactionAmounts>
            <postTransactionAmounts>
                <sharesOwnedFollowingTransaction>
                    <value>55074.387</value>
                </sharesOwnedFollowingTransaction>
            </postTransactionAmounts>
            <ownershipNature>
                <directOrIndirectOwnership>
                    <value>D</value>
                </directOrIndirectOwnership>
            </ownershipNature>
        </nonDerivativeTransaction>
"""