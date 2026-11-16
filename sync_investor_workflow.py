"""Populate the three simple acquisition workflow tabs from official Creek sale leads.

This is intentionally conservative:
* New sheriff leads get a trackable address and likely defendant, never invented title.
* Analysts own owner/deed verification, phone, deal stage, budgets, decisions, texts.
* No messages are sent; every draft requires a manual phone and approval review.
* Existing analyst records are never cleared when a source disappears.
"""
import json
import os
from pathlib import Path
import gspread
from google.oauth2.service_account import Credentials

SHEET_ID = "1vbgqFm_tygMJ545DbQU8vY_RaJr8IbSQG7_PMqmBNdQ"
SOURCE_TAB = "01 Leads - Verify Owner"
DEALS_TAB = "01 DEALS"
TEXTS_TAB = "02 TEXTS"
RESEARCH_TAB = "03 RESEARCH"
SOURCE_HEADERS = [
    "Street Address", "City", "Owner Name (See Verification)",
    "Court-Named Defendant (NOT Owner Verification)", "Auction Date",
    "Minimum Bid", "Appraisal", "Sheriff Status", "Owner Verification",
    "Next Action", "Case Number", "County", "Source", "Updated", "Notes", "Lead ID",
]
DEALS_HEADERS = [
    "Address", "City", "Likely Owner", "Owner Status", "Sale Date",
    "Minimum Bid", "Sheriff Status", "Stage", "Phone", "Next Action",
    "Follow-up", "Case", "Official Source", "Lead ID", "Assigned To", "Notes",
]
TEXTS_HEADERS = [
    "Address", "Owner", "Phone", "Personalized SMS", "Open Google Voice",
    "Approval", "DNC / Consent", "Sent By", "Sent Date", "Reply", "Follow-up", "Lead ID",
]
RESEARCH_HEADERS = [
    "Address", "City", "Case", "Sheriff Appraisal", "Minimum Bid",
    "Deposit at Minimum (10%)", "Record Owner", "Title & Liens",
    "Property Type", "Condition", "Value / Comps", "Repairs", "Max Bid",
    "Deal Decision", "Official Source", "Lead ID", "Plaintiff", "Notes",
    "Other Costs", "Target Profit", "Owner / Assessor Search", "Research Gate",
]
ASSESSOR_URL = "https://oklmrecords.com/creek/map/"
RESEARCH_GATE = "HOLD: deed, liens, condition, value & funds not verified"

def read(sheet, expected):
    raw = sheet.get_all_values()
    if not raw or raw[0][:len(expected)] != expected:
        raise RuntimeError(f"{sheet.title}: schema mismatch, no changes made")
    return raw

def owner_status(name, verification):
    if verification == "Verified — source in notes":
        return "Owner verified"
    if not name or name.lower().startswith("owner identity needs"):
        return "Unclear / estate"
    return "Likely court defendant"

def text_formula(lead_row):
    return [
        f'=IFERROR(INDEX(\'01 DEALS\'!A$2:A$400,MATCH($L{lead_row},\'01 DEALS\'!N$2:N$400,0)),"")',
        f'=IFERROR(INDEX(\'01 DEALS\'!C$2:C$400,MATCH($L{lead_row},\'01 DEALS\'!N$2:N$400,0)),"")',
        f'=IFERROR(INDEX(\'01 DEALS\'!I$2:I$400,MATCH($L{lead_row},\'01 DEALS\'!N$2:N$400,0)),"")',
        f'=IF(OR(B{lead_row}="",REGEXMATCH(LOWER(B{lead_row}),"unknown|needs research|not yet verified|unclear"),REGEXMATCH(LOWER(IFERROR(INDEX(\'01 DEALS\'!D$2:D$400,MATCH($L{lead_row},\'01 DEALS\'!N$2:N$400,0)),"")),"estate|deceased|incorrect|do not contact|mismatch|variant")), "", "Hi "&REGEXEXTRACT(B{lead_row},"^[^ ]+")&", I\'m Xavier. I\'m interested in the property at "&A{lead_row}&" in "&IFERROR(INDEX(\'01 DEALS\'!B$2:B$400,MATCH($L{lead_row},\'01 DEALS\'!N$2:N$400,0)),"")&" and wanted to ask whether you would consider a direct sale. No pressure; if you\'re not interested, just let me know and I won\'t follow up.")',
        '=HYPERLINK("https://voice.google.com/u/0/messages","Open Google Voice")',
    ]

def max_bid_formula(row):
    # Required inputs K = estimated sale value, L = repairs, S = other total
    # costs, T = target profit. Sheriff appraisal is NOT used as ARV.
    return f'=IF(AND(ISNUMBER(K{row}),ISNUMBER(L{row}),ISNUMBER(S{row}),ISNUMBER(T{row})),MAX(0,K{row}-L{row}-S{row}-T{row}),"")'

def deposit_formula(row):
    # Illustration at published minimum only; 10% of ACTUAL winning bid due.
    return f'=IFERROR(VALUE(SUBSTITUTE(SUBSTITUTE(E{row},"$",""),",",""))*10%,"")'

def upsert(book):
    src = read(book.worksheet(SOURCE_TAB), SOURCE_HEADERS)
    deals_ws = book.worksheet(DEALS_TAB)
    texts_ws = book.worksheet(TEXTS_TAB)
    research_ws = book.worksheet(RESEARCH_TAB)
    deals = read(deals_ws, DEALS_HEADERS)
    texts = read(texts_ws, TEXTS_HEADERS)
    research = read(research_ws, RESEARCH_HEADERS)

    deal_ix = {r[13]: (i+2, r) for i,r in enumerate(deals[1:]) if len(r)>13 and r[13]}
    text_ix = {r[11]: (i+2, r) for i,r in enumerate(texts[1:]) if len(r)>11 and r[11]}
    research_ix = {r[15]: (i+2, r) for i,r in enumerate(research[1:]) if len(r)>15 and r[15]}
    deal_ins, text_ins, research_ins, changes = [], [], [], []
    for record in src[1:]:
        r = (record+[""]*len(SOURCE_HEADERS))[:len(SOURCE_HEADERS)]
        address, city, owner, defendant, sale_date, bid, appraisal, status, verified, action, case, county, url, updated, notes, lead = r
        if not lead or not address or not city or not case: continue
        if county.lower()!="creek":continue
        name=owner if owner else "Owner identity needs research"
        state=owner_status(name,verified)
        msg = "Verify assessor/deed owner and liens; compare condition, cost and resale comps"
        if state=="Unclear / estate": msg="Probate/heirs: identify living owner or estate representative before outreach"
        owner_note = "Court defendant is only a possible owner; verify current deed and any court recall before taking action."
        fresh=[address,city,name,state,sale_date,bid,status,"New Lead","",msg,
               "",case,url,lead,"",owner_note]
        if lead in deal_ix:
            n,old=deal_ix[lead]; prior=(old+[""]*16)[:16]
            # Source fields, but not stage/phone/manual follow-up/assignment/notes.
            if prior[:2]!=fresh[:2]:
                changes.append({"range":f"'{DEALS_TAB}'!A{n}:B{n}","values":[fresh[:2]]})
            if prior[4:7]!=fresh[4:7]:
                changes.append({"range":f"'{DEALS_TAB}'!E{n}:G{n}","values":[fresh[4:7]]})
            if prior[11:14]!=fresh[11:14]:
                changes.append({"range":f"'{DEALS_TAB}'!L{n}:N{n}","values":[fresh[11:14]]})
            # Preserve manually checked ownership. Court updates can replace
            # only a court-derived value; never a deed-confirmed name.
            if prior[3] not in ("Owner verified","Incorrect match","Assessor match — deed pending","Estate / deceased — deed pending","Assessor/defendant mismatch — deed pending","Assessor address variant — deed pending") and prior[2:4]!=fresh[2:4]:
                changes.append({"range":f"'{DEALS_TAB}'!C{n}:D{n}","values":[fresh[2:4]]})
        else:
            deal_ins.append(fresh)
        if lead not in text_ix:
            row_num=len(texts)+len(text_ins)+1
            text_ins.append(text_formula(row_num)+["Draft","Not reviewed","","","","",lead])
        if lead not in research_ix:
            row_num=len(research)+len(research_ins)+1
            row=[address,city,case,appraisal,bid,deposit_formula(row_num),
                 "Not verified","Not checked","Unknown","Not inspected",
                 "", "",max_bid_formula(row_num),"Not evaluated",url,lead,"",
                 "Sheriff appraisal is NOT estimated resale value. 10% applies to the winning bid; don't enter or bid without verifying liens, deed and condition.",
                 "", "",ASSESSOR_URL,RESEARCH_GATE]
            if len(row)!=len(RESEARCH_HEADERS):
                raise RuntimeError("Research new-row width mismatch")
            research_ins.append(row)
        else:
            n,old=research_ix[lead]; prior=(old+[""]*len(RESEARCH_HEADERS))[:len(RESEARCH_HEADERS)]
            # Source-derived auction figures and link; all analyst research stays untouched.
            for lo,hi,segment in [(0,3,[address,city,case]),(3,5,[appraisal,bid]),(14,16,[url,lead])]:
                if prior[lo:hi]!=segment:
                    from_col=["A","D","O"][[0,3,14].index(lo)]
                    end_col=["C","E","P"][[0,3,14].index(lo)]
                    changes.append({"range":f"'{RESEARCH_TAB}'!{from_col}{n}:{end_col}{n}",
                                    "values":[segment]})
    for i in range(0,len(changes),100):
        book.values_batch_update({"valueInputOption":"RAW","data":changes[i:i+100]})
    if deal_ins: deals_ws.append_rows(deal_ins,value_input_option="RAW",table_range="A:P")
    if research_ins: research_ws.append_rows(research_ins,value_input_option="USER_ENTERED",table_range="A:V")
    if text_ins: texts_ws.append_rows(text_ins,value_input_option="USER_ENTERED",table_range="A:L")
    return {
        "source_leads":len(src)-1,"new_deals":len(deal_ins),
        "new_research":len(research_ins),"new_text_drafts":len(text_ins),
        "updated_source_ranges":len(changes)
    }

def main():
    secret=os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not secret:raise RuntimeError("Missing GOOGLE_SERVICE_ACCOUNT_JSON")
    creds=Credentials.from_service_account_info(
        json.loads(secret),scopes=["https://www.googleapis.com/auth/spreadsheets"])
    book=gspread.authorize(creds).open_by_key(SHEET_ID)
    info=upsert(book)
    Path("output").mkdir(exist_ok=True)
    Path("output/investor_workflow_sync.json").write_text(json.dumps(info,indent=2))
    print("Investor workflow:",info)

if __name__=="__main__":
    main()
