# AI Companies Data

A structured dataset of artificial intelligence companies worldwide, built to support an interactive infographic for high school students. The goal is to illustrate the size, geography, history, and ownership structure of the AI industry — going well beyond the household names most students already know.

## Repository structure

```
company-data/
├── README.md
├── .gitignore
├── data/
│   └── ai_companies.db        # derived — rebuilt by csv_to_sqlite.py, not tracked in git
└── src/
    └── gather/                # data collection and maintenance
        ├── companies.csv      # source of truth: one row per company
        ├── valuations.csv     # source of truth: one row per valuation event
        ├── add_company.py     # interactive CLI for adding/validating data
        ├── csv_to_sqlite.py   # builds data/ai_companies.db from the CSVs
        └── fetch_market_caps.py  # populates public company market cap history
```

## Workflow

The CSVs are the **source of truth**. The SQLite database is a derived artifact and is not tracked in git.

```bash
# Add a new company interactively
python src/gather/add_company.py company

# Add valuation rows for an existing company
python src/gather/add_company.py valuation

# Check for structural errors (missing foreign keys, bad enums, etc.)
python src/gather/add_company.py validate

# Rebuild the SQLite database after any edits
python src/gather/csv_to_sqlite.py

# Populate public company market cap history (run locally, needs internet)
pip install yfinance
python src/gather/fetch_market_caps.py
```

## Schema

### companies

| Column | Type | Notes |
|--------|------|-------|
| `company_id` | string | Primary key. Short slug, e.g. `openai`, `mistral-ai` |
| `company_name` | string | |
| `founded_year` | integer | |
| `hq_country` | string | ISO 3166-1 alpha-2, e.g. `US`, `FR`, `CN` |
| `hq_city` | string | |
| `public_or_private` | enum | `public` \| `private` \| `acquired` \| `defunct` |
| `stock_ticker` | string | Null if private |
| `category_primary` | enum | `foundation_model` \| `infrastructure` \| `tooling` \| `application` \| `research_lab` \| `hardware` |
| `category_secondary` | enum | Same options as primary; null if not applicable |
| `revenue_2025_usd_billions` | float | Most recent known annual revenue; public companies only in most cases |
| `profit_loss_2025_usd_billions` | float | Positive = profit, negative = loss. Null for most private companies — intentionally, not an oversight |
| `lead_investor_region` | string | Country code(s) of lead investor(s); hand-approximate |
| `data_confidence` | enum | `high` \| `medium` \| `low` |
| `sources` | string | Pipe-separated URLs |
| `ceo_name` | string | |
| `ceo_wikipedia_url` | string | |
| `founder_names` | string | Pipe-separated |
| `founder_wikipedia_urls` | string | Pipe-separated |
| `gov_contracts` | string | Pipe-separated government codes. `CN (structural)` means legal obligation under PRC National Intelligence Law rather than a discrete contract |
| `gov_contract_notes` | string | Nature and significance of government relationships |
| `regulatory_actions` | string | Lawsuits, fines, bans, and notable controversies |
| `notes` | string | Free text |

### valuations

| Column | Type | Notes |
|--------|------|-------|
| `company_id` | string | Foreign key → `companies.company_id` |
| `date` | string | ISO 8601 `YYYY-MM-DD` |
| `valuation_usd_billions` | float | |
| `valuation_type` | enum | `funding_round` \| `market_cap_snapshot` \| `ipo` \| `acquisition` |
| `round_name` | string | e.g. `Series A`, `n/a` for market cap snapshots |
| `notes` | string | e.g. lead investor, deal context |
| `source` | string | Single URL or citation |

## Data notes

**Private company financials are mostly absent by design.** Private companies are not required to disclose revenue or profit/loss. The pattern of nulls in `profit_loss_2025_usd_billions` for private companies is itself a teaching point: most of these companies are burning VC capital, and we simply cannot know how much.

**Chinese companies carry `CN (structural)` in `gov_contracts`.** China's National Intelligence Law (2017) requires all Chinese companies and citizens to cooperate with state intelligence agencies on request. This is a structural legal obligation that applies regardless of whether a specific government contract exists.

**Public company market cap history requires `fetch_market_caps.py`.** The valuations table ships with placeholder rows for public companies. Run `src/gather/fetch_market_caps.py` locally (requires `pip install yfinance`) to populate 6-month market cap snapshots back to 2015. The resulting database is written to `data/ai_companies.db`.

**Valuation data for private companies is sparse and point-in-time.** Each row represents a disclosed funding round. The true current value of any private company is unknown between rounds.

## Coverage

Current seed dataset: 29 companies across 8 countries.

| Country | Companies |
|---------|-----------|
| US | 18 |
| CN | 4 |
| GB | 2 |
| AE | 1 |
| CA | 1 |
| DE | 1 |
| FR | 1 |
| IL | 1 |

Planned additions: more US application-layer companies, ByteDance/Doubao, MiniMax, G42 (UAE), Krutrim (India), Sarvam AI (India), Preferred Networks (Japan).

## Pedagogical context

This dataset was built to support a classroom exercise asking students: *do the people making decisions at these companies share my values? Who should I trust?*

The `gov_contract_notes`, `regulatory_actions`, `ceo_wikipedia_url`, and `founder_wikipedia_urls` fields are specifically designed to support that question. The Wikipedia links are a starting point, not an endpoint.
