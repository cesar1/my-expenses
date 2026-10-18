#!/usr/bin/env python3
"""Regenerate the BLS-sourced figures in app.SAMPLE_EXPENSES.

Dev-only helper -- never imported by app.py. The landing page reads a baked-in
constant so it has no runtime network dependency.

Usage:
    python scripts/refresh_sample_costs.py

The BLS API needs no key for this many series (keyless callers get 25 series per
request and 25 requests per day). The two Census housing figures do need a free
key, so they are printed as a reminder to transcribe by hand.
"""

import json
import urllib.request

BLS_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
YEAR = "2024"

# Consumer Expenditure Survey, all consumer units. Series ID is
# CXU<item_code>LB0101M; item codes come from
# https://download.bls.gov/pub/time.series/cx/cx.item
# (that host 403s without a descriptive User-Agent).
SERIES = {
    "CXUFOODHOMELB0101M": ("Groceries", "Food"),
    "CXUFOODAWAYLB0101M": ("Dining out", "Food"),
    "CXUGASFUELLB0101M": ("Gasoline", "Transport"),
    "CXU500110LB0101M": ("Car insurance", "Transport"),
    "CXU260112LB0101M": ("Electricity", "Utilities"),
    "CXU270102LB0101M": ("Cell phone", "Utilities"),
    "CXUWATERLB0101M": ("Water & sewer", "Utilities"),
    "CXU690114LB0101M": ("Internet", "Utilities"),
    "CXU260212LB0101M": ("Natural gas", "Utilities"),
}

# No API publishes these; they are advertised subscription prices.
ADVERTISED = [
    ("Netflix (Standard)", 17.99, "Entertainment"),
    ("Spotify Premium", 11.99, "Entertainment"),
]


def fetch():
    body = json.dumps(
        {"seriesid": list(SERIES), "startyear": YEAR, "endyear": YEAR}
    ).encode()
    req = urllib.request.Request(
        BLS_URL, data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        payload = json.load(resp)

    if payload.get("status") != "REQUEST_SUCCEEDED":
        raise SystemExit(f"BLS request failed: {payload.get('status')} {payload.get('message')}")

    for note in payload.get("message", []):
        if "does not exist" in note or "No Data" in note:
            print(f"  !! {note}")

    results = {}
    for series in payload["Results"]["series"]:
        rows = [r for r in series["data"] if r["value"] not in ("-", "")]
        if rows:
            results[series["seriesID"]] = float(rows[0]["value"])
    return results


def main():
    annual = fetch()
    print(f"\nBLS Consumer Expenditure Survey {YEAR} (annual per consumer unit / 12):\n")
    for series_id, (label, category) in SERIES.items():
        if series_id not in annual:
            print(f"  {label:<28} MISSING ({series_id})")
            continue
        monthly = round(annual[series_id] / 12, 2)
        print(f'  {{"description": "{label}", "amount": {monthly}, "category": "{category}"}},')

    print("\nAdvertised prices (update by hand):")
    for label, amount, category in ADVERTISED:
        print(f'  {{"description": "{label}", "amount": {amount}, "category": "{category}"}},')

    print(
        "\nHousing rows need the Census ACS 1-year estimates (free API key required).\n"
        "  Source: https://www.census.gov/newsroom/press-releases/2025/acs-1-year-estimates.html\n"
        "  Rent     = median gross rent MINUS an estimated renter utility allowance\n"
        "  Mortgage = median monthly owner costs w/ mortgage MINUS estimated utilities\n"
        "  Both Census figures bundle utilities, so subtracting avoids double-counting\n"
        "  the utility rows above. Do NOT use the CE rent series: it averages\n"
        "  homeowners paying $0 rent into the mean."
    )


if __name__ == "__main__":
    main()
