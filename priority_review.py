"""Maintain a focused candidate-review table from the county-independent GIS Screening tab.

Only preliminary research candidates are included. Never claims a property is buildable,
available, or a profitable acquisition. Preserves analyst disposition and notes across runs.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials

SHEET_ID = "1vbgqFm_tygMJ545DbQU8vY_RaJr8IbSQG7_PMqmBNdQ"
TAB = "Priority Review"
HEADERS = [
    "Lead ID", "Parcel ID", "County", "City", "GIS Location", "Acres",
    "Suggested Initial Bid", "Legal Description", "Screening Flag",
    "Required Due Diligence", "Assessor Source", "County Sale Source",
    "Current Review Status", "Analyst Notes", "Assigned To", "Last Updated"
]

def main():
    secret = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not secret:
        raise RuntimeError("Missing GOOGLE_SERVICE_ACCOUNT_JSON")
    credentials = Credentials.from_service_account_info(
        json.loads(secret), scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    book = gspread.authorize(credentials).open_by_key(SHEET_ID)
    source = book.worksheet("GIS Screening").get_all_values()
    if not source:
        raise RuntimeError("GIS Screening is empty")
    col = {name: i for i, name in enumerate(source[0])}
    expected = ["Lead ID", "Parcel ID", "GIS Match", "Assessor Location", "City",
                "Acres", "Legal Description", "Suggested Initial Bid", "Screening Flag",
                "GIS Source", "Treasurer Source"]
    if any(x not in col for x in expected):
        raise RuntimeError("GIS Screening header mismatch")
    def value(row, key):
        i = col[key]
        return row[i].strip() if i < len(row) else ""
    try:
        tab = book.worksheet(TAB)
    except gspread.WorksheetNotFound:
        tab = book.add_worksheet(title=TAB, rows=1000, cols=len(HEADERS))
        tab.update(range_name="A1:P1", values=[HEADERS])
    old = tab.get_all_values()
    if not old or old[0][:len(HEADERS)] != HEADERS:
        raise RuntimeError("Priority Review header mismatch")
    indexed = {r[0]: (i + 2, r) for i, r in enumerate(old[1:]) if r and r[0]}
    updates, inserts, eligible = [], [], set()
    stamp = datetime.now(timezone.utc).isoformat()
    for record in source[1:]:
        if not record or value(record, "Screening Flag") != "RESEARCH CANDIDATE":
            continue
        key = value(record, "Lead ID")
        if not key:
            continue
        eligible.add(key)
        current = indexed.get(key)
        previous = current[1] if current else []
        def oldval(i, default):
            return previous[i] if i < len(previous) and previous[i] else default
        row = [
            key, value(record, "Parcel ID"), "Oklahoma", value(record, "City"),
            value(record, "Assessor Location"), value(record, "Acres"),
            value(record, "Suggested Initial Bid"), value(record, "Legal Description"),
            value(record, "Screening Flag"),
            "Verify GIS shape/frontage; zoning; road access; improvements/utilities; liens/title; county sale availability; closing rules; value comps",
            value(record, "GIS Source"), value(record, "Treasurer Source"),
            oldval(12, "Not reviewed"), oldval(13, ""), oldval(14, ""), stamp
        ]
        if current:
            # Only refresh source-derived columns A:L and date P. Preserve human columns M:O.
            n = current[0]
            updates.extend([
                {"range": f"'{TAB}'!A{n}:L{n}", "values": [row[:12]]},
                {"range": f"'{TAB}'!P{n}", "values": [[stamp]]},
            ])
        else:
            inserts.append(row)
    if updates:
        for i in range(0, len(updates), 100):
            book.values_batch_update({"valueInputOption": "RAW", "data": updates[i:i + 100]})
    if inserts:
        tab.append_rows(inserts, value_input_option="RAW", table_range="A:P")
    # Previously listed candidates which no longer qualify remain visible for audit and
    # analyst notes, with an explicit status flag rather than being silently deleted.
    dropped = 0
    for key, (row_number, oldrow) in indexed.items():
        if key not in eligible and (len(oldrow) <= 12 or oldrow[12] != "Screening changed - recheck"):
            tab.update(range_name=f"M{row_number}", values=[["Screening changed - recheck"]])
            dropped += 1
    Path("output").mkdir(exist_ok=True)
    Path("output/priority_review_summary.json").write_text(
        json.dumps({"candidates": len(eligible), "inserted": len(inserts),
                    "previous_candidates_flagged": dropped}, indent=2)
    )
    print(f"Priority Review: {len(eligible)} research candidates, {len(inserts)} new, {dropped} previously flagged.")

if __name__ == "__main__":
    main()
