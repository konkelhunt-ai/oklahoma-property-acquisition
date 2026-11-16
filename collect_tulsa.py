"""Fetch and inspect the Tulsa County Sheriff's official Excel report.
Never import historical files as current auctions.
"""
import csv
import io
import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
import pandas as pd

PAGE = "https://tcso.org/public-auction-report-excel/"
CASE = re.compile(r"\b(?:CJ|CV)[-\s]?\d{2,4}[-\s]?\d{2,6}\b", re.I)
OUTPUT = Path("output")
OUTPUT.mkdir(exist_ok=True)

def run():
    headers = {"User-Agent": "Mozilla/5.0 (compatible; OklahomaPropertyResearch/1.0)"}
    response = requests.get(PAGE, headers=headers, timeout=45)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    link = next((a for a in soup.find_all("a", href=True)
                 if "Public Auction Report - Excel" in a.get_text(" ", strip=True)
                 and "Previous" not in a.get_text(" ", strip=True)), None)
    if not link:
        raise RuntimeError("Current official Tulsa Excel report link not found")
    url = urljoin(PAGE, link["href"])
    result = requests.get(url, headers=headers, timeout=60)
    result.raise_for_status()
    if len(result.content) < 500:
        raise RuntimeError("Official report download unexpectedly small")
    (OUTPUT / "tulsa_official_report.xls").write_bytes(result.content)
    sheets = pd.read_excel(io.BytesIO(result.content), sheet_name=None, header=None, dtype=str)
    now = datetime.now(timezone.utc)
    records = []
    dates_found = []
    for tab, frame in sheets.items():
        for _, row in frame.fillna("").iterrows():
            cells = [str(x).strip() for x in row.tolist()]
            joined = " | ".join(cells)
            for match in re.finditer(r"\b(?:0?[1-9]|1[0-2])[/.-](?:0?[1-9]|[12]\d|3[01])[/.-]20\d{2}\b", joined):
                try:
                    dates_found.append(datetime.strptime(match.group().replace("-", "/").replace(".", "/"), "%m/%d/%Y").replace(tzinfo=timezone.utc))
                except ValueError:
                    pass
            cases = CASE.findall(joined)
            if not cases:
                continue
            case = cases[0].upper().replace(" ", "-")
            # Retain full official row rather than guessing address/attorney columns.
            import hashlib
            identifier = "TULSA-" + hashlib.sha256((case + "|" + joined).encode()).hexdigest()[:14]
            records.append({"lead_id": identifier, "county": "Tulsa", "case_number": case,
                            "status": "Needs verification", "sale_date": "", "address": "",
                            "plaintiff": "", "source_url": url, "checked_at": now.isoformat(),
                            "source_row": joined, "source_tab": tab})
    manifest = {"source_page": PAGE, "download_url": url, "checked_at": now.isoformat(),
                "rows_with_cases": len(records), "dates_detected": [d.date().isoformat() for d in dates_found[:40]],
                "warning": "Do not import until official report freshness and field mapping are validated"}
    (OUTPUT / "tulsa_manifest.json").write_text(json.dumps(manifest, indent=2))
    (OUTPUT / "tulsa_unverified_rows.json").write_text(json.dumps(records, indent=2))
    if not dates_found or max(dates_found) < now - timedelta(days=45):
        raise RuntimeError("Official linked spreadsheet appears historical or has no recent report date; import blocked")
    if not records:
        raise RuntimeError("No case records in official report; import blocked")
    print(f"Inspected {len(records)} case rows from official Tulsa Excel. Manual column mapping still required; no sheet changes.")

if __name__ == "__main__":
    run()
