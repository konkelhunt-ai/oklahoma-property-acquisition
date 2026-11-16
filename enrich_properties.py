"""Create a county-independent enrichment queue from the master Properties sheet.

No inferred street addresses, owners, valuations, or investment scores are written.
County adapters can later add verified assessor/tax/recorder fields.
"""
import json
import os
import re
from datetime import datetime, timezone
import gspread
from google.oauth2.service_account import Credentials

SHEET_ID = "1vbgqFm_tygMJ545DbQU8vY_RaJr8IbSQG7_PMqmBNdQ"
HEADERS = ["Lead ID","County","Parcel ID","Research Status","Address Status","Assessor Lookup","Treasurer Lookup","Research Priority","Research Checklist","Last Reviewed"]
COUNTY_SOURCES = {
    "Oklahoma": {
        "assessor": "https://www.oklahomacounty.org/elected-offices/assessor",
        "treasurer": "https://docs.oklahomacounty.org/treasurer/CountyOwnedList.asp",
    },
}
def sources(county):
    return COUNTY_SOURCES.get(county, {"assessor": "", "treasurer": ""})

def main():
    raw = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
    creds = Credentials.from_service_account_info(json.loads(raw), scopes=["https://www.googleapis.com/auth/spreadsheets"])
    book = gspread.authorize(creds).open_by_key(SHEET_ID)
    master = book.worksheet("Properties")
    values = master.get_all_values()
    if not values:
        raise RuntimeError("Properties has no header")
    columns = {name: i for i, name in enumerate(values[0])}
    required = ["Lead ID","County","Parcel ID","Street Address","Property Type","Owner Name"]
    if any(x not in columns for x in required):
        raise RuntimeError("Properties header mismatch")
    def cell(row, name):
        i = columns[name]
        return row[i].strip() if i < len(row) else ""
    try:
        sheet = book.worksheet("Enrichment Queue")
    except gspread.WorksheetNotFound:
        sheet = book.add_worksheet(title="Enrichment Queue", rows=1000, cols=len(HEADERS))
        sheet.update(range_name="A1:J1", values=[HEADERS])
    existing = sheet.get_all_values()
    if not existing or existing[0][:len(HEADERS)] != HEADERS:
        raise RuntimeError("Enrichment Queue header mismatch; refusing overwrite")
    indexed = {r[0]: (n+2,r) for n,r in enumerate(existing[1:]) if r and r[0]}
    inserts, updates = [], []
    now = datetime.now(timezone.utc).date().isoformat()
    for row in values[1:]:
        lead = cell(row, "Lead ID")
        if not lead:
            continue
        county = cell(row, "County")
        parcel = cell(row, "Parcel ID")
        address = cell(row, "Street Address")
        owner = cell(row, "Owner Name")
        prop_type = cell(row, "Property Type")
        lookup = sources(county)
        # Review queue prioritizes missing address and unknown property type.
        priority = "HIGH - identify parcel" if not address or prop_type.lower() in ("", "unverified") else "NORMAL"
        checklist = "Confirm parcel on assessor; verify physical location, legal description, lot size, property class, owner; inspect access and liens; verify current availability"
        proposed = [lead,county,parcel,"Needs official assessor verification",
                    "Verified address present" if address else "Missing / do not infer",
                    lookup["assessor"],lookup["treasurer"],priority,checklist,now]
        old = indexed.get(lead)
        if old:
            # Preserve manually edited status, checklist, and review date.
            previous = old[1]
            proposed[3] = previous[3] if len(previous)>3 and previous[3] else proposed[3]
            proposed[8] = previous[8] if len(previous)>8 and previous[8] else proposed[8]
            proposed[9] = previous[9] if len(previous)>9 and previous[9] else proposed[9]
            if proposed != (previous + [""] * 10)[:10]:
                updates.append({"range": f"'Enrichment Queue'!A{old[0]}:J{old[0]}", "values":[proposed]})
        else:
            inserts.append(proposed)
    if updates:
        book.values_batch_update({"valueInputOption":"RAW","data":updates})
    if inserts:
        sheet.append_rows(inserts,value_input_option="RAW",table_range="A:J")
    print(f"Enrichment queue: {len(inserts)} new, {len(updates)} refreshed, {len(indexed)} existing. No unverified facts written to Properties.")

if __name__ == "__main__":
    main()
