"""
Task 02 — Live Market Data Fetch

Fetches live market prices for BTC, NIFTY50, and GOLD, and displays them in a clean table.
"""

import sys
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
import requests
import yfinance as yf
from tabulate import tabulate

logging.basicConfig(
    format="%(levelname)s: %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)

IST = ZoneInfo("Asia/Kolkata")

TROY_OZ_TO_GRAMS = 31.1035  
GOLD_TICKER = "GC=F"
USDINR_TICKER = "USDINR=X"
COINGECKO_API_URL = "https://api.coingecko.com/api/v3/simple/price"

# ── Individual asset fetchers

def fetch_btc_usd() -> dict:
    """Fetch BTC price in USD from CoinGecko (no API key required)."""
    params = {"ids": "bitcoin", "vs_currencies": "usd"}

    try:
        response = requests.get(COINGECKO_API_URL, params=params, timeout=10)
        response.raise_for_status()
        price = response.json()["bitcoin"]["usd"]
        return {"asset": "BTC", "price": price, "currency": "USD"}
    except Exception as e:
        log.error("Failed to fetch BTC: %s", e)
        return {"asset": "BTC", "price": "ERR", "currency": "-", "error": str(e)}


def get_yfinance_last_price(ticker: str) -> float:
    """Fetch the latest price for a ticker via yfinance."""
    data = yf.Ticker(ticker)
    price = data.fast_info.get("last_price") or data.fast_info.get("regularMarketPrice")

    if price is None:
        hist = data.history(period="1d")
        if hist.empty:
            raise ValueError("No price data returned")
        price = float(hist["Close"].iloc[-1])

    return float(price)


def fetch_usd_to_inr() -> float:
    """Fetch live USD → INR exchange rate via yfinance."""
    return get_yfinance_last_price(USDINR_TICKER)


def fetch_gold_inr_per_gram() -> dict:
    """
    Fetch gold price in INR per gram.
    Conversion pipeline: GC=F (USD/oz) → live USD/INR rate → INR/oz → INR/g
    """
    try:
        usd_per_oz = get_yfinance_last_price(GOLD_TICKER)
        usd_to_inr = fetch_usd_to_inr()
        inr_per_gram = (usd_per_oz * usd_to_inr) / TROY_OZ_TO_GRAMS
        return {"asset": "GOLD", "price": round(inr_per_gram, 2), "currency": "INR/g"}
    except Exception as e:
        log.error("Failed to fetch GOLD in INR/g: %s", e)
        return {"asset": "GOLD", "price": "ERR", "currency": "-", "error": str(e)}


def fetch_yfinance_asset(ticker: str, display_name: str, currency: str) -> dict:
    """Generic yfinance fetcher — works for any ticker (index, stock, commodity)."""
    try:
        price = get_yfinance_last_price(ticker)
        return {"asset": display_name, "price": round(price, 2), "currency": currency}
    except Exception as e:
        log.error("Failed to fetch %s (%s): %s", display_name, ticker, e)
        return {"asset": display_name, "price": "ERR", "currency": "-", "error": str(e)}



def format_price(value: object) -> str:
    """Format numeric prices with commas; pass through error strings as-is."""
    if isinstance(value, (int, float)):
        return f"{value:,.2f}"
    return str(value)


def render_table(rows: list[dict], fetch_time: str) -> None:
    """Print a clean formatted table to stdout using tabulate."""
    if not rows:
        print("No data to display — all fetches failed.")
        return

    table_data = [
        [r["asset"], format_price(r["price"]), r["currency"]]
        for r in rows
    ]

    print(f"\nAsset Prices — fetched at {fetch_time}\n")
    print(tabulate(table_data, headers=["Asset", "Price", "Currency"], tablefmt="pretty"))
    print()

    errors = [r for r in rows if r.get("error")]
    if errors:
        print("Errors:")
        for row in errors:
            print(f"  - {row['asset']}: {row['error']}")
        print()


def main() -> None:
    """Main execution block: fetch prices and render the table."""
    fetch_time = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")

    log.info("Fetching asset prices...")

    results = [
        fetch_btc_usd(),
        fetch_yfinance_asset("^NSEI", "NIFTY50", "INR"),
        fetch_gold_inr_per_gram(),
    ]

    successful = [r for r in results if not r.get("error")]

    if len(successful) < len(results):
        log.warning("%d of %d fetches failed.", len(results) - len(successful), len(results))

    render_table(results, fetch_time)

    if len(successful) < len(results):
        sys.exit(1)


if __name__ == "__main__":
    main()