import yfinance as yf

indicators = {
    "^KLSE": "KLCI - Malaysian stock index",
    "EWM": "iShares MSCI Malaysia ETF",
    "^STI": "Straits Times Index (Singapore)",
    "DBC": "Commodity ETF",
    "GSG": "S&P GSCI Commodity ETF",
}

for sym, name in indicators.items():
    try:
        t = yf.download(sym, start="2024-01-01", progress=False)
        if len(t) > 0:
            last_close = t["Close"].iloc[-1]
            if hasattr(last_close, 'iloc'):
                last_close = last_close.iloc[0]
            print(f"{sym}: {len(t)} rows, last={t.index[-1].date()}, close={last_close:.2f} - {name}")
        else:
            print(f"{sym}: EMPTY - {name}")
    except Exception as e:
        print(f"{sym}: FAILED - {e}")
