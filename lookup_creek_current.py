"""Current Creek assessor search with exact situs matching.

Uses the live OKLM County Assessor page, not the outdated 2023 parcel dataset.
Never equate a search result for 1801 with the property at 801.
First stage: research-only JSON/CSV artifact, no sheet edits or outreach.
"""
import json
import re
from pathlib import Path
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright

PAGE="https://oklmrecords.com/creek/map/"
SOURCE="Creek County Assessor, live parcel record search"
ADDRESSES=[
("801 S MAIN ST","Bristow","CJ-25-417"),
("23569 W 102ND ST S","Sapulpa","CJ-26-8"),
("17398 S 246TH W PL","Kellyville","CJ-26-83"),
("6125 W HILTON RD","Sapulpa","CJ-26-122"),
("805 E PERSHING PL","Bristow","CJ-26-20"),
("3566 W 151ST ST","Kiefer","CJ-23-352"),
("304 S MAPLE ST","Bristow","CJ-25-439"),
("778 N MOCCASIN ST","Sapulpa","CJ-26-41"),
("3636 HILLSIDE DR","Sapulpa","CJ-25-248"),
]
OUT=Path("output")
# Use conservative street token mapping, not fuzzy geographic matches.
SHORT={"STREET":"ST","PLACE":"PL","ROAD":"RD","DRIVE":"DR","AVENUE":"AVE",
       "NORTH":"N","SOUTH":"S","EAST":"E","WEST":"W"}
def normalized_address(s):
    s=re.sub(r"\s*\[(?:Address|Name|Legal|Account)\].*$","",str(s),flags=re.I).upper().strip()
    s=re.sub(r"[.,#]"," ",s)
    tokens=s.split()
    if not tokens:return ""
    tokens=[SHORT.get(t,t) for t in tokens]
    tokens=[re.sub(r"^(\d+)(?:ST|ND|RD|TH)$",r"\1",t) for t in tokens]
    if tokens[0].isdigit():tokens[0]=str(int(tokens[0]))
    return " ".join(tokens)

def extract_record(text):
    # The record card selected from official live page; not the sidebar
    # autocomplete, which may contain similar but different street numbers.
    def find(label):
        m=re.search(r"(?im)^"+re.escape(label)+r":\s*(.+)$",text)
        return m.group(1).strip() if m else ""
    return {"account":find("Account"),"assessor_owner":find("Owner's Name"),
            "situs":find("Situs")}

def search_one(page,street,city,case):
    result={"requested_address":street,"city":city,"case":case,
            "source":PAGE,"status":"No exact match",
            "checked_at":datetime.now(timezone.utc).isoformat()}
    field=page.locator("#srch-parcel")
    number=street.split()[0]
    searches=[street,number,number.zfill(5)]
    tried=[]
    exact=[]
    address_variant=False
    for search in dict.fromkeys(searches):
        field.fill(search)
        # A partial number may find a parcel whose indexed address differs from
        # the sheriff's spelling. Never accept a different house number.
        page.wait_for_timeout(900)
        labels=page.locator("ul.ui-autocomplete:visible li .ui-menu-item-wrapper")
        suggestions=[labels.nth(i).inner_text().strip()
                     for i in range(min(labels.count(),100))]
        tried.append({"query":search,"suggestions":suggestions[:40]})
        exact=[x for x in suggestions if normalized_address(x)==normalized_address(street)]
        if not exact and case=="CJ-23-352":
            # Sheriff omits a final directional S; current property listings
            # also show 3566 W 151ST ST S. Record as a VARIANT, not an exact match.
            alternative=[x for x in suggestions
                         if normalized_address(x)==normalized_address(street)+" S"]
            if len(alternative)==1:
                exact=alternative
                address_variant=True
        if exact:break
    result["tried"]=tried
    result["candidate_labels"]=tried[-1]["suggestions"] if tried else []
    if len(exact)!=1:
        result["status"]="Ambiguous" if len(exact)>1 else "No exact address suggestion"
        field.fill("")
        return result
    exact_label=exact[0]
    result["selected_exact_label"]=exact_label
    matches=page.locator("ul.ui-autocomplete:visible li .ui-menu-item-wrapper")
    for i in range(matches.count()):
        if matches.nth(i).inner_text().strip()==exact_label:
            matches.nth(i).click(timeout=5000)
            break
    page.wait_for_timeout(1400)
    cards=page.locator("#results-panel .results-list--div")
    possibilities=[]
    for i in range(min(cards.count(),25)):
        item=cards.nth(i)
        t=item.inner_text()
        record=extract_record(t)
        record["panel"]=t[:400]
        possibilities.append(record)
    result["record_options"]=possibilities
    compare=normalized_address(street)+(" S" if address_variant else "")
    real=[r for r in possibilities if normalized_address(r["situs"])==compare
          and r["account"] and r["assessor_owner"]]
    if len(real)!=1:
        result["status"]="Ambiguous parcel records" if len(real)>1 else "No exact parcel record"
    else:
        r=real[0]
        result.update({"status":("Near-exact situs: sheriff omits trailing S — confirm deed"
                                               if address_variant else
                                               "Exact assessor situs match — deed unverified"),
                       "assessor_owner":r["assessor_owner"],"assessor_account":r["account"],
                       "assessor_situs":r["situs"],
                       "assessor_details_url":PAGE.replace("/map/","/map/details.php?account="+r["account"])})
    # Clear old search to avoid autocomplete/sidepanel cross-contamination.
    field.fill("")
    page.wait_for_timeout(200)
    return result

def main():
    OUT.mkdir(exist_ok=True)
    results=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        page=browser.new_page(viewport={"width":1280,"height":850})
        try:
            page.goto(PAGE,wait_until="domcontentloaded",timeout=55000)
            page.wait_for_timeout(1200)
            start=page.get_by_role("button",name="Get Started")
            if start.count() and start.first.is_visible():
                start.first.click()
                page.wait_for_timeout(500)
            for street,city,case in ADDRESSES:
                try:
                    rec=search_one(page,street,city,case)
                except Exception as e:
                    rec={"requested_address":street,"case":case,"status":"Error",
                         "error":type(e).__name__+": "+str(e)[:250]}
                results.append(rec)
                print(street,rec.get("status"),rec.get("assessor_owner",""),rec.get("assessor_account",""))
        finally:
            browser.close()
    stats={}
    for rec in results:stats[rec["status"]]=stats.get(rec["status"],0)+1
    output={"checked_at":datetime.now(timezone.utc).isoformat(),"official_search":PAGE,
            "facts_caveat":"Assessor owner is not independently confirmed deed title; exact situs match required.",
            "status_counts":stats,"records":results}
    (OUT/"current_creek_assessor_matches.json").write_text(json.dumps(output,indent=2))
    print("Summary",stats)
if __name__=="__main__":main()
