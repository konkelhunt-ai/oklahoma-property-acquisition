"""Synchronize all GIS-screened leads into a persistent, analyst-safe diligence ledger.

Every county adapter emits the common GIS Screening schema. Existing analyst columns
J:T are never overwritten; records with risk flags are retained with an explicit
automated disposition in a new column U, rather than deleted or treated as investable.
"""
import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import gspread
from google.oauth2.service_account import Credentials

SHEET_ID="1vbgqFm_tygMJ545DbQU8vY_RaJr8IbSQG7_PMqmBNdQ"
TAB="Due Diligence Tracker"
HEADERS=[
 "Lead ID","County","Parcel ID","City","Acres","County Suggested Bid (NOT value)",
 "Legal Description","Sale Source","Assessor Source","Availability Verified",
 "Parcel Boundary / Road Access","Buildability / Zoning","Utilities / Flood",
 "Title / Liens","Market Comps / Value","Estimated Total Cost","Decision",
 "Assigned To","Last Verified","Research Notes","Automated Screening Flag",
 "Research Priority","Screening Synced At"
]
COUNTY_PREFIX={"OKCOUNTY-":"Oklahoma"}
def getrows(sheet):
    raw=sheet.get_all_values()
    if not raw: raise RuntimeError(f"{sheet.title} is empty")
    return raw[0],[r for r in raw[1:] if r and r[0]]
def lookup(row,cols,name):
    i=cols.get(name,-1)
    return row[i].strip() if i>=0 and i<len(row) else ""
def main():
    raw=os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not raw: raise RuntimeError("Missing GOOGLE_SERVICE_ACCOUNT_JSON")
    creds=Credentials.from_service_account_info(json.loads(raw),scopes=["https://www.googleapis.com/auth/spreadsheets"])
    book=gspread.authorize(creds).open_by_key(SHEET_ID)
    screen=book.worksheet("GIS Screening")
    header,records=getrows(screen)
    cols={n:i for i,n in enumerate(header)}
    required={"Lead ID","Parcel ID","GIS Match","City","Acres","Legal Description",
              "Suggested Initial Bid","Screening Flag","GIS Source","Treasurer Source"}
    if not required.issubset(cols): raise RuntimeError(f"Missing GIS columns: {required-set(cols)}")
    dest=book.worksheet(TAB)
    previous_header,previous=getrows(dest)
    if previous_header[:20]!=HEADERS[:20]: raise RuntimeError("Due Diligence Tracker header mismatch")
    if dest.col_count<len(HEADERS):
        dest.add_cols(len(HEADERS)-dest.col_count)
    if len(previous_header)<len(HEADERS):
        dest.update(range_name="U1:W1",values=[HEADERS[20:]])
    prior={r[0]:(i+2,r) for i,r in enumerate(previous) if r and r[0]}
    now=datetime.now(timezone.utc).isoformat()
    inserts,updates,counts=[],[],Counter()
    for r in records:
        lead=lookup(r,cols,"Lead ID")
        if not lead: continue
        county=lookup(r,cols,"County") or next((v for k,v in COUNTY_PREFIX.items() if lead.startswith(k)),"County unverified")
        flag=lookup(r,cols,"Screening Flag")
        counts[flag]+=1
        if flag=="RESEARCH CANDIDATE":
            priority="REVIEW - requires verification"
        elif flag=="UNMATCHED":
            priority="IDENTITY RESEARCH - no parcel match"
        else:
            priority="HOLD - physical or legal risk"
        fields=[lead,county,lookup(r,cols,"Parcel ID"),lookup(r,cols,"City"),
            lookup(r,cols,"Acres"),lookup(r,cols,"Suggested Initial Bid"),
            lookup(r,cols,"Legal Description"),lookup(r,cols,"Treasurer Source"),
            lookup(r,cols,"GIS Source")]
        if lead in prior:
            n,old=prior[lead]
            # Only write the 9 source fields, and the three computed columns U:W.
            # All analyst-managed cells J:T, including notes and decision, are preserved.
            if fields!=(old+[""]*9)[:9]:
                updates.append({"range":f"'{TAB}'!A{n}:I{n}","values":[fields]})
            computed=[flag,priority,now]
            if computed!=(old+[""]*23)[20:23]:
                updates.append({"range":f"'{TAB}'!U{n}:W{n}","values":[computed]})
        else:
            row=fields+["Not verified"]*5+["Not researched","","RESEARCH ONLY","","",
              "Unverified: confirm county availability, legal access, zoning, title and economics before bidding.",
              flag,priority,now]
            if len(row)!=len(HEADERS): raise RuntimeError("Incorrect row width")
            inserts.append(row)
    for i in range(0,len(updates),100):
        book.values_batch_update({"valueInputOption":"RAW","data":updates[i:i+100]})
    if inserts: dest.append_rows(inserts,value_input_option="RAW",table_range="A:W")
    Path("output").mkdir(exist_ok=True)
    Path("output/diligence_sync.json").write_text(json.dumps({"screened":sum(counts.values()),
        "by_flag":dict(counts),"new":len(inserts),"updated_ranges":len(updates)},indent=2))
    print(f"Due diligence ledger: {sum(counts.values())} leads; {len(inserts)} added, {len(updates)} refreshed ranges. Analyst fields J:T preserved.")
if __name__=="__main__": main()
