"""Collect Oklahoma County Treasurer county-owned parcels, not historical resale auctions.

This is a secondary Oklahoma-wide source, not a replacement for Tulsa sheriff sales.
Only rows with parcel identifiers and explicit suggested bids are staged.
"""
import json
import re
from datetime import datetime, timezone
from pathlib import Path
import requests
from bs4 import BeautifulSoup

SOURCE = "https://docs.oklahomacounty.org/treasurer/CountyOwnedList.asp"
OUT = Path("output")
OUT.mkdir(exist_ok=True)
PARCEL = re.compile(r"^\d{4}-\d{2}-\d{3}-\d{4}$")
MONEY = re.compile(r"\$?([\d,]+(?:\.\d{2})?)")

def collect():
    resp = requests.get(SOURCE, timeout=45, headers={"User-Agent": "Mozilla/5.0 OklahomaAcquisitionResearch/1.0"})
    resp.raise_for_status()
    (OUT / "oklahoma_county_source.html").write_text(resp.text, encoding="utf-8")
    soup = BeautifulSoup(resp.text, "html.parser")
    rows = []
    seen = set()
    for tr in soup.select("tr"):
        cells = [x.get_text(" ", strip=True) for x in tr.find_all(["td", "th"], recursive=False)]
        joined = " | ".join(cells)
        match = next((PARCEL.fullmatch(x) for x in cells if PARCEL.fullmatch(x)), None)
        if not match:
            continue
        parcel = match.group()
        if parcel in seen:
            continue
        seen.add(parcel)
        if len(cells) < 7 or cells[3] != "N/A":
            continue  # Only unscheduled parcels in this source; never invent auction dates.
        rows.append({"scheduled_sale": cells[3], "initial_bid": cells[4], "suggested_initial_bid": cells[5],
                     "property_description": cells[6], "lead_id": "OKCOUNTY-COUNTYOWNED-" + parcel, "county": "Oklahoma",
                     "auction_type": "County-owned property (commissioners sale)",
                     "case_number": parcel, "sale_date": "",
                     "address": cells[6],
                     "status": "County-owned list; availability unverified",
                     "plaintiff": "", "source_url": SOURCE,
                     "checked_at": datetime.now(timezone.utc).isoformat(),
                     "source_row": joined})
    (OUT / "oklahoma_county_owned_staging.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    if not rows:
        raise RuntimeError("No county-owned parcel rows parsed; original HTML saved for diagnosis")
    print(f"Staged {len(rows)} county-owned parcels for validation. No auction dates or active sale claims inferred.")

if __name__ == "__main__":
    collect()
