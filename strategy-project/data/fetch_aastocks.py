#!/usr/bin/env python3
"""Fetch HK IPO data from AAStocks Listed IPO page.

Scrapes the paginated AAStocks listed IPO table for:
  - ipo_info:  listing_date, ipo_price (Offer Price), public_subscription_multiple,
               one_lot_success_rate
  - grey_market: grey_change_pct (debut day change %, proxy for grey market)

Fields NOT available on AAStocks (require HKEX prospectus):
  offer_price_low, offer_price_high, sponsor, industry
  grey_market_date, grey_close, premium_to_ipo_price

Output:
  data/external/ipo_info.csv   — merged with ipo_info_template.csv
  data/external/grey_market.csv — merged with grey_market_template.csv
"""

from __future__ import annotations

import argparse
import csv
import re
from datetime import date
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DATA_DIR = Path(__file__).resolve().parent
EXTERNAL_DIR = DATA_DIR / "external"
RAW_DIR = DATA_DIR / "raw"
AASTOCKS_URL = "https://www.aastocks.com/en/stocks/market/ipo/listedipo.aspx"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
}

IPO_FIELDS = [
    "symbol", "listing_date", "ipo_price", "offer_price_low",
    "offer_price_high", "sponsor", "industry",
    "public_subscription_multiple", "one_lot_success_rate",
    "source_url", "source_note", "collected_at",
]

GREY_FIELDS = [
    "symbol", "grey_market_date", "grey_close", "grey_change_pct",
    "premium_to_ipo_price", "source_url", "source_note", "collected_at",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def clean_html(cell: str) -> str:
    """Strip HTML tags and whitespace from a table cell."""
    text = re.sub(r"<[^>]+>", " ", cell)
    text = text.replace("&nbsp;", " ")
    return re.sub(r"\s+", " ", text).strip()


def fetch_page(page: int) -> str:
    """Fetch one page of the AAStocks listed IPO table (sorted by listing date ascending)."""
    url = f"{AASTOCKS_URL}?s=3&o=0&page={page}"
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.text


def parse_page(html: str) -> list[dict[str, str]]:
    """Parse IPO rows from an AAStocks HTML page.

    Table columns (0-indexed):
      0: expand icon
      1: name + symbol link
      2: listing date
      3: lot size
      4: market cap (B)
      5: offer price     ← ipo_price
      6: listing price
      7: over-sub rate   ← public_subscription_multiple
      8: applied lots for 1 lot
      9: one-lot success rate
     10: last price
     11: % chg on debut  ← grey_change_pct
     12: acc % chg
    """
    rows = re.findall(r"<tr>(.*?)</tr>", html, re.DOTALL)
    results = []

    for row in rows:
        # Only rows containing a symbol link
        if "symbol=" not in row:
            continue

        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL)
        if len(cells) < 12:
            continue

        symbol_match = re.search(r"symbol=(\d{5})", cells[1])
        if not symbol_match:
            continue

        symbol = f"{symbol_match.group(1)}.HK"
        offer_price = clean_html(cells[5])
        over_sub = clean_html(cells[7])
        one_lot_rate = clean_html(cells[9])
        listing_date_raw = clean_html(cells[2])
        debut_change = clean_html(cells[11])

        # Reformat listing date from YYYY/MM/DD if present
        listing_date = listing_date_raw.replace("/", "-") if listing_date_raw else ""

        # Skip rows without an offer price
        if not offer_price or offer_price in ("-", "N/A", ""):
            continue

        results.append({
            "symbol": symbol,
            "listing_date": listing_date,
            "ipo_price": offer_price,
            "public_subscription_multiple": over_sub,
            "one_lot_success_rate": one_lot_rate,
            "grey_change_pct": debut_change,
        })

    return results


def load_template(path: Path, fieldnames: list[str]) -> list[dict[str, str]]:
    """Load a CSV template, returning rows as dicts (all values stripped)."""
    if path.exists():
        with open(path, "r", encoding="utf-8") as fh:
            return [
                {k: v.strip() for k, v in row.items()}
                for row in csv.DictReader(fh)
            ]
    return []


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    """Write rows to CSV, only including known fieldnames."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(
        description="Scrape AAStocks listed IPO data and merge into external CSV files."
    )
    parser.add_argument("--max-pages", type=int, default=20,
                        help="Maximum pages to scrape (default: 20)")
    parser.add_argument("--ipo-template", type=Path,
                        default=EXTERNAL_DIR / "ipo_info_template.csv")
    parser.add_argument("--grey-template", type=Path,
                        default=EXTERNAL_DIR / "grey_market_template.csv")
    parser.add_argument("--dry-run", action="store_true",
                        help="Scrape only, do not write files")
    args = parser.parse_args()

    # ------------------------------------------------------------------
    # 1. Scrape AAStocks
    # ------------------------------------------------------------------
    all_data: dict[str, dict[str, str]] = {}
    total_symbols = 0

    for page in range(1, args.max_pages + 1):
        try:
            html = fetch_page(page)
        except requests.RequestException as exc:
            print(f"Page {page}: request failed — {exc}")
            break

        page_data = parse_page(html)
        if not page_data:
            print(f"Page {page}: no data rows — stopping")
            break

        for item in page_data:
            if item["symbol"] not in all_data:
                all_data[item["symbol"]] = item

        total_symbols += len(page_data)
        print(f"Page {page}: {len(page_data)} symbols")

    print(f"\nTotal scraped: {len(all_data)} unique symbols")

    # ------------------------------------------------------------------
    # 2. Merge into ipo_info_template.csv (in-place)
    # ------------------------------------------------------------------
    ipo_rows = load_template(args.ipo_template, IPO_FIELDS)
    today = date.today().isoformat()
    updated = 0

    for row in ipo_rows:
        symbol = row["symbol"]
        if symbol not in all_data:
            continue

        src = all_data[symbol]
        for field in ["listing_date", "ipo_price",
                       "public_subscription_multiple", "one_lot_success_rate"]:
            if src.get(field) and not row[field].strip():
                row[field] = src[field]

        if not row["source_url"].strip():
            row["source_url"] = AASTOCKS_URL
        if not row["source_note"].strip():
            row["source_note"] = "AAStocks Listed IPO page"
        if not row["collected_at"].strip():
            row["collected_at"] = today

        updated += 1

    if not args.dry_run:
        write_csv(args.ipo_template, IPO_FIELDS, ipo_rows)
    print(f"ipo_info: {updated}/{len(ipo_rows)} rows updated")

    # ------------------------------------------------------------------
    # 3. Merge into grey_market_template.csv (in-place)
    # ------------------------------------------------------------------
    grey_rows = load_template(args.grey_template, GREY_FIELDS)
    updated = 0

    for row in grey_rows:
        symbol = row["symbol"]
        if symbol not in all_data:
            continue

        src = all_data[symbol]
        if src.get("grey_change_pct") and not row["grey_change_pct"].strip():
            row["grey_change_pct"] = src["grey_change_pct"]

        if not row["source_url"].strip():
            row["source_url"] = AASTOCKS_URL
        if not row["source_note"].strip():
            row["source_note"] = "AAStocks Listed IPO debut change (proxy for grey market)"
        if not row["collected_at"].strip():
            row["collected_at"] = today

        updated += 1

    if not args.dry_run:
        write_csv(args.grey_template, GREY_FIELDS, grey_rows)
    print(f"grey_market: {updated}/{len(grey_rows)} rows updated")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
