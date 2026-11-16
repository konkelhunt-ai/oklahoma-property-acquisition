"""Upsert Oklahoma County county-owned leads into a separate tab, preserving Auctions."""
import json
import os
from pathlib import Path
import gspread
from google.oauth2.service_account import Credentials

SHEET_ID = "1vbgqFm_tygMJ545DbQU8vY_RaJr8IbSQG7_PMqmBNdQ"
TAB = "County-Owned Leads"
HEADERS = ["Lead ID", "County", "Parcel ID", "Property Description", "Scheduled Sale", "Initial Bid", "Suggested Initial Bid", "Status", "Source URL", "Last Checked", "Research Notes"]

def main():
    records = json.loads(Path("output/oklahoma_county_owned_staging.json").read_text())
    if not records or len({r["lead_id"] for r in records}) != len(records):
        raise RuntimeError("Empty or duplicate county-owned source; no writes")
    raw = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not raw:
        raise RuntimeError("Missing Google secret")
    creds = Credentials.from_service_account_info(json.loads(raw), scopes=["https://www.googleapis.com/auth/spreadsheets"])
    book = gspread.authorize(creds).open_by_key(SHEET_ID)
    try:
        sheet = book.worksheet(TAB)
    except gspread.WorksheetNotFound:
        sheet = book.add_worksheet(title=TAB, rows=500, cols=len(HEADERS))
        sheet.update(range_name="A1:K1", values=[HEADERS])
    existing = sheet.get_all_values()
    if not existing or existing[0][:len(HEADERS)] != HEADERS:
        raise RuntimeError("Unexpected County-Owned Leads header; refusing changes")
    indexed = {row[0]: (i + 2, row) for i, row in enumerate(existing[1:]) if row and row[0]}
    updates, inserts = [], []
    for r in records:
        old = indexed.get(r["lead_id"])
        notes = old[1][10] if old and len(old[1]) > 10 else ""
        row = [r["lead_id"], r["county"], r["case_number"], r["property_description"],
               r["scheduled_sale"], r["initial_bid"], r["suggested_initial_bid"],
               r["status"], r["source_url"], r["checked_at"], notes]
        if old:
            updates.append({"range": f"'{TAB}'!A{old[0]}:J{old[0]}", "values": [row[:10]]})
        else:
            inserts.append(row)
    if updates:
        book.values_batch_update({"valueInputOption": "RAW", "data": updates})
    if inserts:
        sheet.append_rows(inserts, value_input_option="RAW", table_range="A:K")
    print(f"County-owned leads: {len(inserts)} new, {len(updates)} updated. Research Notes preserved.")

if __name__ == "__main__":
    main()
