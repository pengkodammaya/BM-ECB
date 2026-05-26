"""Test alternative FRED series for external demand + yfinance PMI proxy."""
import httpx
import yfinance as yf
key = open(".fred_key").read().strip()

url = "https://api.stlouisfed.org/fred/series/observations"

# FRED alternatives
fred_series = {
    "INDPRO": "US Industrial Production (monthly index)",
    "TCU": "US Capacity Utilization (% of capacity)",
    "T10Y2Y": "10Y-2Y Treasury Spread (recession signal)",
    "UMCSENT": "U Michigan Consumer Sentiment",
}

for sid, desc in fred_series.items():
    params = {
        "series_id": sid, "api_key": key, "file_type": "json",
        "observation_start": "2015-01-01",
        "sort_order": "desc", "limit": 3,
    }
    resp = httpx.get(url, params=params, timeout=15)
    data = resp.json()
    obs = data.get("observations", [])
    vals = [(o["date"], o["value"]) for o in obs if o["value"] != "."]
    print(f"{sid}: {desc}")
    print(f"  {len(obs)} obs from 2015, last: {vals[0] if vals else 'none'}")
    print()

# yfinance PMI proxy: XLI (Industrial Select Sector SPDR)
print("--- yfinance PMI proxy ---")
for ticker in ["XLI", "DIA", "IYT"]:
    try:
        data = yf.download(ticker, start="2015-01-01", progress=False)
        if data is not None and len(data) > 0:
            close = data[("Close", ticker)] if isinstance(data.columns, pd.MultiIndex) else data["Close"]
            monthly = close.resample("ME").last().dropna()
            print(f"{ticker}: {len(monthly)} monthly obs, last={monthly.index[-1].date()}, value={monthly.values[-1]:.0f}")
    except Exception as e:
        print(f"{ticker}: {e}")
