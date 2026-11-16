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
    # Mirror new leads into the existing Properties pipeline, without changing
    # existing deal stages, assignments, contact research, or other human edits.
    master = book.worksheet("Properties")
    master_values = master.get_all_values()
    required = ["Lead ID", "County", "Parcel ID", "Property Type", "Source Type", "Source URL", "Auction Status", "Minimum Bid", "Last Verified", "Notes"]
    headers = master_values[0] if master_values else []
    if any(h not in headers for h in required):
        raise RuntimeError("Properties header changed; county-owned source synced, master mirror blocked")
    master_ids = {r[0] for r in master_values[1:] if r}
    new_master = []
    for r in records:
        if r["lead_id"] in master_ids:
            continue
        values = {
            "Lead ID": r["lead_id"], "County": r["county"],
            "Parcel ID": r["case_number"], "Property Type": "Unverified",
            "Source Type": "County-owned / tax resale", "Source URL": r["source_url"],
            "Auction Status": "County-owned list; availability unverified",
            "Minimum Bid": r["suggested_initial_bid"], "Last Verified": r["checked_at"],
            "Notes": "Property description: " + r["property_description"] + ". Verify title, availability, and bidding process before outreach."
        }
        new_master.append([values.get(h, "") for h in headers])
    if new_master:
        master.append_rows(new_master, value_input_option="RAW", table_range="A:U")
    print(f"Mirrored {len(new_master)} new county-owned leads into Properties; existing rows untouched.")
    print(f"County-owned leads: {len(inserts)} new, {len(updates)} updated. Research Notes preserved.")

if __name__ == "__main__":
    main()
