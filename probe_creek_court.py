"""Read-only public OSCN case check for the three unresolved Creek foreclosures.

The sheriff listing confirms street address and defendant; OSCN may reveal an
underlying legal description/party relationships. Does NOT prove deed ownership.
"""
import json,re
from pathlib import Path
from datetime import datetime,timezone
from playwright.sync_api import sync_playwright
OUT=Path("output");OUT.mkdir(exist_ok=True)
CASES=["CJ-2026-83","CJ-2026-122","CJ-2026-20"]
BASE="https://www.oscn.net/dockets/GetCaseInformation.aspx"
def main():
    output={"checked_at":datetime.now(timezone.utc).isoformat(),"source":BASE,"cases":[]}
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        page=browser.new_page()
        for case in CASES:
            item={"case":case,"status":"Not confirmed"}
            try:
                url=f"{BASE}?db=creek&number={case}"
                resp=page.goto(url,wait_until="domcontentloaded",timeout=45000)
                page.wait_for_timeout(1100)
                text=page.locator("body").inner_text(timeout=9000)
                item["url"]=page.url
                item["http_status"]=resp.status if resp else None
                item["snippet"]=text[:11000]
                item["links"]=[{"label":x.inner_text().strip()[:90],"href":x.get_attribute("href")}
                               for x in page.locator("a").all()[:90]
                               if x.get_attribute("href") and ("pdf" in x.get_attribute("href").lower() or
                                   "caseinformation" in x.get_attribute("href").lower())]
                item["status"]="Page loaded — review case identity" if case in text or case.replace("2026","26") in text else "Page loaded; case identity not confirmed"
            except Exception as e:
                item["error"]=type(e).__name__+": "+str(e)[:300]
            output["cases"].append(item)
            print(case,item["status"],item.get("http_status"),item.get("error",""))
        browser.close()
    (OUT/"creek_oscn_cases.json").write_text(json.dumps(output,indent=2),encoding="utf-8")
if __name__=="__main__":main()
