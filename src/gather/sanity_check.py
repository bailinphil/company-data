#!/usr/bin/env python3
"""
sanity_check.py — data quality checks for ai_companies.db.

Prerequisites (must be run first):
    python src/gather/fetch_market_caps.py   # populate market cap history
    python src/gather/csv_to_sqlite.py       # build the SQLite database

Usage:
    python src/gather/sanity_check.py

All output is advisory: findings are suspicious items that warrant a human
look, not hard failures. The script always exits 0.

Checks are grouped into five categories:
    [VALUATION]  Implausible or suspicious valuation figures
    [CROSSFIELD] Contradictions between fields on the same company
    [COMPLETE]   Missing data that is expected to be present
    [GEO]        Malformed country / region codes
    [TEMPORAL]   Dates that are out of range or logically impossible
"""

import re
import sqlite3
import sys
from datetime import date
from pathlib import Path

DIR       = Path(__file__).parent
REPO_ROOT = DIR.parent.parent           # src/gather -> src -> repo root
DB_PATH   = REPO_ROOT / 'data' / 'ai_companies.db'

TODAY      = date.today()
THIS_YEAR  = TODAY.year

# Approximate all-time market cap ceiling (Nvidia peaked ~$3.7T, Apple ~$3.9T)
MAX_PLAUSIBLE_MARKET_CAP_B  = 5_000.0
# No private company has ever been valued above this
MAX_PLAUSIBLE_PRIVATE_VAL_B = 300.0
# Flag consecutive market_cap snapshots that drop by more than this fraction
MAX_SNAPSHOT_DROP_FRACTION  = 0.90

# ISO 3166-1 alpha-2: two uppercase letters
ISO_ALPHA2_RE = re.compile(r'^[A-Z]{2}$')


# ── Issue collector ───────────────────────────────────────────────────────────

issues = []   # list of (category, message)

def flag(category, msg):
    issues.append((category, msg))


# ── Checks ────────────────────────────────────────────────────────────────────

def check_valuation_plausibility(con):
    # Market cap snapshots above the plausible ceiling
    for row in con.execute("""
        SELECT c.company_name, v.date, v.valuation_usd_billions
        FROM valuations v
        JOIN companies c ON c.company_id = v.company_id
        WHERE v.valuation_type = 'market_cap_snapshot'
          AND v.valuation_usd_billions > ?
        ORDER BY v.valuation_usd_billions DESC
    """, (MAX_PLAUSIBLE_MARKET_CAP_B,)):
        flag('VALUATION',
              f"{row[0]}: market_cap_snapshot on {row[1]} = "
              f"${row[2]:,.1f}B exceeds plausible ceiling "
              f"(${MAX_PLAUSIBLE_MARKET_CAP_B:,.0f}B) — likely a currency "
              f"conversion error")

    # Private company valuations above the plausible ceiling
    for row in con.execute("""
        SELECT c.company_name, v.date, v.valuation_usd_billions, v.valuation_type
        FROM valuations v
        JOIN companies c ON c.company_id = v.company_id
        WHERE c.public_or_private = 'private'
          AND v.valuation_usd_billions > ?
        ORDER BY v.valuation_usd_billions DESC
    """, (MAX_PLAUSIBLE_PRIVATE_VAL_B,)):
        flag('VALUATION',
             f"{row[0]}: private company valuation on {row[1]} = "
             f"${row[2]:,.1f}B ({row[3]}) exceeds "
             f"${MAX_PLAUSIBLE_PRIVATE_VAL_B:,.0f}B — verify this is correct")

    # Consecutive market_cap_snapshot drops of >90% for the same company
    # (fetch ordered rows per company and compare neighbours in Python)
    snapshots = {}
    for row in con.execute("""
        SELECT company_id, date, valuation_usd_billions
        FROM valuations
        WHERE valuation_type = 'market_cap_snapshot'
          AND valuation_usd_billions IS NOT NULL
        ORDER BY company_id, date
    """):
        snapshots.setdefault(row[0], []).append((row[1], row[2]))

    name_map = dict(con.execute("SELECT company_id, company_name FROM companies"))
    for cid, rows in snapshots.items():
        for (d1, v1), (d2, v2) in zip(rows, rows[1:]):
            if v1 > 0 and (v1 - v2) / v1 > MAX_SNAPSHOT_DROP_FRACTION:
                flag('VALUATION',
                     f"{name_map.get(cid, cid)}: market cap dropped "
                     f"{(v1-v2)/v1:.0%} between {d1} (${v1:,.1f}B) "
                     f"and {d2} (${v2:,.1f}B)")


def check_cross_field_consistency(con):
    # Public company with no ticker
    for row in con.execute("""
        SELECT company_name FROM companies
        WHERE public_or_private = 'public'
          AND (stock_ticker IS NULL OR stock_ticker = '')
    """):
        flag('CROSSFIELD',
             f"{row[0]}: public_or_private='public' but stock_ticker is empty")

    # Ticker present but not marked public
    for row in con.execute("""
        SELECT company_name, stock_ticker, public_or_private FROM companies
        WHERE (stock_ticker IS NOT NULL AND stock_ticker != '')
          AND public_or_private != 'public'
    """):
        flag('CROSSFIELD',
             f"{row[0]}: stock_ticker='{row[1]}' but "
             f"public_or_private='{row[2]}'")

    # Acquired or defunct companies with recent market cap snapshots
    cutoff = str(date(THIS_YEAR - 1, 1, 1))
    for row in con.execute("""
        SELECT c.company_name, c.public_or_private, v.date
        FROM valuations v
        JOIN companies c ON c.company_id = v.company_id
        WHERE c.public_or_private IN ('acquired', 'defunct')
          AND v.valuation_type = 'market_cap_snapshot'
          AND v.date >= ?
        ORDER BY v.date DESC
    """, (cutoff,)):
        flag('CROSSFIELD',
             f"{row[0]}: status='{row[1]}' but has a market_cap_snapshot "
             f"as recent as {row[2]}")

    # category_secondary duplicates category_primary
    for row in con.execute("""
        SELECT company_name, category_primary, category_secondary
        FROM companies
        WHERE category_secondary IS NOT NULL
          AND category_secondary != ''
          AND category_secondary = category_primary
    """):
        flag('CROSSFIELD',
             f"{row[0]}: category_secondary='{row[2]}' duplicates "
             f"category_primary='{row[1]}'")


def check_completeness(con):
    # Public companies that have no valuation rows at all
    for row in con.execute("""
        SELECT c.company_name, c.stock_ticker
        FROM companies c
        LEFT JOIN valuations v ON v.company_id = c.company_id
        WHERE c.public_or_private = 'public'
          AND v.id IS NULL
    """):
        flag('COMPLETE',
             f"{row[0]} (ticker: {row[1]}): public company with no valuation "
             f"rows — did fetch_market_caps.py run successfully for this ticker?")

    # high-confidence rows missing sources
    for row in con.execute("""
        SELECT company_name FROM companies
        WHERE data_confidence = 'high'
          AND (sources IS NULL OR sources = '')
    """):
        flag('COMPLETE',
             f"{row[0]}: data_confidence='high' but sources is empty")

    # Missing ceo_name
    for row in con.execute("""
        SELECT company_name FROM companies
        WHERE ceo_name IS NULL OR ceo_name = ''
        ORDER BY company_name
    """):
        flag('COMPLETE', f"{row[0]}: ceo_name is missing")

    # Missing founder_names
    for row in con.execute("""
        SELECT company_name FROM companies
        WHERE founder_names IS NULL OR founder_names = ''
        ORDER BY company_name
    """):
        flag('COMPLETE', f"{row[0]}: founder_names is missing")


def check_geography(con):
    # hq_country not matching ISO alpha-2 format
    for row in con.execute("""
        SELECT company_name, hq_country FROM companies
        WHERE hq_country IS NOT NULL AND hq_country != ''
    """):
        if not ISO_ALPHA2_RE.match(row[1]):
            flag('GEO',
                 f"{row[0]}: hq_country='{row[1]}' is not a valid "
                 f"ISO 3166-1 alpha-2 code")

    # lead_investor_region: check each pipe- or comma-separated token
    for row in con.execute("""
        SELECT company_name, lead_investor_region FROM companies
        WHERE lead_investor_region IS NOT NULL AND lead_investor_region != ''
    """):
        # Normalise: split on pipe or comma, strip whitespace
        tokens = re.split(r'[|,]', row[1])
        for token in tokens:
            token = token.strip()
            if not token:
                continue
            # Allow country codes with optional qualifier like "(structural)"
            code = re.sub(r'\s*\(.*\)', '', token).strip()
            if code and not ISO_ALPHA2_RE.match(code):
                flag('GEO',
                     f"{row[0]}: lead_investor_region contains "
                     f"'{token}' which doesn't look like an ISO alpha-2 code")


def check_temporal(con):
    # founded_year in the future
    for row in con.execute("""
        SELECT company_name, founded_year FROM companies
        WHERE founded_year > ?
    """, (THIS_YEAR,)):
        flag('TEMPORAL',
              f"{row[0]}: founded_year={row[1]} is in the future")

    # founded_year implausibly early for an AI company
    for row in con.execute("""
        SELECT company_name, founded_year FROM companies
        WHERE founded_year < 1950 AND founded_year IS NOT NULL
    """):
        flag('TEMPORAL',
             f"{row[0]}: founded_year={row[1]} is before 1950 — verify this "
             f"is intentional for an AI company")

    # Valuation date predates founding year
    for row in con.execute("""
        SELECT c.company_name, c.founded_year, v.date, v.valuation_type
        FROM valuations v
        JOIN companies c ON c.company_id = v.company_id
        WHERE c.founded_year IS NOT NULL
          AND CAST(substr(v.date, 1, 4) AS INTEGER) < c.founded_year
    """):
        flag('TEMPORAL',
             f"{row[0]}: valuation row dated {row[2]} ({row[3]}) predates "
             f"founding year {row[1]}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if not DB_PATH.exists():
        sys.exit(
            f"✗ Database not found at {DB_PATH}\n"
            f"  Run: python src/gather/fetch_market_caps.py\n"
            f"       python src/gather/csv_to_sqlite.py"
        )

    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row

    check_valuation_plausibility(con)
    check_cross_field_consistency(con)
    check_completeness(con)
    check_geography(con)
    check_temporal(con)

    con.close()

    # ── Report ────────────────────────────────────────────────────────────────
    if not issues:
        print("✓ No suspicious items found.")
        return

    category_order = ['VALUATION', 'CROSSFIELD', 'COMPLETE', 'GEO', 'TEMPORAL']
    by_cat = {}
    for cat, msg in issues:
        by_cat.setdefault(cat, []).append(msg)

    print(f"\nFound {len(issues)} item(s) that look suspicious and should be checked:\n")
    for cat in category_order:
        for msg in by_cat.get(cat, []):
            print(f"  [{cat}] {msg}")


if __name__ == '__main__':
    main()
