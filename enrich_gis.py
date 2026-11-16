"""Exact parcel enrichment from official county GIS, with a pluggable adapter registry.
Writes only to Parcel Enrichment staging; never guesses missing values or updates ownership in Properties.
"""
import json, os, re, time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import requests, gspread
from google.oauth2.service_account import Credentials

SHEET_ID="1vbgqFm_tygMJ545DbQU8vY_RaJr8IbSQG7_PMqmBNdQ"
GIS="https://services8.arcgis.com/euhkr1dAJeQBIjV0/arcgis/rest/services/TaxParcelsPublics_view/FeatureServer/0"
HEADERS=["Lead ID","County","Parcel ID","Match Status","Assessor Account","Situs / Location","Situs City","Assessor Owner Name","Legal Description","Parcel Acres","Assessor Source","Checked At","Notes","GIS Features"]
def norm(s): return re.sub(r"\D","",str(s or ""))
def request(session,url,params):
    for attempt in range(3):
        try:
            r=session.get(url,params=params,timeout=40);r.raise_for_status();data=r.json()
            if "error" in data: raise RuntimeError(str(data["error"]))
            return data
        except (ValueError,RuntimeError,requests.RequestException):
            if attempt==2: raise
            time.sleep(2**attempt)
def field(a,names):
    for n in names:
        val=a.get(n)
        if val is not None and str(val).strip(): return str(val).strip()
    return ""
def okcounty(session,items):
    meta=request(session,GIS,{"f":"json"})
    fields={x["name"] for x in meta.get("fields",[])}
    if not {"PARCELNB_1","location","name1"}.issubset(fields):
        raise RuntimeError("Oklahoma County GIS schema changed")
    query_ids=sorted({norm(x["parcel"]) for x in items if len(norm(x["parcel"]))==13})
    matches={}
    for i in range(0,len(query_ids),20):
        batch=query_ids[i:i+20]
        where="PARCELNB_1 IN ("+",".join("'"+x+"'" for x in batch)+")"
        data=request(session,GIS+"/query",{"f":"json","where":where,"outFields":"*","returnGeometry":"false","resultRecordCount":1000})
        if data.get("exceededTransferLimit"): raise RuntimeError("Parcel results truncated")
        for obj in data.get("features",[]):
            attrs=obj.get("attributes") or {}
            key=norm(attrs.get("PARCELNB_1"))
            if key in batch: matches.setdefault(key,[]).append(attrs)
        time.sleep(.2)
    result=[]; now=datetime.now(timezone.utc).isoformat()
    for x in items:
        key=norm(x["parcel"]); candidates=matches.get(key,[])
        if len(key)!=13: status="Invalid identifier"; note="Unexpected parcel number length"; a={}
        elif not candidates: status="Not found"; note="No exact parcel match; requires manual review"; a={}
        else:
            signatures={(field(y,["accountno"]),field(y,["name1"]),field(y,["location"])) for y in candidates}
            if len(signatures)>1: status="Conflicting matches";note="Multiple inconsistent assessor records; manual review";a={}
            else: status="Exact parcel match";note="Assessor records are not proof of title, ownership today, or availability";a=candidates[0]
        result.append([x["id"],"Oklahoma",x["parcel"],status,field(a,["accountno"]),field(a,["location"]),
            field(a,["locationcity"]),field(a,["name1"]),field(a,["legal","legaldesc","legaldescription"]),
            field(a,["acres","acreage"]),GIS,now,note,str(len(candidates))])
    return result

ADAPTERS={"Oklahoma":okcounty}
def main():
    raw=os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not raw: raise RuntimeError("Google secret missing")
    creds=Credentials.from_service_account_info(json.loads(raw),scopes=["https://www.googleapis.com/auth/spreadsheets"])
    book=gspread.authorize(creds).open_by_key(SHEET_ID)
    values=book.worksheet("Properties").get_all_values()
    if not values: raise RuntimeError("Properties empty")
    cols={v:i for i,v in enumerate(values[0])}
    if not {"Lead ID","County","Parcel ID"}.issubset(cols): raise RuntimeError("Unexpected Properties headers")
    groups={}
    for row in values[1:]:
        def at(n): return row[cols[n]].strip() if cols[n]<len(row) else ""
        if at("County") in ADAPTERS and at("Lead ID") and at("Parcel ID"):
            groups.setdefault(at("County"),[]).append({"id":at("Lead ID"),"parcel":at("Parcel ID")})
    if not groups: raise RuntimeError("No supported parcels to look up")
    session=requests.Session();session.headers["User-Agent"]="OklahomaPropertyAcquisition/1.0 public GIS research"
    output=[]
    for county,items in groups.items(): output.extend(ADAPTERS[county](session,items))
    if not output or len({r[0] for r in output})!=len(output): raise RuntimeError("Empty or duplicate enrichment")
    folder=Path("output");folder.mkdir(exist_ok=True)
    (folder/"parcel_enrichment.json").write_text(json.dumps(output,indent=2),encoding="utf-8")
    try: tab=book.worksheet("Parcel Enrichment")
    except gspread.WorksheetNotFound:
        tab=book.add_worksheet(title="Parcel Enrichment",rows=1000,cols=len(HEADERS))
        tab.update(range_name="A1:N1",values=[HEADERS])
    previous=tab.get_all_values()
    if not previous or previous[0][:len(HEADERS)]!=HEADERS: raise RuntimeError("Unexpected enrichment headers")
    positions={r[0]:i+2 for i,r in enumerate(previous[1:]) if r and r[0]}
    updates=[]; inserts=[]
    for row in output:
        if row[0] in positions: updates.append({"range":f"'Parcel Enrichment'!A{positions[row[0]]}:N{positions[row[0]]}","values":[row]})
        else: inserts.append(row)
    for i in range(0,len(updates),100):
        book.values_batch_update({"valueInputOption":"RAW","data":updates[i:i+100]})
    if inserts: tab.append_rows(inserts,value_input_option="RAW",table_range="A:N")
    print("Enrichment status: "+str(dict(Counter(r[3] for r in output))))
    print(f"Synced {len(inserts)} new and {len(updates)} existing enriched rows; Properties unchanged")
if __name__=="__main__": main()
