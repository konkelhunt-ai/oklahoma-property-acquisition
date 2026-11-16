"""Refresh the easy-to-read dashboard from the underlying, county-independent source tabs.

Never fabricate a situs address or a private owner. Source tables remain intact.
"""
import json,os
from pathlib import Path
import gspread
from google.oauth2.service_account import Credentials
SHEET_ID="1vbgqFm_tygMJ545DbQU8vY_RaJr8IbSQG7_PMqmBNdQ"
TAB="PROPERTY DASHBOARD"
HEADERS=["County","City","Property Address","Recorded Owner","Parcel ID","Suggested Bid","Acres","Screening","Next Step","Sale Status","Source","Lead ID","Parcel Map","Address Source"]
def records(ws):
    rows=ws.get_all_values()
    if not rows: raise RuntimeError(f"{ws.title} empty")
    cols={h:i for i,h in enumerate(rows[0])}
    return cols,{r[0]:r for r in rows[1:] if r and r[0]}
def field(record,cols,key):
    i=cols.get(key,-1)
    return record[i].strip() if i>=0 and i<len(record) else ""
def main():
    secret=os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not secret: raise RuntimeError("Missing service account")
    credentials=Credentials.from_service_account_info(json.loads(secret),scopes=["https://www.googleapis.com/auth/spreadsheets"])
    book=gspread.authorize(credentials).open_by_key(SHEET_ID)
    pc,props=records(book.worksheet("Properties"))
    ec,enriched=records(book.worksheet("Parcel Enrichment"))
    gc,screened=records(book.worksheet("GIS Screening"))
    try:
        lc,locations=records(book.worksheet("Parcel Locations"))
    except gspread.WorksheetNotFound:
        lc,locations={},{}
    # Owner Research can contain analyst-verified owners; prefer them only when
    # the recorded match is verified and not an unconfirmed possible owner.
    oc,owners=records(book.worksheet("Owner Research"))
    sheet=book.worksheet(TAB)
    existing=sheet.get_all_values()
    if not existing or existing[0][:12]!=HEADERS[:12]: raise RuntimeError("Dashboard schema changed")
    if sheet.col_count<len(HEADERS): sheet.add_cols(len(HEADERS)-sheet.col_count)
    if existing[0][12:14]!=HEADERS[12:14]:
        sheet.update(range_name="M1:N1",values=[HEADERS[12:14]])
    output=[]
    for lead,p in props.items():
        e=enriched.get(lead,[]); g=screened.get(lead,[]); o=owners.get(lead,[]); loc=locations.get(lead,[])
        getp=lambda k:field(p,pc,k)
        gete=lambda k:field(e,ec,k)
        getg=lambda k:field(g,gc,k)
        owner=getp("Owner Name") or gete("Assessor Owner Name") or "Owner not verified"
        # Owner Research is a separate research workspace; do not silently
        # substitute an unverified person for the official assessor owner.
        address=getp("Street Address")
        if not address:
            location=gete("Situs / Location")
            address="No street address on file" if not location or location.upper().startswith("0 UNKNOWN") else location
        official=field(loc,lc,"Official Situs Address")
        if official: address=official
        if official:
            address_type="Official situs"
        elif field(loc,lc,"Location Type"):
            address_type=field(loc,lc,"Location Type")
        elif address!="No street address on file":
            address_type="Assessor location"
        else:
            address_type="Address unavailable"
        flag=getg("Screening Flag") or "NOT SCREENED"
        if flag=="RESEARCH CANDIDATE": action="Research access, zoning & title"
        elif flag=="UNMATCHED": action="Confirm parcel ID"
        elif flag=="SMALL PARCEL": action="Check dimensions & legal access"
        else: action="Hold - review legal/physical risk"
        output.append([getp("County") or "Unknown",gete("Situs City") or getp("City") or "Unknown",
            address,owner,getp("Parcel ID") or gete("Parcel ID"),
            getp("Minimum Bid") or getg("Suggested Initial Bid"),
            gete("Parcel Acres") or getg("Acres"),flag,action,
            getp("Auction Status") or "Not verified",
            getp("Source URL") or getg("Treasurer Source"),lead,
            field(loc,lc,"Map Link"),address_type])
    # Refresh source-derived display only. Dashboard is a read-only overview.
    needed=len(output)+1
    if sheet.row_count<needed: sheet.add_rows(needed-sheet.row_count)
    if output:
        for i in range(0,len(output),200):
            start=i+2
            sheet.update(range_name=f"A{start}:N{start+len(output[i:i+200])-1}",
                         values=output[i:i+200],value_input_option="RAW")
    if len(existing)>needed:
        sheet.batch_clear([f"A{needed+1}:N{len(existing)}"])
    Path("output").mkdir(exist_ok=True)
    Path("output/dashboard_sync.json").write_text(json.dumps({"dashboard_leads":len(output)},indent=2))
    print(f"Dashboard refreshed: {len(output)} properties")
if __name__=="__main__":main()
