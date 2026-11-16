"""Resolve parcel-number locations from Oklahoma County's public assessor GIS.

Official situs addresses are distinguished from approximate GIS map points.
Never reverse-geocode a neighboring house into an invented parcel address.
"""
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
import requests
import gspread
from google.oauth2.service_account import Credentials

SHEET_ID="1vbgqFm_tygMJ545DbQU8vY_RaJr8IbSQG7_PMqmBNdQ"
GIS="https://services8.arcgis.com/euhkr1dAJeQBIjV0/arcgis/rest/services/TaxParcelsPublics_view/FeatureServer/0"
TAB="Parcel Locations"
HEADERS=["Lead ID","Parcel ID","Official Situs Address","Location Type","Latitude","Longitude","Map Link","Assessor Account","GIS Source","Checked At"]
def digits(value): return re.sub(r"\D","",str(value or ""))
def fetch(session,params):
    for attempt in range(3):
        try:
            response=session.get(GIS+"/query",params=params,timeout=55)
            response.raise_for_status()
            payload=response.json()
            if "error" in payload: raise RuntimeError(str(payload["error"]))
            if payload.get("exceededTransferLimit"): raise RuntimeError("Truncated GIS results")
            return payload
        except (requests.RequestException,ValueError,RuntimeError):
            if attempt==2: raise
            time.sleep(2**attempt)
def valid_address(s):
    s=str(s or "").strip()
    if not s or s.upper().startswith("0 UNKNOWN") or s.upper() in {"UNKNOWN","N/A","0"}:
        return ""
    # A city or an unknown road is not an assigned physical address.
    return s if re.match(r"^\d+\s+\S+",s) else ""
def polygon_point(feature):
    centroid=feature.get("centroid") or {}
    if isinstance(centroid,dict) and "x" in centroid and "y" in centroid:
        return (float(centroid["y"]),float(centroid["x"]))
    geom=feature.get("geometry") or {}
    # The envelope midpoint is only an approximate mapping point; never call it a
    # street address, exact survey coordinate, or proof of legal access.
    pts=[p for ring in geom.get("rings",[]) for p in ring if len(p)>=2]
    if not pts: return None
    xs=[float(p[0]) for p in pts];ys=[float(p[1]) for p in pts]
    return ((min(ys)+max(ys))/2,(min(xs)+max(xs))/2)
def locate(items,session):
    ids=sorted({digits(x["parcel"]) for x in items if len(digits(x["parcel"]))==13})
    byid={}
    for start in range(0,len(ids),12):
        batch=ids[start:start+12]
        where="PARCELNB_1 IN ("+",".join("'"+x+"'" for x in batch)+")"
        payload=fetch(session,{"f":"json","where":where,"outFields":"PARCELNB_1,location,accountno",
                               "returnGeometry":"true","returnCentroid":"true",
                               "outSR":"4326","resultRecordCount":1000})
        for feat in payload.get("features",[]):
            attrs=feat.get("attributes") or {}
            key=digits(attrs.get("PARCELNB_1"))
            if key in batch: byid.setdefault(key,[]).append(feat)
        time.sleep(.2)
    stamp=datetime.now(timezone.utc).isoformat()
    out=[]
    for item in items:
        key=digits(item["parcel"])
        feats=byid.get(key,[])
        addresses={valid_address((f.get("attributes") or {}).get("location")) for f in feats}
        addresses.discard("")
        # Multiple inconsistent official situs values must be reviewed manually.
        address=next(iter(addresses)) if len(addresses)==1 else ""
        pt=next((p for f in feats if (p:=polygon_point(f)) is not None),None)
        status=("Official situs" if address else "GIS map point only" if pt else
                "No GIS location found")
        if len(addresses)>1: status="Conflicting situs values - review"
        lat=f"{pt[0]:.6f}" if pt else ""
        lon=f"{pt[1]:.6f}" if pt else ""
        maplink=f"https://www.google.com/maps/search/?api=1&query={lat}%2C{lon}" if pt else ""
        account=(feats[0].get("attributes") or {}).get("accountno","") if feats else ""
        out.append([item["lead"],item["parcel"],address,status,lat,lon,maplink,
                    str(account or ""),GIS,stamp])
    return out
def main():
    secret=os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not secret: raise RuntimeError("Missing GOOGLE_SERVICE_ACCOUNT_JSON")
    creds=Credentials.from_service_account_info(json.loads(secret),
        scopes=["https://www.googleapis.com/auth/spreadsheets"])
    book=gspread.authorize(creds).open_by_key(SHEET_ID)
    values=book.worksheet("Parcel Enrichment").get_all_values()
    cols={name:i for i,name in enumerate(values[0])}
    for required in ["Lead ID","County","Parcel ID"]:
        if required not in cols: raise RuntimeError("Parcel Enrichment schema changed")
    items=[{"lead":r[cols["Lead ID"]],"parcel":r[cols["Parcel ID"]]}
           for r in values[1:] if len(r)>max(cols["Lead ID"],cols["County"],cols["Parcel ID"])
           and r[cols["Lead ID"]] and r[cols["County"]]=="Oklahoma"]
    if not items: raise RuntimeError("No Oklahoma County parcels to locate")
    session=requests.Session()
    session.headers["User-Agent"]="OklahomaPropertyAcquisition/1.0 assessor GIS research"
    rows=locate(items,session)
    try: tab=book.worksheet(TAB)
    except gspread.WorksheetNotFound:
        tab=book.add_worksheet(title=TAB,rows=max(500,len(rows)+10),cols=len(HEADERS))
        tab.update(range_name="A1:J1",values=[HEADERS])
    previous=tab.get_all_values()
    if not previous or previous[0][:len(HEADERS)]!=HEADERS:
        raise RuntimeError("Parcel Locations schema mismatch")
    positions={r[0]:i+2 for i,r in enumerate(previous[1:]) if r and r[0]}
    updates=[];inserts=[]
    for row in rows:
        if row[0] in positions:
            updates.append({"range":f"'{TAB}'!A{positions[row[0]]}:J{positions[row[0]]}","values":[row]})
        else: inserts.append(row)
    for i in range(0,len(updates),100):
        book.values_batch_update({"valueInputOption":"RAW","data":updates[i:i+100]})
    if inserts: tab.append_rows(inserts,value_input_option="RAW",table_range="A:J")
    Path("output").mkdir(exist_ok=True)
    stats={k:sum(r[3]==k for r in rows) for k in sorted({r[3] for r in rows})}
    Path("output/parcel_locations.json").write_text(json.dumps({"total":len(rows),"status":stats},indent=2))
    print("Parcel locations:",len(rows),stats)
if __name__=="__main__":main()
