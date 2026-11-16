"""Investigate current Creek County treasurer tax roll by parcel number.

Read-only: diagnostic artifact. Do not treat a third-party parcel claim as confirmed,
or a tax-billed owner as a deed-certified current owner.
"""
import json,re
from datetime import datetime,timezone
from pathlib import Path
from playwright.sync_api import sync_playwright
URL="https://oktaxrolls.com/searchTaxRoll/Creek?tax_info_sel=property_id"
PARCEL="0000-20-018-012-0-022-00"
OUT=Path("output")
def visible_text(page):
    try:return page.locator("body").inner_text(timeout=9000)[:18000]
    except:return ""
def input_info(page):
    fields=[]
    el=page.locator("input")
    for i in range(min(el.count(),45)):
        item=el.nth(i)
        x=item.evaluate("(e)=>({outer:e.outerHTML.slice(0,600),name:e.name,id:e.id,type:e.type,placeholder:e.placeholder})")
        x["visible"]=item.is_visible()
        fields.append(x)
    return fields
def main():
    OUT.mkdir(exist_ok=True)
    report={"source":URL,"input_parcel":PARCEL,"checked_at":datetime.now(timezone.utc).isoformat(),"steps":[]}
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        page=browser.new_page(viewport={"width":1280,"height":860})
        try:
            response=page.goto(URL,wait_until="domcontentloaded",timeout=50000)
            page.wait_for_timeout(1400)
            report["http_status"]=response.status if response else None
            report["steps"].append({"stage":"open","url":page.url,"body":visible_text(page)[:2200],"inputs":input_info(page)})
            target=None
            for css in ('input[name*="property" i]','input[id*="property" i]',
                        'input[placeholder*="xxxx" i]','input[placeholder*="Property" i]'):
                loc=page.locator(css)
                for i in range(loc.count()):
                    if loc.nth(i).is_visible() and loc.nth(i).get_attribute("type")!="hidden":
                        target=loc.nth(i)
                        break
                if target:break
            if target:
                report["selected_input"]=target.evaluate("(e)=>e.outerHTML.slice(0,400)")
                target.fill(PARCEL)
                target.press("Enter")
                page.wait_for_timeout(2200)
                report["steps"].append({"stage":"submit Enter","url":page.url,"body":visible_text(page),"inputs":input_info(page)})
                report["found_exact_parcel"]=PARCEL.replace("-","") in re.sub(r"[^0-9]","",visible_text(page))
            else:
                report["blocker"]="No identifiable visible parcel ID search input found"
        except Exception as exc:
            report["error"]=type(exc).__name__+": "+str(exc)[:500]
        finally:
            browser.close()
    (OUT/"creek_taxroll_parcel_probe.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k!="steps"},indent=2))
    for step in report["steps"]:
        print("STAGE",step["stage"],"url",step["url"])
        print("VISIBLE BODY",step["body"][:3200])
        print("INPUTS",[(x["name"],x["id"],x["placeholder"],x["visible"]) for x in step["inputs"] if x["visible"]][:20])
if __name__=="__main__":main()
