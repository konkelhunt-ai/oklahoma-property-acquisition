"""Screen every assessor-enriched parcel and upsert a reusable GIS Screening tab.

Rules are *review flags*, not property valuations or zoning/buildability determinations.
Preserves Research Status and manual edits in the existing screening tab.
A county adapter only has to populate the common Parcel Enrichment schema.
"""
import json
import os
import re
from collections import Counter
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials

SHEET_ID = "1vbgqFm_tygMJ545DbQU8vY_RaJr8IbSQG7_PMqmBNdQ"
HEADERS = [
    "Lead ID", "Parcel ID", "GIS Match", "Assessor Location", "City", "Acres",
    "Assessor Owner", "Legal Description", "Suggested Initial Bid", "Screening Flag",
    "Reason", "Next Research Action", "GIS Source", "Treasurer Source", "Research Status",
]
SPECIAL = re.compile(r"\b(COMMON AREAS?|DRAINAGE|DETENTION|RESERVE(?:D)?|RETENTION)\b", re.I)
STRIP = re.compile(
    r"\b(EASEMENT|RIGHT OF WAY|R/W|ROW|STRIP|(?:\d+(?:\.\d+)?\s*FT\s*WIDE)|"
    r"(?:WLY|ELY|NLY|SLY)\s+\d+(?:\.\d+)?\s*FT)\b",
    re.I,
)

def classify(match_status, location, legal, acres):
    """Return flag, reason, next step; a flag is never a final investment verdict."""
    legal = legal or ""
    location = location or ""
    try:
        acreage = float(acres)
    except (ValueError, TypeError):
        acreage = None
    if match_status != "Exact parcel match":
        return ("UNMATCHED", "No verified exact assessor parcel match",
                "Reconcile parcel identifier and legal description with county assessor")
    if SPECIAL.search(legal) or re.search(r"\bCOMMON AREA\b", location, re.I):
        return ("SPECIAL-USE RISK", "Source suggests common or restricted-use land",
                "Investigate dedication, restrictions, title and permitted uses")
    if STRIP.search(legal):
        return ("STRIP / ACCESS RISK", "Legal wording suggests a narrow strip or access restriction",
                "Check plat, survey, width, road frontage, access rights and setbacks")
    if acreage is not None and acreage < 0.15:
        return ("SMALL PARCEL", "Assessor acreage is under 0.15 acres; feasibility unknown",
                "Confirm dimensions, frontage, utilities, setbacks, zoning and nearby owners")
    return ("RESEARCH CANDIDATE", "Parcel matched; suitability, title and availability not established",
            "Check map, zoning, utilities, access, tax status, title and county availability")

def row_dicts(sheet, required):
    rows = sheet.get_all_values()
    if not rows:
        raise RuntimeError(f"{sheet.title} has no header")
    headers = rows[0]
    missing = set(required) - set(headers)
    if missing:
        raise RuntimeError(f"{sheet.title} missing required columns: {sorted(missing)}")
    return [{h: (r[i] if i < len(r) else "") for i, h in enumerate(headers)}
            for r in rows[1:] if r and r[0]]

def main():
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not raw:
        raise RuntimeError("Google service account secret missing")
    creds = Credentials.from_service_account_info(
        json.loads(raw), scopes=["https://www.googleapis.com/auth/spreadsheets"])
    book = gspread.authorize(creds).open_by_key(SHEET_ID)
    gis = row_dicts(book.worksheet("Parcel Enrichment"),
                    ["Lead ID", "Parcel ID", "Match Status", "Situs / Location",
                     "Situs City", "Parcel Acres", "Assessor Owner Name",
                     "Legal Description", "Assessor Source"])
    county = row_dicts(book.worksheet("County-Owned Leads"),
                      ["Lead ID", "Suggested Initial Bid", "Source URL"])
    bids = {r["Lead ID"]: r for r in county}
    try:
        screen = book.worksheet("GIS Screening")
    except gspread.WorksheetNotFound:
        screen = book.add_worksheet(title="GIS Screening", rows=1000, cols=len(HEADERS))
        screen.update(range_name="A1:O1", values=[HEADERS])
    old = screen.get_all_values()
    if not old or old[0][:len(HEADERS)] != HEADERS:
        raise RuntimeError("GIS Screening headers differ; refusing changes")
    positions = {r[0]: (i + 2, r) for i, r in enumerate(old[1:]) if r and r[0]}
    updates, inserts, flags = [], [], Counter()
    for rec in gis:
        key = rec["Lead ID"]
        matched_bid = bids.get(key, {})
        flag, reason, next_action = classify(rec["Match Status"],
                    rec.get("Situs / Location", ""), rec.get("Legal Description", ""),
                    rec.get("Parcel Acres", ""))
        flags[flag] += 1
        incoming = [
            key, rec["Parcel ID"], rec["Match Status"], rec["Situs / Location"],
            rec["Situs City"], rec["Parcel Acres"], rec["Assessor Owner Name"],
            rec["Legal Description"], matched_bid.get("Suggested Initial Bid", ""),
            flag, reason, next_action, rec["Assessor Source"],
            matched_bid.get("Source URL", ""),
        ]
        if key in positions:
            row_no, previous = positions[key]
            # A:M are computed source data; N is source link and O is analyst research status.
            # Preserve N when no refreshed source available. Never change O.
            if not incoming[13] and len(previous) > 13:
                incoming[13] = previous[13]
            if incoming != (previous + [""] * 14)[:14]:
                updates.append({"range": f"'GIS Screening'!A{row_no}:N{row_no}",
                                "values": [incoming]})
        else:
            inserts.append(incoming + ["Not verified"])
    if updates:
        for i in range(0, len(updates), 100):
            book.values_batch_update({"valueInputOption": "RAW",
                                      "data": updates[i:i+100]})
    if inserts:
        screen.append_rows(inserts, value_input_option="RAW", table_range="A:O")
    Path("output").mkdir(exist_ok=True)
    Path("output/gis_screening_summary.json").write_text(
        json.dumps({"total": len(gis), "flags": dict(flags), "new": len(inserts),
                    "refreshed": len(updates)}, indent=2), encoding="utf-8")
    print(f"Screened {len(gis)} parcels: {dict(flags)}; {len(inserts)} added, {len(updates)} refreshed.")
    print("No property was declared buildable or available; manual research statuses preserved.")

if __name__ == "__main__":
    main()
