"""Keep the simple Tulsa-area owner-verification queue current from Creek sheriff sales.

Street address and named court defendant come from the sheriff; recorded owner does NOT.
Never turn defendants into owners, overwrite analyst verification, or auto-send messages.
"""
import json
import os
import re
from datetime import datetime, timezone, date
from pathlib import Path
import gspread
from google.oauth2.service_account import Credentials

SHEET_ID="1vbgqFm_tygMJ545DbQU8vY_RaJr8IbSQG7_PMqmBNdQ"
TAB="01 Leads - Verify Owner"
SOURCE="https://www.creekcountysheriff.gov/sheriff-sales"
INPUT=Path("output/creek_sheriff.json")
HEADERS=["Street Address","City","Owner of Record","Court-Named Defendant (NOT Owner Verification)",
         "Auction Date","Minimum Bid","Appraisal","Sheriff Status","Owner Verification",
         "Next Action","Case Number","County","Source","Updated","Notes","Lead ID"]
CITIES=["Sapulpa","Bristow","Kellyville","Kiefer","Mannford","Drumright","Oilton",
        "Depew","Mounds","Slick","Shamrock","Jenks","Tulsa","Sand Springs"]
def parse_address(raw):
    value=re.sub(r"\s+"," ",str(raw or "")).strip()
    if not re.match(r"^\d{1,6}\s+[^,]+",value): return None
    for city in sorted(CITIES,key=len,reverse=True):
        m=re.search(r"(?:,\s*|\s+)"+re.escape(city)+r"(?:,\s*OK(?:\s+\d{5})?)?$",value,re.I)
        if m: return value[:m.start()].strip(" ,"),city
    return None
def key(case,address):
    case=re.sub(r"\s+","-",case.upper().strip())
    slug=re.sub(r"[^A-Z0-9]","",address.upper())[:12]
    return f"CREEK-{case}-{slug}"
def iso_date(value):
    for fmt in ("%m/%d/%Y","%Y-%m-%d"):
        try:return datetime.strptime(value.strip(),fmt).date()
        except (ValueError,AttributeError): pass
    return None
def rows_from_records(records,today):
    updates=[]
    for rec in records:
        parsed=parse_address(rec.get("address",""))
        day=iso_date(rec.get("sale_date",""))
        if not parsed or not day: continue
        address,city=parsed
        if not re.match(r"^(CJ|CV)-\d{2,4}-\d{1,6}$",rec.get("case_number",""),re.I):continue
        status=str(rec.get("status","")).strip()
        # New opportunities must have an upcoming date and be marked Active.
        if status.lower()!="active" or day<=today: continue
        lead=key(rec["case_number"],address)
        updates.append([address,city,"NOT YET VERIFIED",rec.get("defendant",""),
                        day.isoformat(),rec.get("minimum_bid",""),rec.get("appraisal",""),
                        "Active — check for recalls","Needs assessor/deed verification",
                        "Verify assessor owner and recorded deed before contacting anyone",
                        rec["case_number"],"Creek",SOURCE,
                        datetime.now(timezone.utc).date().isoformat(),
                        "Court-named defendant is not confirmed property owner.",lead])
    return updates
def main():
    if not INPUT.exists(): raise RuntimeError("Missing latest sheriff extract")
    records=json.loads(INPUT.read_text(encoding="utf-8"))
    if not records: raise RuntimeError("Official extract has no records, refusing to change sheet")
    today=datetime.now(timezone.utc).date()
    staged=rows_from_records(records,today)
    if not staged:
        # Normal when no active upcoming sales, but avoid destroying old records.
        print("No new qualifying future sheriff listings; existing lead queue preserved")
        return
    secret=os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not secret: raise RuntimeError("Missing GOOGLE_SERVICE_ACCOUNT_JSON")
    creds=Credentials.from_service_account_info(json.loads(secret),
        scopes=["https://www.googleapis.com/auth/spreadsheets"])
    book=gspread.authorize(creds).open_by_key(SHEET_ID)
    sheet=book.worksheet(TAB)
    previous=sheet.get_all_values()
    if not previous or previous[0][:16]!=HEADERS: raise RuntimeError("Verification queue schema changed")
    bykey={r[15]:(i+2,r) for i,r in enumerate(previous[1:]) if len(r)>15 and r[15]}
    updates=[]; inserts=[]; now=datetime.now(timezone.utc).date().isoformat()
    for row in staged:
        k=row[15]
        if k in bykey:
            n,old=bykey[k]
            # Preserve owner (C), human verification (I), and notes (O).
            # Never change the owner of record just because an auction lists a defendant.
            if (old+[""]*16)[:2]!=row[:2]:
                updates.append({"range":f"'{TAB}'!A{n}:B{n}","values":[row[:2]]})
            if (old+[""]*16)[3:8]!=row[3:8]:
                updates.append({"range":f"'{TAB}'!D{n}:H{n}","values":[row[3:8]]})
            updates.append({"range":f"'{TAB}'!J{n}:N{n}","values":[row[9:14]]})
        else: inserts.append(row)
    # When an existing case is explicitly recalled/inactive, update its status,
    # never label a vanished case "sold" without an official sale result.
    statuses={}
    for rec in records:
        parsed=parse_address(rec.get("address",""))
        if parsed:
            statuses[key(rec.get("case_number",""),parsed[0])]=rec.get("status","")
    for k,(n,old) in bykey.items():
        status=str(statuses.get(k,"")).lower()
        if status in ("recalled","inactive","sold"):
            updates.append({"range":f"'{TAB}'!H{n}","values":[[status.title()+" — do not bid"]]})
    for i in range(0,len(updates),100):
        book.values_batch_update({"valueInputOption":"RAW","data":updates[i:i+100]})
    if inserts:sheet.append_rows(inserts,value_input_option="RAW",table_range="A:P")
    Path("output/owner_queue_sync.json").write_text(json.dumps(
        {"upcoming_addressed":len(staged),"new_rows":len(inserts),
         "refreshed_cells":len(updates),"checked":now},indent=2))
    print(f"Owner verification queue: {len(staged)} future addressed sales, {len(inserts)} new.")
if __name__=="__main__":main()
