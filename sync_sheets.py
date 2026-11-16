"""Upsert collected auction records into the existing Google Sheets master database.

Requires GOOGLE_SERVICE_ACCOUNT_JSON secret; fails closed if absent.
Never overwrites analyst-managed fields or marks disappeared listings sold.
"""
import json
import os
from pathlib import Path
import gspread
from google.oauth2.service_account import Credentials

SPREADSHEET_ID = "1vbgqFm_tygMJ545DbQU8vY_RaJr8IbSQG7_PMqmBNdQ"
HEADERS = ["Lead ID", "County", "Auction Type", "Case Number", "Sale Date", "Location", "Status", "Plaintiff", "Attorney", "Source URL", "Last Checked"]
COLLECTED = Path(os.environ.get("COLLECTED_JSON", "output/creek_sheriff.json"))

def main():
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not raw:
        raise RuntimeError("Missing GOOGLE_SERVICE_ACCOUNT_JSON secret. No sheet writes performed.")
    credentials = Credentials.from_service_account_info(
        json.loads(raw), scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    gc = gspread.authorize(credentials)
    spreadsheet = gc.open_by_key(SPREADSHEET_ID)
    sheet = spreadsheet.worksheet("Auctions")
    rows = sheet.get_all_values()
    if not rows or rows[0][:len(HEADERS)] != HEADERS:
        raise RuntimeError("Unexpected Auctions headers; refusing to change sheet.")
    existing = {row[0]: i + 1 for i, row in enumerate(rows[1:], start=1) if row and row[0]}
    incoming = json.loads(COLLECTED.read_text(encoding="utf-8"))
    if not incoming:
        raise RuntimeError("Empty collector output; refusing to sync.")
    inserts = []
    updates = []
    for rec in incoming:
        key = rec["lead_id"]
        # Preserve manual Attorney field (column I) when updating existing rows.
        current = rows[existing[key] - 1] if key in existing else []
        attorney = current[8] if len(current) > 8 else ""
        row = [
            key, rec["county"], "Sheriff foreclosure", rec["case_number"],
            rec["sale_date"], rec["address"], rec["status"], rec["plaintiff"],
            attorney, rec["source_url"], rec["checked_at"],
        ]
        if key in existing:
            updates.append((existing[key], row))
        else:
            inserts.append(row)
    # Batch API requests for efficiency; update only A:H and J:K on existing rows.
    requests = []
    for row_number, row in updates:
        requests.append({"range": f"Auctions!A{row_number}:H{row_number}", "values": [row[:8]]})
        requests.append({"range": f"Auctions!J{row_number}:K{row_number}", "values": [row[9:11]]})
    if requests:
        spreadsheet.values_batch_update({"valueInputOption": "RAW", "data": requests})
    if inserts:
        sheet.append_rows(inserts, value_input_option="RAW", table_range="A:K")
    print(f"Synced {len(incoming)} auction records: {len(inserts)} new, {len(updates)} existing updated.")

if __name__ == "__main__":
    main()
