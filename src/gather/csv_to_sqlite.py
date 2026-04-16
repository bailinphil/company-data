#!/usr/bin/env python3
"""
csv_to_sqlite.py — build ai_companies.db from ai-companies.csv and valuations.csv.

Usage:
    python csv_to_sqlite.py

Reads CSVs from data/, writes ai_companies.db to data/.
Safe to re-run: drops and recreates tables each time.

The database has two tables:
    companies   — one row per company
    valuations  — one row per valuation event (funding round or market cap snapshot)

Foreign key enforcement is enabled. Indexes are created on common query paths.
"""

import csv
import sqlite3
from pathlib import Path

DIR            = Path(__file__).parent
REPO_ROOT      = DIR.parent.parent          # src/gather -> src -> repo root
COMPANIES_CSV  = REPO_ROOT / 'data' / 'ai-companies.csv'
VALUATIONS_CSV = REPO_ROOT / 'data' / 'valuations.csv'
DB_PATH        = REPO_ROOT / 'data' / 'ai_companies.db'


# ── Type coercion helpers ─────────────────────────────────────────────────────

def to_int(val):
    try:
        return int(val) if val.strip() else None
    except (ValueError, AttributeError):
        return None

def to_float(val):
    try:
        return float(val) if val.strip() else None
    except (ValueError, AttributeError):
        return None

def to_str(val):
    """Return None for empty strings so SQLite stores NULL, not ''."""
    if val is None:
        return None
    stripped = val.strip()
    return stripped if stripped else None


# ── DDL ───────────────────────────────────────────────────────────────────────

COMPANIES_DDL = """
CREATE TABLE companies (
    company_id                   TEXT PRIMARY KEY,
    company_name                 TEXT NOT NULL,
    founded_year                 INTEGER,
    hq_country                   TEXT,           -- ISO alpha-2
    hq_city                      TEXT,
    public_or_private            TEXT CHECK(public_or_private IN
                                     ('public','private','acquired','defunct')),
    stock_ticker                 TEXT,
    category_primary             TEXT CHECK(category_primary IN
                                     ('foundation_model','infrastructure','tooling',
                                      'application','research_lab','hardware')),
    category_secondary           TEXT CHECK(category_secondary IN
                                     ('foundation_model','infrastructure','tooling',
                                      'application','research_lab','hardware', NULL)),
    revenue_2025_usd_billions    REAL,
    profit_loss_2025_usd_billions REAL,
    lead_investor_region         TEXT,
    data_confidence              TEXT CHECK(data_confidence IN ('high','medium','low')),
    sources                      TEXT,           -- pipe-separated URLs
    ceo_name                     TEXT,
    ceo_wikipedia_url            TEXT,
    founder_names                TEXT,           -- pipe-separated
    founder_wikipedia_urls       TEXT,           -- pipe-separated
    gov_contracts                TEXT,           -- pipe-separated country codes
    gov_contract_notes           TEXT,
    regulatory_actions           TEXT,
    notes                        TEXT
);
"""

VALUATIONS_DDL = """
CREATE TABLE valuations (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id               TEXT NOT NULL REFERENCES companies(company_id),
    date                     TEXT NOT NULL,  -- ISO 8601 YYYY-MM-DD
    valuation_usd_billions   REAL,
    valuation_type           TEXT CHECK(valuation_type IN
                                 ('funding_round','market_cap_snapshot',
                                  'ipo','acquisition')),
    round_name               TEXT,
    notes                    TEXT,
    source                   TEXT
);
"""

INDEXES = [
    "CREATE INDEX idx_valuations_company ON valuations(company_id);",
    "CREATE INDEX idx_valuations_date    ON valuations(date);",
    "CREATE INDEX idx_companies_country  ON companies(hq_country);",
    "CREATE INDEX idx_companies_category ON companies(category_primary);",
    "CREATE INDEX idx_companies_public   ON companies(public_or_private);",
]


# ── Build DB ──────────────────────────────────────────────────────────────────

def build():
    # Read CSVs
    with open(COMPANIES_CSV, newline='') as f:
        companies = list(csv.DictReader(f))
    with open(VALUATIONS_CSV, newline='') as f:
        valuations = list(csv.DictReader(f))

    print(f"Read {len(companies)} companies, {len(valuations)} valuation rows.")

    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA foreign_keys = ON;")
    con.execute("PRAGMA journal_mode = WAL;")  # better for concurrent reads

    # Drop and recreate
    con.execute("DROP TABLE IF EXISTS valuations;")
    con.execute("DROP TABLE IF EXISTS companies;")
    con.execute(COMPANIES_DDL)
    con.execute(VALUATIONS_DDL)
    for idx in INDEXES:
        con.execute(idx)

    # Insert companies
    company_insert = """
        INSERT INTO companies VALUES (
            :company_id, :company_name, :founded_year,
            :hq_country, :hq_city, :public_or_private, :stock_ticker,
            :category_primary, :category_secondary,
            :revenue_2025_usd_billions, :profit_loss_2025_usd_billions,
            :lead_investor_region, :data_confidence, :sources,
            :ceo_name, :ceo_wikipedia_url,
            :founder_names, :founder_wikipedia_urls,
            :gov_contracts, :gov_contract_notes,
            :regulatory_actions, :notes
        )
    """
    for row in companies:
        con.execute(company_insert, {
            'company_id':                    to_str(row['company_id']),
            'company_name':                  to_str(row['company_name']),
            'founded_year':                  to_int(row['founded_year']),
            'hq_country':                    to_str(row['hq_country']),
            'hq_city':                       to_str(row['hq_city']),
            'public_or_private':             to_str(row['public_or_private']),
            'stock_ticker':                  to_str(row['stock_ticker']),
            'category_primary':              to_str(row['category_primary']),
            'category_secondary':            to_str(row['category_secondary']),
            'revenue_2025_usd_billions':     to_float(row['revenue_2025_usd_billions']),
            'profit_loss_2025_usd_billions': to_float(row['profit_loss_2025_usd_billions']),
            'lead_investor_region':          to_str(row['lead_investor_region']),
            'data_confidence':               to_str(row['data_confidence']),
            'sources':                       to_str(row['sources']),
            'ceo_name':                      to_str(row['ceo_name']),
            'ceo_wikipedia_url':             to_str(row['ceo_wikipedia_url']),
            'founder_names':                 to_str(row['founder_names']),
            'founder_wikipedia_urls':        to_str(row['founder_wikipedia_urls']),
            'gov_contracts':                 to_str(row['gov_contracts']),
            'gov_contract_notes':            to_str(row['gov_contract_notes']),
            'regulatory_actions':            to_str(row['regulatory_actions']),
            'notes':                         to_str(row['notes']),
        })

    # Insert valuations
    valuation_insert = """
        INSERT INTO valuations
            (company_id, date, valuation_usd_billions,
             valuation_type, round_name, notes, source)
        VALUES
            (:company_id, :date, :valuation_usd_billions,
             :valuation_type, :round_name, :notes, :source)
    """
    for row in valuations:
        con.execute(valuation_insert, {
            'company_id':             to_str(row['company_id']),
            'date':                   to_str(row['date']),
            'valuation_usd_billions': to_float(row['valuation_usd_billions']),
            'valuation_type':         to_str(row['valuation_type']),
            'round_name':             to_str(row['round_name']),
            'notes':                  to_str(row['notes']),
            'source':                 to_str(row['source']),
        })

    con.commit()

    # ── Smoke tests ───────────────────────────────────────────────────────────
    print("\nSmoke tests:")

    n_companies = con.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
    n_valuations = con.execute("SELECT COUNT(*) FROM valuations").fetchone()[0]
    print(f"  companies:  {n_companies} rows")
    print(f"  valuations: {n_valuations} rows")

    print("\n  Companies by country:")
    for row in con.execute("""
        SELECT hq_country, COUNT(*) as n
        FROM companies GROUP BY hq_country ORDER BY n DESC
    """):
        print(f"    {row[0]:5s}  {row[1]}")

    print("\n  Companies by category:")
    for row in con.execute("""
        SELECT category_primary, COUNT(*) as n
        FROM companies GROUP BY category_primary ORDER BY n DESC
    """):
        print(f"    {row[0]:20s}  {row[1]}")

    print("\n  Most valuation history (top 5):")
    for row in con.execute("""
        SELECT c.company_name, COUNT(v.id) as n,
               MIN(v.date) as earliest, MAX(v.date) as latest
        FROM companies c
        JOIN valuations v ON v.company_id = c.company_id
        GROUP BY c.company_id
        ORDER BY n DESC LIMIT 5
    """):
        print(f"    {row[0]:25s}  {row[1]} rows  {row[2]} → {row[3]}")

    print("\n  Companies with gov contracts outside US:")
    for row in con.execute("""
        SELECT company_name, hq_country, gov_contracts
        FROM companies
        WHERE gov_contracts IS NOT NULL
          AND gov_contracts != ''
          AND gov_contracts != 'US'
        ORDER BY hq_country
    """):
        print(f"    {row[1]:5s}  {row[0]:30s}  {row[2]}")

    print("\n  Private companies with no profit/loss data:")
    for row in con.execute("""
        SELECT company_name
        FROM companies
        WHERE public_or_private = 'private'
          AND profit_loss_2025_usd_billions IS NULL
        ORDER BY company_name
    """):
        print(f"    {row[0]}")

    con.close()
    print(f"\n✓ Written to {DB_PATH}")


if __name__ == '__main__':
    build()
