"""Daily, source-fresh CURRENT SALES view. Only live Active future Creek sheriff sales.

Uses only the new official sheriff extract from this SAME GitHub Actions run.
Neither archived GIS data nor missing-owner estimates can create a sales row.
All manual research stays in 01 DEALS / 03 RESEARCH; this view is disposable.
"""
import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import gspread
from google.oauth2.service_account import Credentials
from sync_owner_queue import rows_from_records

SHEET_ID="1vbgqFm_tygMJ545DbQU8vY_RaJr8IbSQG7_PMqmBNdQ"
TAB="00 CURRENT SALES"
HEADERS=["Street Address","City","Likely Owner / Defendant","Ownership",
         "Auction Date","Minimum Bid","Sheriff Appraisal","Sheriff Status",
         "Court Case","Next Action","Source","Last Source Check"]
def choose_rows(records,deals,today,checked):
    """Return only future, explicitly Active, addressed sheriff listings."""
    indexed={r[13]:r for r in deals[1:] if len(r)>13 and r[13]}
    result=[]
    for r in rows_from_records(records,today):
        lead=r[15]
        old=indexed.get(lead,[])
        display_owner=r[2] or "Owner identity needs research"
        if len(old)>3 and old[3]=="Owner verified" and old[2]:
            display_owner=old[2]
            ownership="Deed verified — review source"
        else:
            ownership=("Court defendant — NOT deed verified"
                       if display_owner!="Owner identity needs research"
                       else "Owner identity needs research")
        next_action=(old[9] if len(old)>9 and old[9] else
                     "Check current deed, liens, property condition & costs")
        result.append([r[0],r[1],display_owner,ownership,r[4],r[5],
                      r[6],"Active — confirm before bid",r[10],
                      next_action,r[12],checked])
    return sorted(result,key=lambda x:(x[4],x[1],x[0]))

def main():
    latest=Path("output/creek_sheriff.json")
    if not latest.exists():raise RuntimeError("No official sheriff snapshot from this run")
    records=json.loads(latest.read_text(encoding="utf-8"))
    if not records:raise RuntimeError("Official collector returned no records, refusing to clear current view")
    now=datetime.now(ZoneInfo("America/Chicago"))
    checked=now.strftime("%Y-%m-%d %I:%M %p %Z")
    token=os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not token:raise RuntimeError("Missing Google Sheets authorization secret")
    credentials=Credentials.from_service_account_info(json.loads(token),
        scopes=["https://www.googleapis.com/auth/spreadsheets"])
    book=gspread.authorize(credentials).open_by_key(SHEET_ID)
    target=book.worksheet(TAB)
    previous=target.get_all_values()
    if not previous or previous[0][:len(HEADERS)]!=HEADERS:
        raise RuntimeError("Current sales sheet schema mismatch; refusing changes")
    deals=book.worksheet("01 DEALS").get_all_values()
    if not deals or deals[0][:3]!=["Address","City","Likely Owner"]:
        raise RuntimeError("Deal data schema mismatch")
    rows=choose_rows(records,deals,now.date(),checked)
    if len(rows)+1>target.row_count:
        target.add_rows(len(rows)+1-target.row_count)
    # Rebuild only this read-only snapshot; never overwrite analyst notes or texts.
    if rows:
        target.update(range_name=f"A2:L{len(rows)+1}",values=rows,value_input_option="RAW")
    # Delete old snapshot rows, including when there are zero current sales.
    prior_count=len(previous)-1
    if prior_count>len(rows):
        target.batch_clear([f"A{len(rows)+2}:L{prior_count+1}"])
    if not rows:
        target.update(range_name="A2",values=[["No Active future sales on latest sheriff snapshot"]])
    Path("output").mkdir(exist_ok=True)
    meta={"active_future":len(rows),"checked_at":now.isoformat(),
          "source":"https://www.creekcountysheriff.gov/sheriff-sales"}
    Path("output/current_sales_sync.json").write_text(json.dumps(meta,indent=2))
    print("Current sheriff opportunities:",meta)
if __name__=="__main__":main()
