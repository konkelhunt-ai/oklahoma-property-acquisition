"""Keep FastPeopleSearch name/address links current; preserve all human research.

No scraping, mass skip tracing, automated outreach or sending.
"""
import json, os
from pathlib import Path
import gspread
from google.oauth2.service_account import Credentials

SHEET_ID="1vbgqFm_tygMJ545DbQU8vY_RaJr8IbSQG7_PMqmBNdQ"
TAB="04 CONTACT RESEARCH"
HEADERS=["Property Address","City","Potential Owner","Owner Evidence","FastPeopleSearch - Name",
         "FastPeopleSearch - Address","Matched Person","Possible Phone","Identity Check",
         "Contact Review","Source Profile URL","Last Checked","Research Notes",
         "Lead ID","Review Gate"]
DEAL_HEADERS=["Address","City","Likely Owner","Owner Status","Sale Date","Minimum Bid",
              "Sheriff Status","Stage","Phone","Next Action","Follow-up","Case",
              "Official Source","Lead ID","Assigned To","Notes"]

def field_formula(letter,row):
    return f'=IFERROR(INDEX(\'01 DEALS\'!{letter}2:{letter}400,MATCH(N{row},\'01 DEALS\'!N2:N400,0)),"")'

def review_gate(row):
    return (f'=IF(OR(REGEXMATCH(LOWER(D{row}),'
            f'"mismatch|estate|deceased|discrepancy|variant|unclear|incorrect"),'
            f'G{row}="",I{row}<>"Name + address confirmed",'
            f'J{row}<>"Reviewed - permitted",K{row}="",'
            f'LEN(REGEXREPLACE(TO_TEXT(H{row}),"[^0-9]",""))<10,'
            f'LEN(REGEXREPLACE(TO_TEXT(H{row}),"[^0-9]",""))>11),'
            f'"HOLD","READY FOR MANUAL REVIEW")')

def fastpeople_formulas(n):
    # SEO-style person and reverse-address links documented for FastPeopleSearch.
    # This navigates to the site; no personal records are scraped or assumed.
    slug=lambda letter: f'LOWER(REGEXREPLACE(TRIM({letter}{n}),"[^A-Za-z0-9]+","-"))'
    name=(f'=IF(OR(C{n}="",REGEXMATCH(LOWER(C{n}),'
          f'"needs research|unknown|deceased|estate| and |&")),"",'
          f'HYPERLINK("https://www.fastpeoplesearch.com/name/"&'
          f'{slug("C")}&"_"&{slug("B")}&"-ok","FastPeopleSearch name"))')
    address=(f'=IF(A{n}="","",HYPERLINK("https://www.fastpeoplesearch.com/address/"&'
             f'{slug("A")}&"_"&{slug("B")}&"-ok","FastPeopleSearch address"))')
    return [name,address]

def row_for(lead,status,row):
    n=row
    name,address=fastpeople_formulas(n)
    status_low=status.lower()
    note=("HOLD: sheriff defendant and assessor name differ; establish deed/title first."
          if "mismatch" in status_low else
          "HOLD: deceased party/estate; identify living owner or authorized representative."
          if "estate" in status_low or "deceased" in status_low else
          "HOLD: sheriff address differs from county records; verify legal description."
          if "discrepancy" in status_low or "variant" in status_low else
          "Match full name AND property address; directory phone data can be outdated.")
    return ([field_formula(c,n) for c in "ABCD"]+
            [name,address,"","","Not reviewed","Not reviewed","","",note,lead,
             review_gate(n)])

def main():
    secret=os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not secret:raise RuntimeError("Missing Google authorization")
    creds=Credentials.from_service_account_info(json.loads(secret),
        scopes=["https://www.googleapis.com/auth/spreadsheets"])
    book=gspread.authorize(creds).open_by_key(SHEET_ID)
    sheet=book.worksheet(TAB)
    old=sheet.get_all_values()
    if not old or old[0][:len(HEADERS)]!=HEADERS:
        raise RuntimeError("Contact research schema mismatch, refusing write")
    deals=book.worksheet("01 DEALS").get_all_values()
    if not deals or deals[0][:len(DEAL_HEADERS)]!=DEAL_HEADERS:
        raise RuntimeError("Deals schema mismatch, refusing write")
    seen={r[13] for r in old[1:] if len(r)>13 and r[13]}
    additions=[]
    for raw in deals[1:]:
        r=(raw+[""]*16)[:16]
        if not r[13] or not r[0] or r[13] in seen:continue
        n=len(old)+len(additions)+1
        additions.append(row_for(r[13],r[3],n))
        seen.add(r[13])
    # Refresh only search links (columns E:F) on existing leads; never
    # overwrite matched person, candidate number, review notes, or decisions.
    fixes=[]
    for i,r in enumerate(old[1:],start=2):
        if len(r)>13 and r[13]:
            fixes.append({"range":f"'{TAB}'!E{i}:F{i}",
                          "values":[fastpeople_formulas(i)]})
    for i in range(0,len(fixes),80):
        book.values_batch_update({"valueInputOption":"USER_ENTERED","data":fixes[i:i+80]})
    if additions:
        sheet.append_rows(additions,value_input_option="USER_ENTERED",table_range="A:O")
    Path("output").mkdir(exist_ok=True)
    result={"deals":len(deals)-1,"refreshed_fastpeople_links":len(fixes),"new_research_rows":len(additions),
            "automatic_messages":0}
    Path("output/contact_lookup_sync.json").write_text(json.dumps(result,indent=2))
    print(result)

if __name__=="__main__":main()
