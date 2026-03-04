#!/usr/bin/env python3
"""Parse Green Software Foundation CSV data into a bundled JSON file for What-If comparison.

Downloads the GSF Real-Time Cloud dataset, extracts carbon intensity and PUE per region,
applies a fallback chain for carbon intensity columns, injects DigitalOcean regions
manually, and writes the result to app/static/data/cloud_regions.json.

Usage:
    python scripts/build_region_data.py
"""

import csv
import json
import sys
import urllib.request
from pathlib import Path

# GSF Real-Time Cloud CSV URLs (estimates file has the most recent/complete data)
CSV_URLS = [
    "https://raw.githubusercontent.com/Green-Software-Foundation/real-time-cloud/main/Cloud_Region_Metadata_estimate.csv",
    "https://raw.githubusercontent.com/Green-Software-Foundation/real-time-cloud/main/Cloud_Region_Metadata.csv",
]

OUTPUT_PATH = Path(__file__).parent.parent / "app" / "static" / "data" / "cloud_regions.json"

# Carbon intensity column fallback chain (try in order, use first non-empty value)
CI_COLUMNS = [
    "grid-carbon-intensity",
    "grid-carbon-intensity-marginal-consumption-annual",
    "grid-carbon-intensity-average-production-annual",
]

# Provider name normalisation
PROVIDER_MAP = {
    "Amazon Web Services": "AWS",
    "Google Cloud": "GCP",
    "Microsoft Azure": "Azure",
}

# DigitalOcean regions mapped to GSF grid zones.
# Carbon intensity values are populated from GSF data where possible,
# otherwise use reasonable defaults. LON1 uses real-time UK API at runtime.
DO_REGIONS = [
    {"region": "LON1", "location": "London, UK", "grid_zone": "GB"},
    {"region": "FRA1", "location": "Frankfurt, Germany", "grid_zone": "DE"},
    {"region": "AMS3", "location": "Amsterdam, Netherlands", "grid_zone": "NL"},
    {"region": "NYC1", "location": "New York, USA", "grid_zone": "US-NY"},
    {"region": "SFO3", "location": "San Francisco, USA", "grid_zone": "US-CA"},
    {"region": "TOR1", "location": "Toronto, Canada", "grid_zone": "CA-ON"},
    {"region": "SGP1", "location": "Singapore", "grid_zone": "SG"},
    {"region": "BLR1", "location": "Bangalore, India", "grid_zone": "IN"},
    {"region": "SYD1", "location": "Sydney, Australia", "grid_zone": "AU-NSW"},
]

# Default PUE for DigitalOcean (colocation average), except LON1 which uses configured 1.2
DO_PUE_DEFAULT = 1.5
DO_LON1_PUE = 1.2

# Fallback carbon intensity values by grid zone (gCO2eq/kWh, annual averages)
# Used when GSF data doesn't have a matching em-zone-id
GRID_ZONE_FALLBACKS = {
    "GB": 230.0,
    "DE": 350.0,
    "NL": 340.0,
    "US-NY": 280.0,
    "US-CA": 210.0,
    "CA-ON": 30.0,
    "SG": 410.0,
    "IN": 630.0,
    "AU-NSW": 660.0,
}


def fetch_csv(url: str) -> list[dict]:
    """Download and parse a CSV file from a URL."""
    print(f"Fetching {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "greenscope-build/1.0"})
    with urllib.request.urlopen(req) as response:
        text = response.read().decode("utf-8")
    reader = csv.DictReader(text.splitlines())
    return list(reader)


def parse_float(value: str | None) -> float | None:
    """Parse a string to float, returning None for empty/invalid values."""
    if not value or value.strip() == "":
        return None
    try:
        return float(value.strip())
    except ValueError:
        return None


def get_carbon_intensity(row: dict) -> float | None:
    """Apply fallback chain to extract carbon intensity from a CSV row."""
    for col in CI_COLUMNS:
        val = parse_float(row.get(col))
        if val is not None and val > 0:
            return round(val, 1)
    return None


def process_gsf_data(rows: list[dict]) -> dict[tuple[str, str], dict]:
    """Process GSF CSV rows into a dict keyed by (provider, region).

    For regions with multiple years, keeps the most recent year's data.
    """
    regions: dict[tuple[str, str], dict] = {}

    for row in rows:
        provider_raw = row.get("cloud-provider", "").strip()
        provider = PROVIDER_MAP.get(provider_raw)
        if not provider:
            continue

        region = row.get("cloud-region", "").strip()
        if not region:
            continue

        ci = get_carbon_intensity(row)
        if ci is None:
            continue

        pue = parse_float(row.get("power-usage-effectiveness"))
        location = row.get("location", "").strip()
        year = parse_float(row.get("year"))
        em_zone = row.get("em-zone-id", "").strip()

        key = (provider, region)
        existing = regions.get(key)

        # Keep the most recent year's data
        if existing and year and existing.get("_year") and year < existing["_year"]:
            continue

        regions[key] = {
            "provider": provider,
            "region": region,
            "location": location,
            "carbon_intensity": ci,
            "pue": round(pue, 3) if pue else None,
            "em_zone_id": em_zone,
            "_year": year,
        }

    return regions


def find_do_intensity(gsf_regions: dict[tuple[str, str], dict], grid_zone: str) -> float | None:
    """Find carbon intensity for a DO region by matching its grid zone to GSF em-zone-id."""
    # Search all GSF regions for a matching em-zone-id
    for entry in gsf_regions.values():
        if entry.get("em_zone_id") == grid_zone:
            return entry["carbon_intensity"]
    return None


def build_do_regions(gsf_regions: dict[tuple[str, str], dict]) -> list[dict]:
    """Build DigitalOcean region entries using GSF data where available."""
    do_entries = []
    for do_region in DO_REGIONS:
        grid_zone = do_region["grid_zone"]

        # Try to find CI from GSF data
        ci = find_do_intensity(gsf_regions, grid_zone)
        if ci is None:
            ci = GRID_ZONE_FALLBACKS.get(grid_zone)
        if ci is None:
            print(f"  Warning: no carbon intensity for DO {do_region['region']} ({grid_zone}), skipping")
            continue

        pue = DO_LON1_PUE if do_region["region"] == "LON1" else DO_PUE_DEFAULT

        do_entries.append(
            {
                "provider": "DO",
                "region": do_region["region"],
                "location": do_region["location"],
                "carbon_intensity": ci,
                "pue": pue,
            }
        )

    return do_entries


def main():
    # Fetch and combine CSV data from both files
    all_rows: list[dict] = []
    for url in CSV_URLS:
        try:
            rows = fetch_csv(url)
            print(f"  Loaded {len(rows)} rows")
            all_rows.extend(rows)
        except Exception as e:
            print(f"  Warning: failed to fetch {url}: {e}")

    if not all_rows:
        print("Error: no CSV data loaded")
        sys.exit(1)

    # Process GSF data
    gsf_regions = process_gsf_data(all_rows)
    print(f"Processed {len(gsf_regions)} unique cloud regions from GSF data")

    # Build output list from GSF regions
    output = []
    for entry in gsf_regions.values():
        output.append(
            {
                "provider": entry["provider"],
                "region": entry["region"],
                "location": entry["location"],
                "carbon_intensity": entry["carbon_intensity"],
                "pue": entry["pue"],
            }
        )

    # Add DigitalOcean regions
    do_entries = build_do_regions(gsf_regions)
    output.extend(do_entries)
    print(f"Added {len(do_entries)} DigitalOcean regions")

    # Sort by provider then region
    output.sort(key=lambda r: (r["provider"], r["region"]))

    # Write JSON
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2)

    print(f"Wrote {len(output)} regions to {OUTPUT_PATH}")

    # Summary by provider
    from collections import Counter

    counts = Counter(r["provider"] for r in output)
    for provider, count in sorted(counts.items()):
        print(f"  {provider}: {count} regions")


if __name__ == "__main__":
    main()
