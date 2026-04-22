#!/usr/bin/env python3
"""
add_company.py — data entry tool for the AI companies dataset.

Usage:
    python add_company.py company          # add a new company row
    python add_company.py valuation        # add one or more valuation rows
    python add_company.py validate         # check both CSVs for integrity

CSVs are read from / written to data/ at the repo root.
"""

import csv
import io
import os
import sys
from datetime import datetime
from pathlib import Path

DIR       = Path(__file__).parent
REPO_ROOT = DIR.parent.parent          # src/gather -> src -> repo root
COMPANIES_FILE  = REPO_ROOT / 'data' / 'ai-companies.csv'
VALUATIONS_FILE = REPO_ROOT / 'data' / 'valuations.csv'

COMPANIES_FIELDS = [
    'company_id',
    'company_name',
    'founded_year',
    'hq_country',
    'hq_city',
    'public_or_private',
    'stock_ticker',
    'category_primary',
    'category_secondary',
    'revenue_2025_usd_billions',
    'profit_loss_2025_usd_billions',
    'lead_investor_region',
    'data_confidence',
    'sources',
    'ceo_name',
    'ceo_wikipedia_url',
    'founder_names',
    'founder_wikipedia_urls',
    'gov_contracts',
    'gov_contract_notes',
    'regulatory_actions',
    'notes',
]

VALUATIONS_FIELDS = [
    'company_id',
    'date',
    'valuation_usd_billions',
    'valuation_type',
    'round_name',
    'notes',
    'source',
]

ENUMS = {
    'public_or_private': ['public', 'private', 'acquired', 'defunct'],
    'category_primary':  ['foundation_model', 'infrastructure', 'tooling',
                          'application', 'research_lab', 'hardware',
                          'cloud_ai', 'semiconductor', 'autonomous_vehicles',
                          'robotics'],
    'category_secondary':['foundation_model', 'infrastructure', 'tooling',
                          'application', 'research_lab', 'hardware',
                          'cloud_ai', 'semiconductor', 'autonomous_vehicles',
                          'robotics', ''],
    'data_confidence':   ['high', 'medium', 'low'],

    'valuation_type':    ['funding_round', 'market_cap_snapshot', 'ipo', 'acquisition'],
}


# ── Helpers ──────────────────────────────────────────────────────────────────

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

def ask(prompt, default='', enum=None, required=False):
    """Prompt the user for a value, with optional default and enum validation."""
    hint = ''
    if enum:
        hint = f" [{'/'.join(enum)}]"
    if default:
        hint += f" (default: {default})"
    while True:
        raw = input(f"  {prompt}{hint}: ").strip()
        value = raw if raw else default
        if required and not value:
            print("    ✗ This field is required.")
            continue
        if enum and value and value not in enum:
            print(f"    ✗ Must be one of: {', '.join(enum)}")
            continue
        return value

def confirm(prompt):
    return input(f"\n{prompt} [y/N]: ").strip().lower() == 'y'


# ── Add company ───────────────────────────────────────────────────────────────

def add_company():
    companies = read_csv(COMPANIES_FILE)
    existing_ids = {r['company_id'] for r in companies}

    print("\n── Add Company ──────────────────────────────────────────────────")
    print("Pipe-separate multiple values where noted (e.g. founder_names).")
    print("Leave blank for unknown/null fields.\n")

    row = {}

    # Required fields
    while True:
        cid = ask("company_id (short slug, e.g. 'mistral-ai')", required=True)
        if cid in existing_ids:
            print(f"    ✗ '{cid}' already exists.")
        else:
            break
    row['company_id'] = cid

    row['company_name']   = ask("company_name", required=True)
    row['founded_year']   = ask("founded_year (YYYY)", required=True)
    row['hq_country']     = ask("hq_country (ISO alpha-2, e.g. US, FR, CN)", required=True).upper()
    row['hq_city']        = ask("hq_city", required=True)
    row['public_or_private'] = ask("public_or_private", required=True,
                                   enum=ENUMS['public_or_private'])
    row['stock_ticker']   = ask("stock_ticker (blank if private)")
    row['category_primary']   = ask("category_primary", required=True,
                                    enum=ENUMS['category_primary'])
    row['category_secondary'] = ask("category_secondary",
                                    enum=ENUMS['category_secondary'])

    # Financial snapshot
    print("\n  ── 2025 financials (public companies only; leave blank if unknown) ──")
    row['revenue_2025_usd_billions']     = ask("revenue_2025_usd_billions")
    row['profit_loss_2025_usd_billions'] = ask("profit_loss_2025_usd_billions "
                                               "(negative = loss)")

    # Provenance
    print("\n  ── Provenance ──")
    row['lead_investor_region'] = ask("lead_investor_region (e.g. 'US', 'US, SA')")
    row['data_confidence']      = ask("data_confidence", default='medium',
                                      enum=ENUMS['data_confidence'])
    row['sources'] = ask("sources (pipe-separated URLs)")

    # Leadership
    print("\n  ── Leadership ──")
    row['ceo_name']              = ask("ceo_name")
    row['ceo_wikipedia_url']     = ask("ceo_wikipedia_url")
    row['founder_names']         = ask("founder_names (pipe-separated if multiple)")
    row['founder_wikipedia_urls']= ask("founder_wikipedia_urls (pipe-separated)")
    print("\n  ── Government contracts & regulatory history ──")
    print("  gov_contracts: pipe-separated government codes, e.g. 'US|FR|EU'.")
    print("  Append '(structural)' for legal obligations (e.g. 'CN (structural)').")
    row['gov_contracts']      = ask("gov_contracts")
    row['gov_contract_notes'] = ask("gov_contract_notes (nature/significance of contracts)")
    row['regulatory_actions'] = ask("regulatory_actions (lawsuits, fines, bans, controversies)")
    row['notes'] = ask("notes (free text)")

    # Preview and confirm
    print("\n── Preview ──────────────────────────────────────────────────────")
    for k, v in row.items():
        print(f"  {k}: {v!r}")

    if confirm("Save this company?"):
        companies.append(row)
        write_csv(COMPANIES_FILE, COMPANIES_FIELDS, companies)
        print(f"✓ Saved '{row['company_id']}' to ai-companies.csv")
    else:
        print("Cancelled.")


# ── Add valuation ─────────────────────────────────────────────────────────────

def add_valuation():
    companies  = read_csv(COMPANIES_FILE)
    valuations = read_csv(VALUATIONS_FILE)
    valid_ids  = {r['company_id'] for r in companies}

    print("\n── Add Valuation Row(s) ─────────────────────────────────────────")
    print("You can add multiple rows for the same company in one session.\n")

    while True:
        cid = ask("company_id", required=True)
        if cid not in valid_ids:
            print(f"    ✗ '{cid}' not found in ai-companies.csv. "
                  f"Add the company first.")
            continue
        break

    adding = True
    while adding:
        row = {'company_id': cid}

        # Date
        while True:
            d = ask("date (YYYY-MM-DD)", required=True)
            try:
                datetime.strptime(d, '%Y-%m-%d')
                row['date'] = d
                break
            except ValueError:
                print("    ✗ Use YYYY-MM-DD format.")

        row['valuation_usd_billions'] = ask("valuation_usd_billions")
        row['valuation_type'] = ask("valuation_type", required=True,
                                    enum=ENUMS['valuation_type'])
        row['round_name'] = ask("round_name (e.g. 'Series A', or 'n/a')")
        row['notes']  = ask("notes")
        row['source'] = ask("source (single URL or citation)")

        print("\n  Preview:", row)
        if confirm("Save this valuation row?"):
            valuations.append(row)
            write_csv(VALUATIONS_FILE, VALUATIONS_FIELDS, valuations)
            print("✓ Saved.")

        adding = confirm("Add another valuation row for this company?")


# ── Validate ──────────────────────────────────────────────────────────────────

def validate():
    print("\n── Validating ───────────────────────────────────────────────────")
    errors = []

    companies  = read_csv(COMPANIES_FILE)
    valuations = read_csv(VALUATIONS_FILE)

    company_ids = {r['company_id'] for r in companies}

    # Check column counts
    for i, row in enumerate(companies, start=2):
        if set(row.keys()) != set(COMPANIES_FIELDS):
            errors.append(f"companies row {i}: unexpected columns")

    for i, row in enumerate(valuations, start=2):
        if set(row.keys()) != set(VALUATIONS_FIELDS):
            errors.append(f"valuations row {i}: unexpected columns")

    # Check foreign keys
    for i, row in enumerate(valuations, start=2):
        if row['company_id'] not in company_ids:
            errors.append(f"valuations row {i}: unknown company_id "
                          f"'{row['company_id']}'")

    # Check enum fields in companies
    for i, row in enumerate(companies, start=2):
        for field, allowed in ENUMS.items():
            if field in COMPANIES_FIELDS:
                val = row.get(field, '')
                if val and val not in allowed:
                    errors.append(f"companies row {i} ({row['company_id']}): "
                                  f"{field}={val!r} not in {allowed}")

    # Check dates in valuations
    for i, row in enumerate(valuations, start=2):
        d = row.get('date', '')
        if d:
            try:
                datetime.strptime(d, '%Y-%m-%d')
            except ValueError:
                errors.append(f"valuations row {i}: bad date {d!r}")

    if errors:
        print(f"✗ {len(errors)} error(s) found:")
        for e in errors:
            print(f"  • {e}")
    else:
        print(f"✓ All good. {len(companies)} companies, "
              f"{len(valuations)} valuation rows.")

    # Summary stats
    val_counts = {}
    for row in valuations:
        val_counts[row['company_id']] = val_counts.get(row['company_id'], 0) + 1

    no_vals = [cid for cid in company_ids if cid not in val_counts]
    if no_vals:
        print(f"\n  Companies with no valuation rows: {no_vals}")

    todo = [r for r in valuations if str(r.get('valuation_usd_billions','')).startswith('TODO') 
            or r.get('source') == 'yfinance']
    if todo:
        print(f"\n  Valuation rows still needing yfinance population: "
              f"{len(todo)}")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    if len(sys.argv) < 2 or sys.argv[1] not in ('company', 'valuation', 'validate'):
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == 'company':
        add_company()
    elif cmd == 'valuation':
        add_valuation()
    elif cmd == 'validate':
        validate()
