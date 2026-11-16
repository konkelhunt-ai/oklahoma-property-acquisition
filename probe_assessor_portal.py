"""One-off diagnostic of Creek County's CURRENT assessor portal.

The goal is to learn whether current address/owner lookup can be automated
reliably, without using the stale 2023 GIS layer. No sheet changes.
"""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

URL="https://oklmrecords.com/creek/map/"
OUT=Path("output"); OUT.mkdir(exist_ok=True)
ADDRESS="801 S MAIN ST"
def summarize(page,label):
    text=page.locator("body").inner_text(timeout=15000)
    (OUT/f"assessor_{label}.txt").write_text(text[:25000],encoding="utf-8")
    (OUT/f"assessor_{label}.html").write_text(page.content()[:150000],encoding="utf-8")
    try:page.screenshot(path=str(OUT/f"assessor_{label}.png"),full_page=False)
    except Exception:pass
    ins=page.locator("input")
    inputs=[]
    for i in range(min(ins.count(),25)):
        x=ins.nth(i)
        inputs.append({
            "outerHTML":x.evaluate("(e)=>e.outerHTML").replace("\n"," ")[:500],
            "visible":x.is_visible(),
        })
    return {"url":page.url,"title":page.title(),"body":text[:4000],"inputs":inputs}
def main():
    details={"source":URL,"address":ADDRESS,"steps":[],"response_urls":[]}
    with sync_playwright() as play:
        browser=play.chromium.launch(headless=True)
        page=browser.new_page(viewport={"width":1280,"height":850})
        page.on("response",lambda r: details["response_urls"].append({
            "status":r.status,
            "url":r.url[:250]
        }) if ("/api/" in r.url.lower() or "search" in r.url.lower() or "parcel" in r.url.lower()) and len(details["response_urls"])<70 else None)
        try:
            page.goto(URL,wait_until="domcontentloaded",timeout=50000)
            page.wait_for_timeout(3500)
            details["steps"].append({"label":"open",**summarize(page,"open")})
            button=page.get_by_role("button",name="Get Started")
            if button.count() and button.first.is_visible():
                button.first.click()
                page.wait_for_timeout(1500)
                details["steps"].append({"label":"start",**summarize(page,"start")})
            # Use only a visible assessor parcel-search field, not Google 911 address search.
            candidates=page.locator('input[placeholder*="search" i]')
            search=None
            for i in range(candidates.count()):
                if candidates.nth(i).is_visible():
                    search=candidates.nth(i);break
            if search is None:
                details["blocker"]="No visible assessor search field"
            else:
                search.fill(ADDRESS)
                search.press("Enter")
                page.wait_for_timeout(4500)
                details["steps"].append({"label":"search",**summarize(page,"search")})
                # Select only an exact address when visible.
                exact=page.get_by_text("801 S MAIN ST",exact=False)
                if exact.count():
                    for i in range(min(exact.count(),8)):
                        x=exact.nth(i)
                        if x.is_visible():
                            try:
                                x.click(timeout=3000)
                                page.wait_for_timeout(2700)
                                details["steps"].append({"label":"selected",**summarize(page,"selected")})
                                break
                            except Exception:pass
        except Exception as exc:
            details["error"]=type(exc).__name__+": "+str(exc)[:500]
        browser.close()
    (OUT/"current_assessor_probe.json").write_text(json.dumps(details,indent=2),encoding="utf-8")
    print(json.dumps({"address":ADDRESS,"steps":[(x["label"],x["url"],len(x["inputs"])) for x in details["steps"]],
          "urls":details["response_urls"][:20],"error":details.get("error"),"blocker":details.get("blocker")},indent=2))
if __name__=="__main__":main()
