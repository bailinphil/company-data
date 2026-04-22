"""Build the standalone bubble-chart site into visualize/dist/.

Reads data/ai_companies.db, serializes each company with its most recent
valuation as `company_value`, embeds the JSON payload into the HTML
template, and copies the CSS/JS next to it. The resulting dist/ folder is
self-contained and can be opened directly via file:// or deployed to any
static host.

Usage:
    python visualize/build.py
"""

from __future__ import annotations

import datetime as dt
import json
import shutil
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent
DB_PATH = REPO_ROOT / "data" / "ai_companies.db"
SRC_DIR = ROOT / "src"
DIST_DIR = ROOT / "dist"
TEMPLATE_PATH = SRC_DIR / "index.html.tmpl"
STATIC_FILES = ("styles.css", "app.js")
DATA_PLACEHOLDER = "{{DATA}}"

# ISO 3166-1 alpha-2 → display name. Only the codes present in the dataset need
# to be listed; if a new code shows up, the build fails loudly so it gets added.
COUNTRY_NAMES = {
    "AE": "United Arab Emirates",
    "CA": "Canada",
    "CN": "China",
    "DE": "Germany",
    "FR": "France",
    "GB": "United Kingdom",
    "IL": "Israel",
    "JP": "Japan",
    "KR": "South Korea",
    "NL": "Netherlands",
    "TW": "Taiwan",
    "US": "United States",
}


def _split_pipes(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [part.strip() for part in raw.split("|") if part.strip()]


def _split_founder_names(raw: str | None) -> list[str]:
    # Schema says pipe-separated, but several rows use commas. Prefer pipes
    # when present, fall back to commas otherwise so both styles work.
    if not raw:
        return []
    sep = "|" if "|" in raw else ","
    return [part.strip() for part in raw.split(sep) if part.strip()]


def _zip_people(names: str | None, urls: str | None) -> list[dict]:
    name_list = _split_founder_names(names)
    url_list = _split_pipes(urls)
    people = []
    for i, name in enumerate(name_list):
        people.append({
            "name": name,
            "wikipedia_url": url_list[i] if i < len(url_list) else None,
        })
    return people


def _latest_valuations(conn: sqlite3.Connection) -> dict[str, dict]:
    """Return {company_id: {value, date, type}} for the most recent row per company."""
    rows = conn.execute(
        """
        SELECT v.company_id, v.date, v.valuation_usd_billions, v.valuation_type
        FROM valuations v
        JOIN (
            SELECT company_id, MAX(date) AS max_date
            FROM valuations
            WHERE valuation_usd_billions IS NOT NULL
            GROUP BY company_id
        ) latest
          ON v.company_id = latest.company_id
         AND v.date = latest.max_date
        """
    ).fetchall()
    return {
        r["company_id"]: {
            "value": r["valuation_usd_billions"],
            "date": r["date"],
            "type": r["valuation_type"],
        }
        for r in rows
    }


def _country_name(code: str | None) -> str | None:
    if not code:
        return None
    if code not in COUNTRY_NAMES:
        raise SystemExit(
            f"Unknown country code {code!r}. "
            f"Add it to COUNTRY_NAMES in {Path(__file__).name}."
        )
    return COUNTRY_NAMES[code]


def _serialize_companies(conn: sqlite3.Connection) -> list[dict]:
    latest = _latest_valuations(conn)
    rows = conn.execute("SELECT * FROM companies ORDER BY company_name").fetchall()
    companies: list[dict] = []
    for r in rows:
        cats = [r["category_primary"]]
        if r["category_secondary"]:
            cats.append(r["category_secondary"])
        latest_val = latest.get(r["company_id"])
        companies.append({
            "id": r["company_id"],
            "name": r["company_name"],
            "founded_year": r["founded_year"],
            "hq_country": r["hq_country"],
            "hq_country_name": _country_name(r["hq_country"]),
            "hq_city": r["hq_city"],
            "public_or_private": r["public_or_private"],
            "stock_ticker": r["stock_ticker"],
            "categories": cats,
            "revenue": r["revenue_2025_usd_billions"],
            "profit_loss": r["profit_loss_2025_usd_billions"],
            "company_value": latest_val["value"] if latest_val else None,
            "company_value_date": latest_val["date"] if latest_val else None,
            "company_value_type": latest_val["type"] if latest_val else None,
            "data_confidence": r["data_confidence"],
            "sources": _split_pipes(r["sources"]),
            "ceo": {
                "name": r["ceo_name"],
                "wikipedia_url": r["ceo_wikipedia_url"],
            } if r["ceo_name"] else None,
            "founders": _zip_people(r["founder_names"], r["founder_wikipedia_urls"]),
            "gov_contracts": _split_pipes(r["gov_contracts"]),
            "gov_contract_notes": r["gov_contract_notes"] or "",
            "regulatory_actions": r["regulatory_actions"] or "",
            "notes": r["notes"] or "",
        })
    return companies


def build_payload() -> dict:
    if not DB_PATH.exists():
        raise SystemExit(
            f"Database not found at {DB_PATH}. "
            "Run `python src/gather/csv_to_sqlite.py` first."
        )
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        companies = _serialize_companies(conn)
    finally:
        conn.close()
    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "companies": companies,
    }


def render_site(payload: dict) -> None:
    if not TEMPLATE_PATH.exists():
        raise SystemExit(f"Template not found at {TEMPLATE_PATH}")
    for name in STATIC_FILES:
        if not (SRC_DIR / name).exists():
            raise SystemExit(f"Missing static asset {SRC_DIR / name}")

    DIST_DIR.mkdir(parents=True, exist_ok=True)

    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    if DATA_PLACEHOLDER not in template:
        raise SystemExit(
            f"Template {TEMPLATE_PATH} is missing the {DATA_PLACEHOLDER} placeholder"
        )
    # Escape </script to keep the embedded JSON from ending the <script> block.
    data_json = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    rendered = template.replace(DATA_PLACEHOLDER, data_json)
    (DIST_DIR / "index.html").write_text(rendered, encoding="utf-8")

    for name in STATIC_FILES:
        shutil.copy2(SRC_DIR / name, DIST_DIR / name)


def main() -> None:
    payload = build_payload()
    render_site(payload)
    count = len(payload["companies"])
    with_value = sum(1 for c in payload["companies"] if c["company_value"] is not None)
    print(f"Built {DIST_DIR} — {count} companies ({with_value} with company_value)")


if __name__ == "__main__":
    main()
