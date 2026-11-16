"""Diagnostic: check public (historical 2023) Creek GIS for parcel / owner clues.

This script DOES NOT write ownership to the user-facing sheet. A historical GIS
owner is not evidence of current deed ownership.
"""
import json, re, requests
from pathlib import Path
BASE = "https://map11.incog.org/arcgis11wa/rest/services/Parcels_CreekCo/MapServer/0"
ADDRESSES = [
"23569 W 102nd St S, Sapulpa","801 S Main St, Bristow",
"17398 S 246th W Pl, Kellyville","6125 W Hilton Rd, Sapulpa",
"805 E Pershing Pl, Bristow","3566 W 151st St, Kiefer",
"304 S Maple St, Bristow","778 N Moccasin St, Sapulpa",
"3636 Hillside Dr, Sapulpa"]
KEYS=["parcelid","account","ownername","situs","address1","citystate",
"propclass","acres","landvalue","imprvalue","totalvalue","saledate","bookpage","JOIN_ADDR"]
def request(session,url,params):
    x=session.get(url,params=params,timeout=35)
    x.raise_for_status()
    data=x.json()
    if "error" in data: raise RuntimeError(str(data["error"]))
    return data
def candidates(session,address):
    number=re.match(r"^\d+",address).group()
    # Broad by street number. Verify the street token in the result in the next
    # stage before linking a historical parcel to a present auction address.
    road_terms={"23569":"102ND","801":"MAIN","17398":"246TH","6125":"HILTON",
                "805":"PERSHING","3566":"151ST","304":"MAPLE","778":"MOCCASIN",
                "3636":"HILLSIDE"}
    road=road_terms.get(number)
    where=(f"(situs LIKE '%{number}%' AND situs LIKE '%{road}%') OR "
           f"(JOIN_ADDR LIKE '%{number}%' AND JOIN_ADDR LIKE '%{road}%')")
    data=request(session,BASE+"/query",{"f":"json","where":where,
         "outFields":",".join(KEYS),"returnGeometry":"false",
         "resultRecordCount":100})
    return data.get("features",[])
def main():
    output=Path("output");output.mkdir(exist_ok=True)
    session=requests.Session()
    session.headers["User-Agent"]="OklahomaPropertyAcquisition/1.0 parcel identity research"
    result={"source":BASE,"staleness":"2023 layer: do not treat as current ownership","records":[]}
    try:
        meta=request(session,BASE,{"f":"json"})
        result["description"]=meta.get("description")
        result["schema_fields"]=[f["name"] for f in meta.get("fields",[])]
        print("GIS metadata readable; fields:",",".join(result["schema_fields"][:28]))
    except Exception as exc:
        result["metadata_error"]=type(exc).__name__+": "+str(exc)[:250]
        print("GIS metadata ERROR:",result["metadata_error"])
    for address in ADDRESSES:
        r={"requested_address":address}
        try:
            all_candidates=candidates(session,address)
            r["candidate_count"]=len(all_candidates)
            # Protect against false street-number hits. Data is for manual review,
            # not a claimed exact match.
            r["candidates"]=[{k:v for k,v in (c.get("attributes") or {}).items() if k in KEYS}
                  for c in all_candidates[:50]]
        except Exception as exc:
            r["error"]=type(exc).__name__+": "+str(exc)[:250]
        result["records"].append(r)
        print(address,": ",r.get("candidate_count"),r.get("error",""))
    (output/"creek_gis_probe.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    if all("error" in x for x in result["records"]):
        raise RuntimeError("All historical GIS queries failed; see artifact")
if __name__=="__main__":main()
