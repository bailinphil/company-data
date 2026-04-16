# AI Companies Data

A structured dataset of artificial intelligence companies worldwide, built to support an interactive infographic for high school students. The goal is to illustrate the size, geography, history, and ownership structure of the AI industry — going well beyond the household names most students already know.

## Repository structure

```
company-data/
├── README.md
├── .gitignore
├── data/
│   ├── ai-companies.csv       # source of truth: one row per company
|   ├── valuations.csv         # source of truth: one row per valuation event
│   └── ai_companies.db        # derived — rebuilt by csv_to_sqlite.py, not tracked in git
└── src/
    └── gather/                # data collection and maintenance
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

---

## Design decisions and context for contributors

This section records the reasoning behind non-obvious choices in the schema and tooling, so that future contributors — human or AI — don't have to reconstruct it.

### Why CSVs as source of truth, not SQLite directly

The CSVs are human-readable, git-diffable, and editable without any tooling. A change to a company's `gov_contract_notes` shows up as a clear line diff in a pull request. The same change in a SQLite binary is invisible to version control. SQLite is a much better query and serving layer, so we use both: edit in CSV, query and serve from SQLite. `csv_to_sqlite.py` is the bridge and is safe to re-run at any time — it drops and recreates both tables on every run.

### Why the `data/` directory is not in `src/`

All of the data for this project is not executable code, but may be written to or read by tools. See the directory listing above for additional details about which files are considered the source of truth and which are derived.

### Why the valuations table is separate

Two reasons: First, public and private companies have fundamentally different valuation cadences: public companies have a market cap that changes every trading day (we snapshot every 6 months); private companies only have a known valuation at funding round announcements, which may be years apart. Putting both in one table with a `date` column handles this naturally. Second, it makes time-series visualization straightforward — the entire history of any company's valuation is just `SELECT * FROM valuations WHERE company_id = ?` ordered by date.

### Why revenue and profit/loss are snapshot columns, not a time series

Revenue over time for companies like Google or Microsoft reflects enormous non-AI factors — advertising cycles, enterprise software contracts, the COVID-19 pandemic — that would mislead students trying to understand the AI industry specifically. A single 2025 snapshot is more honest about what we actually know and care about. Private company revenue is almost never disclosed, so a time series would be nearly empty anyway.

### The `CN (structural)` convention

Several Chinese companies have no disclosed government contracts but are subject to China's National Intelligence Law (2017), which compels cooperation with state intelligence on request. This is qualitatively different from a company like Palantir that has explicit, disclosed DoD contracts — it's a legal environment, not a transaction. We represent this as `CN (structural)` in the `gov_contracts` field rather than leaving it blank (which would be misleading) or marking it as a regular contract (which would be inaccurate). The `gov_contract_notes` field carries the explanation.

### Why `gov_contracts` replaced a simple `us_gov_contracts` boolean

The original boolean was US-centric and obscured important distinctions. A UAE government research institute (TII) *is* the government — there's no contractor/client relationship to describe. An Israeli company may have structural ties to military intelligence through its founders' backgrounds rather than any formal contract. A French company may have explicit Ministry of Defence contracts that carry very different human rights implications than the same arrangement in Saudi Arabia. The free-text `gov_contract_notes` field is where the real teaching content lives; `gov_contracts` is just a queryable index into it.

### The `data_confidence` field

Sources for private company valuations vary enormously in reliability. A valuation from a company's own press release about a funding round is `high`. A valuation inferred from a journalist's report citing "people familiar with the matter" is `medium`. A valuation from an aggregator article with no primary source is `low`. This field exists so that visualizations can communicate uncertainty honestly — a `low` confidence bubble should probably look different from a `high` confidence one.

### The start date of 2015 for market cap history

The canonical starting point for the modern AI era is usually the 2017 "Attention Is All You Need" paper (the Transformer architecture underlying nearly all current LLMs), or the 2022 public release of ChatGPT. We chose 2015 as the history start date to capture the pre-Transformer context — DeepMind was founded in 2010, OpenAI in 2015, and Nvidia's GPU dominance in ML was already visible by 2013–2015. This gives students a sense of how long the groundwork was being laid before the public noticed. The framing "AI history starts around 2015" is a pedagogical convenience, not a claim that nothing happened before then.

### The `add_company.py` script

This is an interactive CLI, not a bulk import tool. The intent is to make it easy to add one company at a time with prompts and validation, so that data entry doesn't require knowing the schema by heart. It enforces enum values, checks foreign keys in the valuations table, and uses Python's `csv.DictWriter` to ensure empty fields are always serialized correctly (a source of subtle bugs when writing CSV by hand). After running it, always run `csv_to_sqlite.py` to rebuild the database.

### Pipe-separated multi-value fields

Several fields (`sources`, `founder_names`, `founder_wikipedia_urls`, `gov_contracts`) hold multiple values in a single CSV cell, separated by `|`. This is a deliberate trade-off: a proper normalized schema would have junction tables for founders, sources, and government contracts, but that would make the CSVs much harder to read and edit by hand, and the additional complexity isn't worth it at this dataset size. If the dataset grows significantly or the multi-value fields need to be queried individually, splitting them into proper tables would be the right next step.
