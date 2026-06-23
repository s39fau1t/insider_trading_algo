"""
from sec_edgar_downloader import Downloader

# Initialize a downloader instance. Download filings to the current
# working directory. Must declare company name and email address
# to form a user-agent string that complies with the SEC Edgar's
# programmatic downloading fair access policy.
# More info: https://www.sec.gov/os/webmaster-faq#code-support
# Company name and email are used to form a user-agent of the form:
# User-Agent: <Company Name> <Email Address>
dl = Downloader("MyCompanyName", "my.email@domain.com")

# Get all 8-K filings for Apple (ticker: AAPL)
print(dl.get("8-K", "AAPL"))
"""

import yfinance as yf
from datetime import datetime, timedelta

# Initialize the calendars object
start = datetime.now().replace(hour=16)
end = start + timedelta(days=1)

calendars = yf.Calendars(start, end)

# Get upcoming earnings (Limit of 100 results)
df = calendars.get_earnings_calendar()

symbols = []

for row in df.itertuples():
    symbol = row.Index
    ticker = yf.Ticker(symbol)
    exchange = ticker.info.get("exchange")
    #nasdaq = NMS, NYSE = NYQ
    if exchange == "NMS" or exchange == "NYQ":
        symbols.append(symbol)

print(symbols)