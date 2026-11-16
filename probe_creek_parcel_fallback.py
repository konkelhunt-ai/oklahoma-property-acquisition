"""Resolve a foreclosure property by its independently reported PARCEL number.

The county's current assessor search may index parcel IDs even when the sheriff
street address is absent. This is a diagnostic only: do NOT update ownership
unless BOTH parcel ID AND situs match, with separate deed/title verification.
"""
import json,re
from datetime import datetime,timezone
from pathlib import Path
from playwright.sync_api import sync_playwright
from lookup_creek_current import PAGE,normalized_address,extract_record

TARGET={
    "address":"6125 W HILTON RD",
    "city":"Sapulpa",
    "case":"CJ-26-122",
    "third_party_parcel":"0000-20-018-012-0-022-00",
    "parcel_source":"https://www.ownerly.com/ok/sapulpa/hilton-rd-home-details",
}
OUT=Path("output");OUT.mkdir(exist_ok=True)
def main():
    report={"requested":TARGET,"checked_at":datetime.now(timezone.utc).isoformat(),
            "source":PAGE,"results":[],"status":"Not resolved"}
    variants=["0000-20-018-012-0-022-00","000020018012002200",
              "018012002200","6125","HILTON"]
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        page=browser.new_page(viewport={"width":1280,"height":900})
        try:
            page.goto(PAGE,wait_until="domcontentloaded",timeout=50000)
            page.wait_for_timeout(1500)
            start=page.get_by_role("button",name="Get Started")
            if start.count() and start.first.is_visible():
                start.first.click()
            field=page.locator("#srch-parcel")
            for value in variants:
                field.fill(value)
                page.wait_for_timeout(1100)
                items=page.locator("ul.ui-autocomplete:visible li .ui-menu-item-wrapper")
                labels=[items.nth(i).inner_text().strip() for i in range(min(items.count(),120))]
                matches=[x for x in labels if
                         "6125" in x.upper() or
                         ("000020018012002200" in re.sub("[^0-9]","",x))]
                report["results"].append({"query":value,"count":len(labels),
                         "samples":labels[:12],"potential":matches[:20]})
                # Select only suggestions explicitly mentioning same parcel number
                # or matching FULL situs, never a 7125 Hilton neighbor.
                exact=[x for x in matches if
                       normalized_address(x)==normalized_address(TARGET["address"])]
                if len(exact)==1:
                    for i in range(items.count()):
                        if items.nth(i).inner_text().strip()==exact[0]:
                            items.nth(i).click()
                            break
                    page.wait_for_timeout(1350)
                    cards=page.locator("#results-panel .results-list--div")
                    possibilities=[]
                    for i in range(min(cards.count(),20)):
                        rec=extract_record(cards.nth(i).inner_text())
                        possibilities.append(rec)
                    report["results"][-1]["parcel_records"]=possibilities
                    good=[r for r in possibilities if
                          normalized_address(r.get("situs",""))==normalized_address(TARGET["address"])
                          and r.get("account") and r.get("assessor_owner")]
                    if len(good)==1:
                        report["status"]="Exact street/situs match from parcel lookup — deed unverified"
                        report["assessor_owner"]=good[0]["assessor_owner"]
                        report["assessor_account"]=good[0]["account"]
                        report["assessor_situs"]=good[0]["situs"]
                        break
                field.fill("")
        except Exception as exc:
            report["error"]=type(exc).__name__+": "+str(exc)[:350]
        finally:
            browser.close()
    (OUT/"creek_parcel_fallback.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print("PARCEL LOOKUP:",report["status"])
    for item in report["results"]:
        print(item["query"],"candidates",item["count"],"likely",item["potential"][:8])
    if report.get("assessor_owner"):
        print("EXACT COUNTY SITUS OWNER:",report["assessor_owner"],"ACCOUNT:",report["assessor_account"])
if __name__=="__main__":
    main()
