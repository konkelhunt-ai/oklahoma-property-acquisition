"""Test service-account write permission without touching acquisition records."""
import json
import os
import sys
import uuid
import gspread
from google.oauth2.service_account import Credentials

SHEET_ID = "1vbgqFm_tygMJ545DbQU8vY_RaJr8IbSQG7_PMqmBNdQ"

def main():
    raw = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not raw:
        sys.exit("Missing GOOGLE_SERVICE_ACCOUNT_JSON")
    credentials = Credentials.from_service_account_info(
        json.loads(raw), scopes=["https://www.googleapis.com/auth/spreadsheets"])
    client = gspread.authorize(credentials)
    spreadsheet = client.open_by_key(SHEET_ID)
    name = "_connection_test_" + uuid.uuid4().hex[:8]
    temporary = None
    try:
        temporary = spreadsheet.add_worksheet(title=name, rows=2, cols=2)
        temporary.update(range_name="A1:B1", values=[["status", "write-verified"]])
        values = temporary.get("A1:B1")
        if values != [["status", "write-verified"]]:
            raise RuntimeError(f"Write verification mismatch: {values!r}")
        print("SUCCESS: Google Sheets write, read-back, and temporary-sheet cleanup authorized.")
    finally:
        if temporary is not None:
            spreadsheet.del_worksheet(temporary)

if __name__ == "__main__":
    main()
