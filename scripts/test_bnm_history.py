"""Quick test of BNM historical data fetcher."""
import sys; sys.path.insert(0,"src")
from nowcasting_toolbox.data.sources.bnm import fetch_interest_rate_history, fetch_exchange_rate_history

print("Fetching interest rate history...")
ir = fetch_interest_rate_history(start_year=2020, verbose=True)
print(f"  Rows: {len(ir)}")
print(f"  Range: {ir.date.min().date()} to {ir.date.max().date()}")
print(f"  Last 3:\n{ir.tail(3).to_string()}")

print("\nFetching USD/MYR exchange rate history...")
fx = fetch_exchange_rate_history(start_year=2020, verbose=True)
print(f"  Rows: {len(fx)}")
print(f"  Range: {fx.date.min().date()} to {fx.date.max().date()}")
print(f"  Last 3:\n{fx.tail(3).to_string()}")
