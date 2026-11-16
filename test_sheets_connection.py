"""Verify GitHub secret, Sheets API access, and expected Auctions headers without writing data."""
import json
import os
import sys
import gspread
from google.oauth2.service_account import Credentials

SHEET_ID = "1vbgqFm_tygMJ545DbQU8vY_RaJr8IbSQG7_PMqmBNdQ"
EXPECTED = ["Lead ID", "County", "Auction Type", "Case Number", "Sale Date", "Location", "Status", "Plaintiff", "Attorney", "Source URL", "Last Checked"]

def main():
    raw = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    if not raw:
        sys.exit("FAILED: GitHub secret GOOGLE_SERVICE_ACCOUNT_JSON is missing or empty.")
    try:
        info = json.loads(raw)
        creds = Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
        client = gspread.authorize(creds)
        sheet = client.open_by_key(SHEET_ID).worksheet("Auctions")
        headers = sheet.row_values(1)
        if headers[:len(EXPECTED)] != EXPECTED:
            sys.exit("FAILED: Auctions tab headers do not match the sync script.")
        print("SUCCESS: Google Sheets credentials and Auctions tab access verified. No data was changed.")
    except Exception as exc:
        print(f"FAILED: {type(exc).__name__}: {exc}")
        sys.exit(1)

if __name__ == "__main__":
    main()
