import yfinance as yf
from sec_edgar_downloader import Downloader

from datetime import datetime, timedelta, date

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

dl = Downloader("MyCompanyName", "my.email@domain.com")

for symbol in symbols:
    ticker = yf.Ticker(symbol)
    earnings_dates = ticker.get_earnings_dates()
    last_earnings = earnings_dates.index[0].date()

    if last_earnings > date.today():
        last_earnings = earnings_dates.index[1].date()

    dl.get("4", symbol, after=last_earnings)