"""Research ONLY unresolved Creek foreclosure addresses by current county assessor search.

Returns suggestions + candidate owner panels; these are NOT verified deed owners
and never write to the investor worksheet automatically.
"""
import json,re
from pathlib import Path
from datetime import datetime,timezone
from playwright.sync_api import sync_playwright
from lookup_creek_current import PAGE, normalized_address
OUT=Path("output");OUT.mkdir(exist_ok=True)
QUERIES={
"17398 S 246TH W PL":["MARCOU","246TH","17398 S 246"],
"6125 W HILTON RD":["HILTON","SPARKS","6125 W"],
"805 E PERSHING PL":["PERSHING","HIGGINS","805 E"],
"3566 W 151ST ST":["3566 W 151ST ST S","ANSON"],
}
def main():
    collected={}
    with sync_playwright() as play:
        browser=play.chromium.launch(headless=True)
        page=browser.new_page()
        page.goto(PAGE,wait_until="domcontentloaded",timeout=55000)
        page.wait_for_timeout(1400)
        start=page.get_by_role("button",name="Get Started")
        if start.count() and start.first.is_visible():start.first.click()
        field=page.locator("#srch-parcel")
        for address,queries in QUERIES.items():
            options=[]
            for q in queries:
                field.fill(q)
                page.wait_for_timeout(750)
                menu=page.locator("ul.ui-autocomplete:visible li .ui-menu-item-wrapper")
                labels=[menu.nth(i).inner_text().strip() for i in range(min(menu.count(),120))]
                possible=[v for v in labels if (("["+"Address"+"]") in v and
                            (v.lstrip("0").split(" ")[0]==address.split(" ")[0]
                             or "PERSHING" in v or "HILTON" in v or "246" in v or "151" in v))
                            or ("[Name]" in v and any(t in v.upper() for t in
                                    ["MARCOU","HIGGINS","ANSON","SPARKS"]))]
                options.append({"query":q,"suggestions_count":len(labels),
                                "relevant":possible[:50]})
            collected[address]=options
            field.fill("")
        browser.close()
    record={"checked_at":datetime.now(timezone.utc).isoformat(),"source":PAGE,
            "warning":"Address candidate suggestions only; no owner assignment without an exact parcel situs match.",
            "unresolved":collected}
    (OUT/"unresolved_sheriff_addresses.json").write_text(json.dumps(record,indent=2))
    for addr,options in collected.items():
        print(addr,"::",[(q["query"],q["relevant"][:5]) for q in options])
if __name__=="__main__":main()
