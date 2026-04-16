#!/usr/bin/env python3
"""
fetch_market_caps.py — populate market_cap_snapshot rows in valuations.csv
for all public companies using yfinance.

Run this locally (requires internet access):
    pip install yfinance
    python fetch_market_caps.py

It will:
  1. Read ai-companies.csv to find all public companies with a stock_ticker.
  2. For each, fetch historical market cap at 6-month intervals from
     2015-01-01 to today.
  3. Remove any existing market_cap_snapshot rows for those companies
     in valuations.csv (so re-running is safe / idempotent).
  4. Append the new snapshot rows and save.

Requires ai-companies.csv and valuations.csv to be in data/ at the repo root.
"""

import csv
import io
import sys
from datetime import date, timedelta
from pathlib import Path

try:
    import yfinance as yf
except ImportError:
    sys.exit("yfinance not installed. Run: pip install yfinance")

DIR             = Path(__file__).parent
REPO_ROOT       = DIR.parent.parent         # src/gather -> src -> repo root
COMPANIES_FILE  = REPO_ROOT / 'data' / 'ai-companies.csv'
VALUATIONS_FILE = REPO_ROOT / 'data' / 'valuations.csv'
DB_PATH         = REPO_ROOT / 'data' / 'ai_companies.db'

VALUATIONS_FIELDS = [
    'company_id',
    'date',
    'valuation_usd_billions',
    'valuation_type',
    'round_name',
    'notes',
    'source',
]

START_DATE = date(2015, 1, 1)
INTERVAL_MONTHS = 6


def six_month_dates(start, end):
    """Yield dates at ~6-month intervals between start and end."""
    d = start
    while d <= end:
        yield d
        # Advance ~6 months
        month = d.month + INTERVAL_MONTHS
        year  = d.year + (month - 1) // 12
        month = (month - 1) % 12 + 1
        d = date(year, month, 1)


def read_csv(path):
    with open(path, newline='') as f:
        return list(csv.DictReader(f))


def write_csv(path, fields, rows):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields, quoting=csv.QUOTE_MINIMAL,
                       extrasaction='ignore')
    w.writeheader()
    w.writerows(rows)
    with open(path, 'w', newline='') as f:
        f.write(buf.getvalue())


def fetch_market_caps():
    companies  = read_csv(COMPANIES_FILE)
    valuations = read_csv(VALUATIONS_FILE)

    public_cos = [
        r for r in companies
        if r['public_or_private'] == 'public' and r['stock_ticker']
    ]

    if not public_cos:
        print("No public companies with tickers found in ai-companies.csv.")
        return

    print(f"Found {len(public_cos)} public companies: "
          f"{[r['stock_ticker'] for r in public_cos]}\n")

    today = date.today()
    snapshot_dates = list(six_month_dates(START_DATE, today))
    print(f"Will fetch {len(snapshot_dates)} snapshots per company "
          f"({START_DATE} → {today}, every {INTERVAL_MONTHS} months)\n")

    # Remove old market_cap_snapshot rows for public companies
    public_ids = {r['company_id'] for r in public_cos}
    valuations = [
        row for row in valuations
        if not (row['company_id'] in public_ids
                and row['valuation_type'] == 'market_cap_snapshot')
    ]
    print(f"Cleared old market_cap_snapshot rows for: {public_ids}\n")

    # Cache exchange rates to avoid redundant fetches (currency -> USD rate)
    fx_cache = {}

    def get_usd_rate(currency):
        """Return how many USD one unit of currency is worth. 1.0 for USD."""
        if currency == 'USD':
            return 1.0
        if currency in fx_cache:
            return fx_cache[currency]
        fx_ticker = f'{currency}USD=X'
        try:
            rate = float(yf.Ticker(fx_ticker).info.get('regularMarketPrice', None))
        except Exception:
            rate = None
        if not rate:
            print(f"  ✗ Could not fetch exchange rate for {currency}, skipping company.")
            fx_cache[currency] = None
        else:
            print(f"  FX: 1 {currency} = {rate:.6f} USD")
            fx_cache[currency] = rate
        return fx_cache[currency]

    new_rows = []
    for company in public_cos:
        cid    = company['company_id']
        ticker = company['stock_ticker']
        print(f"Fetching {ticker} ({cid})...")

        try:
            tk = yf.Ticker(ticker)
            # Get shares outstanding (most recent)
            info = tk.info
            shares = info.get('sharesOutstanding')
            if not shares:
                print(f"  ✗ No sharesOutstanding for {ticker}, skipping.")
                continue

            currency = info.get('currency', 'USD')
            usd_rate = get_usd_rate(currency)
            if usd_rate is None:
                continue

            # Fetch daily close prices over the full range
            hist = tk.history(
                start=START_DATE.isoformat(),
                end=today.isoformat(),
                interval='1d',
                auto_adjust=True,
            )

            if hist.empty:
                print(f"  ✗ No price history for {ticker}, skipping.")
                continue

            # For each target snapshot date, find the nearest available
            # trading day (look forward up to 7 days)
            for snap_date in snapshot_dates:
                found = None
                for delta in range(8):
                    candidate = snap_date + timedelta(days=delta)
                    candidate_str = candidate.isoformat()
                    matches = hist[hist.index.date == candidate]
                    if not matches.empty:
                        close_price = float(matches['Close'].iloc[0])
                        close_usd = close_price * usd_rate
                        market_cap_b = round((close_usd * shares) / 1e9, 2)
                        currency_note = (f' × {usd_rate:.4f} {currency}/USD'
                                         if currency != 'USD' else '')
                        found = {
                            'company_id':             cid,
                            'date':                   candidate_str,
                            'valuation_usd_billions': market_cap_b,
                            'valuation_type':         'market_cap_snapshot',
                            'round_name':             'n/a',
                            'notes': (f'{ticker} close {close_price:.2f} {currency}'
                                      f'{currency_note} × '
                                      f'{shares/1e9:.3f}B shares'),
                            'source': f'yfinance/{ticker}',
                        }
                        break
                if found:
                    new_rows.append(found)
                # else: market didn't exist yet (e.g. pre-IPO), silently skip

            print(f"  ✓ {sum(1 for r in new_rows if r['company_id'] == cid)} "
                  f"snapshot rows added for {ticker}")

        except Exception as e:
            print(f"  ✗ Error fetching {ticker}: {e}")

    valuations.extend(new_rows)

    # Sort: company_id, then date
    valuations.sort(key=lambda r: (r['company_id'], r['date']))

    write_csv(VALUATIONS_FILE, VALUATIONS_FIELDS, valuations)
    print(f"\n✓ Done. Added {len(new_rows)} market cap snapshots. "
          f"Total valuation rows: {len(valuations)}")


if __name__ == '__main__':
    fetch_market_caps()
